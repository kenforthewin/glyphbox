"""
Basic melee combat skill.

Fights adjacent monsters using melee attacks, with safety checks
for dangerous monsters and low HP situations.
"""


async def melee_fight(
    nh,
    hp_flee_threshold: float = 0.2,
    max_rounds: int = 20,
    **params,
):
    """
    Fight an adjacent monster using melee attacks.

    Attacks the nearest adjacent hostile monster until it's dead,
    the player's HP is too low, or too many rounds pass.

    Category: combat
    Stops when: target_dead, low_hp, no_target, dangerous_monster, max_rounds

    Args:
        nh: NetHackAPI instance
        hp_flee_threshold: HP fraction below which to flee (0.0-1.0)
        max_rounds: Maximum combat rounds before stopping

    Returns:
        SkillResult with combat outcome
    """
    actions_taken = 0
    turns_start = nh.turn
    kills = 0

    for round in range(max_rounds):
        # Check game over
        if nh.is_done:
            return SkillResult.stopped(
                "game_over",
                success=False,
                actions=actions_taken,
                turns=nh.turn - turns_start,
                kills=kills,
            )

        # Check HP threshold
        stats = nh.get_stats()
        hp_fraction = stats.hp / stats.max_hp if stats.max_hp > 0 else 0
        if hp_fraction < hp_flee_threshold:
            return SkillResult.stopped(
                "low_hp",
                success=False,
                actions=actions_taken,
                turns=nh.turn - turns_start,
                hp=stats.hp,
                max_hp=stats.max_hp,
                kills=kills,
            )

        # Find adjacent monsters
        adjacent = nh.get_adjacent_monsters()
        hostile = [m for m in adjacent if m.is_hostile]

        if not hostile:
            # No more adjacent enemies
            if kills > 0:
                return SkillResult.stopped(
                    "target_dead",
                    success=True,
                    actions=actions_taken,
                    turns=nh.turn - turns_start,
                    kills=kills,
                )
            else:
                # Check if there are visible but non-adjacent monsters
                visible = nh.get_visible_monsters()
                hostile_visible = [m for m in visible if m.is_hostile]
                if hostile_visible:
                    # Find the closest one
                    player_pos = stats.position
                    closest = min(hostile_visible, key=lambda m: player_pos.chebyshev_distance(m.position))
                    dist = player_pos.chebyshev_distance(closest.position)

                    # Calculate direction to monster
                    direction = player_pos.direction_to(closest.position)
                    dir_to_cmd = {
                        Direction.N: "move_north", Direction.S: "move_south",
                        Direction.E: "move_east", Direction.W: "move_west",
                        Direction.NE: "move_ne", Direction.NW: "move_nw",
                        Direction.SE: "move_se", Direction.SW: "move_sw",
                    }
                    move_cmd = dir_to_cmd.get(direction, "move toward it")

                    return SkillResult.stopped(
                        "no_adjacent_target",
                        success=False,
                        actions=actions_taken,
                        turns=nh.turn - turns_start,
                        hint=f"Monster '{closest.name}' is {dist} tiles away. Use direct_action with command '{move_cmd}' to approach.",
                        nearest_monster=closest.name,
                        nearest_distance=dist,
                        nearest_direction=move_cmd,
                        nearest_position={"x": closest.position.x, "y": closest.position.y},
                    )
                return SkillResult.stopped(
                    "no_target",
                    success=False,
                    actions=actions_taken,
                    turns=nh.turn - turns_start,
                    hint="No hostile monsters visible",
                )

        # Select target (closest, or most dangerous)
        target = hostile[0]

        # Check for dangerous monsters
        if nh.is_dangerous_melee(target.name):
            return SkillResult.stopped(
                "dangerous_monster",
                success=False,
                actions=actions_taken,
                turns=nh.turn - turns_start,
                monster=target.name,
                kills=kills,
                reason=f"{target.name} is dangerous to fight in melee",
            )

        # Get direction to target
        player_pos = stats.position
        direction = player_pos.direction_to(target.position)

        if direction is None or direction == Direction.SELF:
            # Shouldn't happen with adjacent monster
            continue

        # Attack!
        before_monsters = len(hostile)
        result = nh.attack(direction)
        actions_taken += 1

        # Check if we killed something
        new_adjacent = nh.get_adjacent_monsters()
        new_hostile = [m for m in new_adjacent if m.is_hostile]
        if len(new_hostile) < before_monsters:
            kills += 1

        # Check messages for death confirmation
        message = nh.get_message().lower()
        if "destroy" in message or "kill" in message or "defeat" in message:
            kills = max(kills, 1)  # At least one kill

    # Max rounds reached
    return SkillResult.stopped(
        "max_rounds",
        success=kills > 0,
        actions=actions_taken,
        turns=nh.turn - turns_start,
        kills=kills,
        rounds=max_rounds,
    )
