"""
Look around skill - gives the agent full visual context of surroundings.

This skill should be used sparingly when the agent needs spatial awareness,
NOT on every turn. Use it when:
- You don't know where a monster is
- You need to find stairs, doors, or items
- You're disoriented after teleportation
- You need to plan a path or escape route
"""

from src.api.models import Direction, SkillResult


async def look_around(nh, **params):
    """
    Get a complete view of the current surroundings.

    Returns the ASCII game screen along with parsed information about
    visible monsters, items, and terrain features with their positions
    and directions relative to the player.

    Category: exploration
    Stops when: immediately (this is an information-gathering skill)

    This skill is expensive in terms of context - use it sparingly!
    Only call this when you genuinely need spatial awareness, such as:
    - Finding where a monster is located
    - Locating stairs, doors, or important features
    - Planning movement or escape routes
    - After teleportation or confusion

    Returns:
        SkillResult with screen and parsed environment data
    """
    # Get the raw screen
    screen = nh.get_screen()

    # Get player position
    stats = nh.get_stats()
    player_pos = stats.position

    # Get visible monsters with directions
    monsters = nh.get_visible_monsters()
    monster_info = []
    for m in monsters:
        dist = player_pos.chebyshev_distance(m.position)
        direction = player_pos.direction_to(m.position)

        # Convert direction to readable format
        dir_names = {
            Direction.N: "north", Direction.S: "south",
            Direction.E: "east", Direction.W: "west",
            Direction.NE: "northeast", Direction.NW: "northwest",
            Direction.SE: "southeast", Direction.SW: "southwest",
            Direction.SELF: "here",
        }
        dir_name = dir_names.get(direction, "unknown")

        # Also provide the move command
        dir_to_cmd = {
            Direction.N: "move_north", Direction.S: "move_south",
            Direction.E: "move_east", Direction.W: "move_west",
            Direction.NE: "move_ne", Direction.NW: "move_nw",
            Direction.SE: "move_se", Direction.SW: "move_sw",
        }
        move_cmd = dir_to_cmd.get(direction, None)

        monster_info.append({
            "name": m.name,
            "symbol": m.glyph if hasattr(m, 'glyph') else '?',
            "distance": dist,
            "direction": dir_name,
            "move_command": move_cmd,
            "is_hostile": m.is_hostile,
            "is_adjacent": dist == 1,
            "position": {"x": m.position.x, "y": m.position.y},
        })

    # Sort by distance
    monster_info.sort(key=lambda m: m["distance"])

    # Get items at current position
    items_here = nh.get_items_here()
    item_info = []
    if items_here:
        for item in items_here:
            item_info.append({
                "name": item.name if hasattr(item, 'name') else str(item),
            })

    # Get the current message
    message = nh.get_message()

    # Build a text summary for the LLM
    summary_lines = []
    summary_lines.append(f"=== CURRENT VIEW (Turn {stats.turn}) ===")
    summary_lines.append(f"Position: ({player_pos.x}, {player_pos.y}) on DL:{stats.dungeon_level}")
    summary_lines.append(f"HP: {stats.hp}/{stats.max_hp}")
    summary_lines.append("")

    if message:
        summary_lines.append(f"Message: {message}")
        summary_lines.append("")

    summary_lines.append("--- VISIBLE MONSTERS ---")
    if monster_info:
        for m in monster_info:
            hostile = "HOSTILE" if m["is_hostile"] else "peaceful"
            adjacent = " [ADJACENT]" if m["is_adjacent"] else ""
            cmd_hint = f" (use: {m['move_command']})" if m["move_command"] and not m["is_adjacent"] else ""
            summary_lines.append(
                f"  {m['name']}: {m['distance']} tiles {m['direction']}{adjacent} [{hostile}]{cmd_hint}"
            )
    else:
        summary_lines.append("  No monsters visible")
    summary_lines.append("")

    summary_lines.append("--- ITEMS HERE ---")
    if item_info:
        for item in item_info:
            summary_lines.append(f"  {item['name']}")
    else:
        summary_lines.append("  Nothing here")
    summary_lines.append("")

    summary_lines.append("--- GAME SCREEN ---")
    summary_lines.append(screen)

    text_summary = "\n".join(summary_lines)

    return SkillResult.stopped(
        "looked",
        success=True,
        actions=0,
        turns=0,
        hint=text_summary,
        screen=screen,
        monsters=monster_info,
        items_here=item_info,
        message=message,
        player_position={"x": player_pos.x, "y": player_pos.y},
    )
