"""
Move to a specific location skill.

Pathfinds and moves to a target position, stopping when threats are detected.
"""


async def move_to(nh, target_x: int, target_y: int, max_steps: int = 100, **params):
    """
    Move toward a specific target position.

    Pathfinds to the target and moves step by step, stopping if:
    - Reached the target
    - Adjacent hostile monster detected
    - Nearby hostile monster spotted (within 3 tiles)
    - HP falls below 30%
    - Path becomes blocked
    - Max steps reached

    Category: exploration
    Stops when: reached_target, monster_adjacent, monster_spotted, low_hp, path_blocked, max_steps

    Args:
        nh: NetHackAPI instance
        target_x: Target X coordinate
        target_y: Target Y coordinate
        max_steps: Maximum steps before stopping

    Returns:
        SkillResult with movement outcome
    """
    actions_taken = 0
    turns_start = nh.turn
    target = Position(target_x, target_y)
    hp_threshold = 0.3

    for step in range(max_steps):
        # Check if game is over
        if nh.is_done:
            return SkillResult.stopped(
                "game_over",
                success=False,
                actions=actions_taken,
                turns=nh.turn - turns_start,
            )

        # Get current position
        stats = nh.get_stats()
        current_pos = stats.position

        # Check if we reached the target
        if current_pos.x == target_x and current_pos.y == target_y:
            return SkillResult.stopped(
                "reached_target",
                success=True,
                actions=actions_taken,
                turns=nh.turn - turns_start,
            )

        # Check for adjacent hostile monsters
        adjacent_monsters = nh.get_adjacent_monsters()
        if adjacent_monsters:
            hostile = [m for m in adjacent_monsters if m.is_hostile]
            if hostile:
                return SkillResult.stopped(
                    "monster_adjacent",
                    success=False,
                    actions=actions_taken,
                    turns=nh.turn - turns_start,
                    monster=hostile[0].name,
                    monster_pos={"x": hostile[0].position.x, "y": hostile[0].position.y},
                )

        # Check HP
        if stats.hp / stats.max_hp < hp_threshold:
            return SkillResult.stopped(
                "low_hp",
                success=False,
                actions=actions_taken,
                turns=nh.turn - turns_start,
                hp=stats.hp,
                max_hp=stats.max_hp,
            )

        # Check for nearby hostile monsters (within 3 tiles)
        visible_monsters = nh.get_visible_monsters()
        hostile_visible = [m for m in visible_monsters if m.is_hostile]
        if hostile_visible:
            closest = min(hostile_visible, key=lambda m: current_pos.chebyshev_distance(m.position))
            dist = current_pos.chebyshev_distance(closest.position)
            if dist <= 3:
                return SkillResult.stopped(
                    "monster_spotted",
                    success=False,
                    actions=actions_taken,
                    turns=nh.turn - turns_start,
                    monster=closest.name,
                    distance=dist,
                )

        # Find path to target
        path = nh.find_path(target, avoid_monsters=True)
        if not path:
            # Try without avoiding monsters
            path = nh.find_path(target, avoid_monsters=False)

        if not path:
            return SkillResult.stopped(
                "path_blocked",
                success=False,
                actions=actions_taken,
                turns=nh.turn - turns_start,
                hint=f"Cannot find path from ({current_pos.x}, {current_pos.y}) to ({target_x}, {target_y})",
            )

        # Take one step along the path
        direction = path[0]
        result = nh.move(direction)

        if result.turn_elapsed:
            actions_taken += 1

        if not result.success:
            # Movement blocked - try opening a door
            open_result = nh.open_door(direction)
            if open_result.turn_elapsed:
                actions_taken += 1

            # Try moving again
            result = nh.move(direction)
            if result.turn_elapsed:
                actions_taken += 1

            if not result.success:
                return SkillResult.stopped(
                    "path_blocked",
                    success=False,
                    actions=actions_taken,
                    turns=nh.turn - turns_start,
                    hint=f"Movement blocked at ({current_pos.x}, {current_pos.y})",
                )

    # Reached max steps
    final_pos = nh.get_position()
    return SkillResult.stopped(
        "max_steps",
        success=False,
        actions=actions_taken,
        turns=nh.turn - turns_start,
        final_position={"x": final_pos.x, "y": final_pos.y},
        distance_remaining=final_pos.chebyshev_distance(target),
    )
