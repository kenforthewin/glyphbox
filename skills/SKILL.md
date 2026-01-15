# NetHack Agent Skills

This directory contains behavioral skills for the NetHack agent. Skills are Python async functions that interact with the game through the NetHackAPI.

## Skill Structure

Every skill must follow this structure:

```python
async def skill_name(nh, **params):
    """
    Brief description of what this skill does.

    Category: category_name
    Stops when: condition1, condition2, condition3

    Args:
        nh: NetHackAPI instance
        param1: Description of param1
        param2: Description of param2

    Returns:
        SkillResult with execution outcome
    """
    # Implementation
    return SkillResult.stopped(
        "stop_reason",
        success=True,
        actions=actions_taken,
        turns=turns_elapsed,
        # Additional data...
    )
```

### Required Elements

1. **Async function**: All skills are async to allow cooperative execution
2. **First parameter `nh`**: The NetHackAPI instance for game interaction
3. **`**params`**: Accept additional keyword arguments for flexibility
4. **Docstring with metadata**:
   - `Category:` - Skill category (exploration, combat, resource, navigation, interaction, utility, custom)
   - `Stops when:` - Comma-separated list of stop conditions
5. **Return SkillResult**: Always return via `SkillResult.stopped()` with stop reason

## Categories

### exploration
Skills for exploring the dungeon, finding stairs, discovering rooms.
- `cautious_explore` - Explore until danger is encountered

### combat
Skills for fighting monsters in various situations.
- `melee_fight` - Basic adjacent melee combat

### resource
Skills for managing consumables, food, and healing.
- `eat_when_hungry` - Consume food when hunger threshold reached

### navigation
Skills for pathfinding and movement to specific locations.
- (Agent will generate as needed)

### interaction
Skills for interacting with NPCs, shops, and altars.
- (Agent will generate as needed)

### utility
Skills for misc actions like searching, identifying items.
- (Agent will generate as needed)

### custom
Agent-generated skills that don't fit other categories.
- (Dynamically created)

## Available API Methods

Skills have access to these NetHackAPI methods:

### State Queries
- `nh.get_stats()` - Player stats (HP, power, AC, XP, gold, hunger)
- `nh.get_position()` - Player position
- `nh.get_screen()` - Current 24x80 TTY display
- `nh.get_message()` - Current game message
- `nh.get_visible_monsters()` - All monsters in view
- `nh.get_adjacent_monsters()` - Monsters in 8 adjacent tiles
- `nh.get_inventory()` - Current inventory
- `nh.get_items_here()` - Items at player's position
- `nh.turn` - Current game turn
- `nh.is_done` - Whether game is over

### Movement Actions
- `nh.move(direction)` - Move in direction (returns ActionResult)
- `nh.move_to(position)` - Move toward target position
- `nh.go_up()` - Ascend stairs
- `nh.go_down()` - Descend stairs

### Combat Actions
- `nh.attack(direction)` - Attack in direction
- `nh.kick(direction)` - Kick in direction

### Item Actions
- `nh.pickup()` - Pick up items at feet
- `nh.drop(slot)` - Drop item from inventory slot
- `nh.eat(slot)` - Eat item from inventory
- `nh.quaff(slot)` - Drink potion
- `nh.read(slot)` - Read scroll/spellbook
- `nh.zap(slot, direction)` - Zap wand
- `nh.wear(slot)` - Wear armor
- `nh.wield(slot)` - Wield weapon
- `nh.take_off(slot)` - Remove worn item

### Utility Actions
- `nh.wait()` - Wait one turn
- `nh.search()` - Search for secret doors/traps
- `nh.open_door(direction)` - Open door in direction
- `nh.pray()` - Pray to your god

### Pathfinding
- `nh.find_path(target)` - Find path to target position
- `nh.find_unexplored()` - Find nearest unexplored area
- `nh.find_nearest(predicate)` - Find nearest tile matching condition

### Knowledge
- `nh.is_dangerous_melee(monster_name)` - Check if monster is dangerous in melee
- `nh.is_dangerous_corpse(corpse_name)` - Check if corpse is unsafe to eat

## Stop Conditions

Skills should return with clear stop reasons:

### Common Stop Reasons
- `game_over` - Game ended (death or win)
- `low_hp` - HP below threshold
- `max_steps` / `max_rounds` - Iteration limit reached
- `success` - Primary goal achieved

### Combat-Specific
- `target_dead` - Enemy killed
- `no_target` - No valid target found
- `dangerous_monster` - Encountered a too-dangerous foe

### Exploration-Specific
- `monster_adjacent` - Hostile monster next to player
- `monster_spotted` - Hostile monster visible nearby
- `fully_explored` - Level completely explored

### Resource-Specific
- `ate_food` - Successfully ate
- `no_food` - No food available
- `not_hungry` - Don't need to eat

## Writing New Skills

When the agent generates new skills:

1. **Follow the structure** - Use the template above
2. **Be defensive** - Check game state, handle edge cases
3. **Return early** - Stop when conditions are met
4. **Include data** - Return useful info in SkillResult for analysis
5. **Limit loops** - Always have a max iteration count

### Example: Generated Ranged Combat Skill

```python
async def ranged_attack(nh, max_shots: int = 10, **params):
    """
    Attack monsters with ranged weapons or thrown items.

    Category: combat
    Stops when: out_of_ammo, target_dead, target_out_of_range, low_hp, max_shots

    Args:
        nh: NetHackAPI instance
        max_shots: Maximum projectiles to throw
    """
    shots_fired = 0
    turns_start = nh.turn

    for _ in range(max_shots):
        if nh.is_done:
            return SkillResult.stopped("game_over", success=False, shots=shots_fired)

        stats = nh.get_stats()
        if stats.hp / stats.max_hp < 0.2:
            return SkillResult.stopped("low_hp", success=False, shots=shots_fired)

        # Find ranged weapon or projectiles in inventory
        inventory = nh.get_inventory()
        projectiles = [i for i in inventory if i.is_projectile]

        if not projectiles:
            return SkillResult.stopped("out_of_ammo", success=shots_fired > 0, shots=shots_fired)

        # Find visible target
        visible = nh.get_visible_monsters()
        hostile = [m for m in visible if m.is_hostile]

        if not hostile:
            return SkillResult.stopped("target_dead", success=True, shots=shots_fired)

        target = hostile[0]
        direction = stats.position.direction_to(target.position)

        if direction is None:
            return SkillResult.stopped("target_out_of_range", success=False, shots=shots_fired)

        # Fire!
        nh.throw(projectiles[0].slot, direction)
        shots_fired += 1

    return SkillResult.stopped(
        "max_shots",
        success=True,
        shots=shots_fired,
        turns=nh.turn - turns_start,
    )
```

## Security

Skills run in a sandboxed environment with restrictions:

- **No file I/O** - Cannot read/write files
- **No network** - Cannot make network calls
- **No shell** - Cannot execute commands
- **Limited imports** - Only asyncio, typing, math, etc.
- **Time limited** - Skills timeout after configured duration
- **Memory limited** - Container has 256MB RAM limit

The sandbox validates all code before execution to prevent malicious operations.
