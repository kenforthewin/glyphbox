"""
Eat when hungry skill.

Consumes food from inventory when the player reaches a specified
hunger level, with safety checks for dangerous or tainted food.
"""


async def eat_when_hungry(
    nh,
    hunger_threshold: str = "hungry",
    allow_corpses: bool = False,
    **params,
):
    """
    Eat food when hunger reaches specified threshold.

    Scans inventory for safe food items and consumes them
    when hunger level is at or below the threshold.

    Category: resource
    Stops when: ate_food, no_food, not_hungry, unsafe_food_only, game_over

    Args:
        nh: NetHackAPI instance
        hunger_threshold: Hunger level to trigger eating ("hungry", "weak", "fainting")
        allow_corpses: Whether to eat corpses (risky without knowledge)

    Returns:
        SkillResult with eating outcome
    """
    # Map hunger states to numeric values for comparison
    HUNGER_LEVELS = {
        "satiated": 0,
        "not hungry": 1,
        "hungry": 2,
        "weak": 3,
        "fainting": 4,
        "fainted": 5,
    }

    threshold_value = HUNGER_LEVELS.get(hunger_threshold.lower(), 2)

    # Check game state
    if nh.is_done:
        return SkillResult.stopped(
            "game_over",
            success=False,
            actions=0,
            turns=0,
        )

    # Get current stats
    stats = nh.get_stats()
    # stats.hunger is a HungerState enum, get its value as lowercase string
    current_hunger = stats.hunger.value.lower() if stats.hunger else "not hungry"
    current_value = HUNGER_LEVELS.get(current_hunger, 1)

    # Check if we need to eat
    if current_value < threshold_value:
        return SkillResult.stopped(
            "not_hungry",
            success=True,
            actions=0,
            turns=0,
            hunger=current_hunger,
        )

    # Get inventory
    inventory = nh.get_inventory()

    # Filter for food items
    food_items = []
    for item in inventory:
        # Check if it's food using the is_food property or '%' symbol
        if item.is_food or item.char == '%':
            food_items.append(item)

    if not food_items:
        return SkillResult.stopped(
            "no_food",
            success=False,
            actions=0,
            turns=0,
            hunger=current_hunger,
        )

    # Filter for safe food
    safe_food = []
    unsafe_reasons = []

    for item in food_items:
        name = item.name.lower() if item.name else ""

        # Skip corpses unless allowed
        if "corpse" in name:
            if not allow_corpses:
                unsafe_reasons.append(f"{item.name}: corpse (disabled)")
                continue
            # Even if corpses allowed, check for known dangerous ones
            if nh.is_dangerous_corpse(name):
                unsafe_reasons.append(f"{item.name}: dangerous corpse")
                continue

        # Skip tins (require can opener, take time)
        if "tin" in name:
            # Tins are safe but slow - deprioritize
            continue

        # Skip known dangerous foods
        dangerous_foods = [
            "egg",  # Could be cockatrice egg
        ]
        if any(d in name for d in dangerous_foods):
            # Check if we know it's safe
            if "cockatrice" in name:
                unsafe_reasons.append(f"{item.name}: cockatrice egg")
                continue

        # Item model doesn't track rottenness, so we skip that check
        safe_food.append(item)

    if not safe_food:
        return SkillResult.stopped(
            "unsafe_food_only",
            success=False,
            actions=0,
            turns=0,
            hunger=current_hunger,
            unsafe_items=unsafe_reasons[:5],  # Limit to first 5
        )

    # Prioritize food (prefer identified, non-corpse items)
    def food_priority(item):
        name = item.name.lower() if item.name else ""
        score = 0
        # Prefer rations and common safe foods
        if "ration" in name:
            score += 10
        if "food ration" in name:
            score += 5
        if "lembas" in name or "cram" in name:
            score += 8
        if "apple" in name or "orange" in name or "pear" in name:
            score += 3
        if "corpse" in name:
            score -= 5
        # Prefer identified items
        if item.identified:
            score += 2
        return score

    safe_food.sort(key=food_priority, reverse=True)
    chosen_food = safe_food[0]

    # Eat the food
    turns_start = nh.turn
    result = nh.eat(chosen_food.slot)

    # Check for issues
    message = nh.get_message().lower()

    # Check if eating was interrupted or failed
    if "can't" in message or "don't" in message:
        return SkillResult.stopped(
            "eat_failed",
            success=False,
            actions=1,
            turns=nh.turn - turns_start,
            item=chosen_food.name,
            message=message,
        )

    # Successful eating
    return SkillResult.stopped(
        "ate_food",
        success=True,
        actions=1,
        turns=nh.turn - turns_start,
        item=chosen_food.name,
        previous_hunger=current_hunger,
    )
