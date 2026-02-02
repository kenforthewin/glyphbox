"""
Prompt system for the NetHack agent.

Manages prompt templates and context formatting for LLM interactions.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _deduplicate_with_counts(items: list[str]) -> list[tuple[str, int]]:
    """
    Deduplicate a list while preserving order and counting occurrences.

    Returns list of (item, count) tuples in order of first appearance.
    Empty strings are filtered out.
    """
    from collections import OrderedDict
    counts: OrderedDict[str, int] = OrderedDict()
    for item in items:
        if item:  # Skip empty strings
            counts[item] = counts.get(item, 0) + 1
    return list(counts.items())


class PromptManager:
    """
    Manages prompt templates for the agent.

    Provides methods to format prompts with game context.

    Example usage:
        prompts = PromptManager(skills_enabled=False)

        # Format a decision prompt
        prompt = prompts.format_decision_prompt(
            game_state=state_summary,
            available_skills=skill_list,
            recent_events=events,
        )
    """

    def __init__(self, skills_enabled: bool = False, local_map_mode: bool = False):
        """
        Initialize the prompt manager.

        Args:
            skills_enabled: Whether skill tools are enabled
            local_map_mode: Whether agent sees local map (True) or full map (False)
        """
        self.skills_enabled = skills_enabled
        self.local_map_mode = local_map_mode
        self._templates: dict[str, str] = {}
        self._load_default_templates()

    def _load_default_templates(self) -> None:
        """Load default embedded templates."""
        # Build system prompt with appropriate tools section
        # Use replace() instead of format() to avoid issues with { } in code examples
        if self.local_map_mode:
            tools_section = TOOLS_SECTION_LOCAL_SKILLS if self.skills_enabled else TOOLS_SECTION_LOCAL_NO_SKILLS
        else:
            tools_section = TOOLS_SECTION_FULL_SKILLS if self.skills_enabled else TOOLS_SECTION_FULL_NO_SKILLS
        system_prompt = SYSTEM_PROMPT_BASE.replace("{tools_section}", tools_section)

        self._templates = {
            "system": system_prompt,
            "decision": DECISION_PROMPT,
            "past_turn": PAST_TURN_PROMPT,
            "historical_turn": HISTORICAL_TURN_PROMPT,
            "skill_creation": SKILL_CREATION_PROMPT,
            "analysis": ANALYSIS_PROMPT,
        }

    def get_template(self, name: str) -> Optional[str]:
        """Get a template by name."""
        return self._templates.get(name)

    def format_template(self, name: str, **kwargs) -> str:
        """
        Format a template with provided values.

        Args:
            name: Template name
            **kwargs: Values to substitute

        Returns:
            Formatted prompt string
        """
        template = self._templates.get(name, "")
        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Missing template variable: {e}")
            return template

    def get_system_prompt(self) -> str:
        """Get the system prompt for the agent."""
        return self._templates.get("system", "")

    def format_last_result(self, last_result: dict) -> str:
        """
        Format a last_result dict into display text.

        Args:
            last_result: Result dict from tool execution

        Returns:
            Formatted result text string
        """
        result_lines = []

        # Show error if any
        if last_result.get("error"):
            result_lines.append(f"error: {last_result['error']}")

        # Show game messages (raw feedback from the game)
        # Deduplicate repeated messages with counts
        messages = last_result.get("messages", [])
        if messages:
            result_lines.append("game_messages:")
            deduped = _deduplicate_with_counts(messages)
            for msg, count in deduped:
                if count > 1:
                    result_lines.append(f"  - {msg} (x{count})")
                else:
                    result_lines.append(f"  - {msg}")

        # Show autoexplore result if autoexplore was called
        autoexplore = last_result.get("autoexplore_result")
        if autoexplore:
            stop_reason = autoexplore.get("stop_reason", "unknown")
            steps = autoexplore.get("steps_taken", 0)
            message = autoexplore.get("message", "")
            # Include message for blocked/informative stop reasons
            if message and stop_reason in ("blocked", "fully_explored", "hostile", "attacked"):
                result_lines.append(f"autoexplore: stopped ({stop_reason}) after {steps} steps - {message}")
            else:
                result_lines.append(f"autoexplore: stopped ({stop_reason}) after {steps} steps")

        # Show ALL API calls with success/failure status
        # This ensures the agent always knows what actions were taken
        api_calls = last_result.get("api_calls", [])
        # Fall back to failed_api_calls for backward compatibility
        if not api_calls:
            api_calls = last_result.get("failed_api_calls", [])

        if api_calls:
            result_lines.append("actions:")
            # Convert to strings for deduplication
            call_strs = []
            for c in api_calls:
                method = c.get('method', 'unknown')
                args = c.get('args', '')
                success = c.get('success', True)
                error = c.get('error', '')

                # Format: method(args) ✓ or method(args) ✗ error
                if args:
                    call_str = f"{method}({args})"
                else:
                    call_str = f"{method}()"

                if success:
                    call_strs.append(f"{call_str} ok")
                else:
                    call_strs.append(f"{call_str} FAILED: {error}")

            deduped = _deduplicate_with_counts(call_strs)
            for call_msg, count in deduped:
                if count > 1:
                    result_lines.append(f"  - {call_msg} (x{count})")
                else:
                    result_lines.append(f"  - {call_msg}")

        # Show output if present
        if last_result.get("output"):
            result_lines.append(f"output: {last_result['output']}")

        # Show full map if view_full_map was called
        if last_result.get("full_map"):
            result_lines.append("=== FULL DUNGEON MAP ===")
            result_lines.append(last_result["full_map"])
            result_lines.append("=== END FULL MAP ===")

        return "\n".join(result_lines) if result_lines else "None"

    def format_past_turn(self, last_result_text: str) -> str:
        """
        Format a compressed past-turn message (no game screen).

        Args:
            last_result_text: Pre-formatted result text

        Returns:
            Formatted past-turn prompt
        """
        return self.format_template("past_turn", last_result=last_result_text)

    def format_historical_turn(self, game_screen: str, last_result_text: str, turns_ago: int) -> str:
        """
        Format a historical turn message (includes game screen but no stale metadata).

        Args:
            game_screen: The game screen from that turn
            last_result_text: Pre-formatted result text
            turns_ago: How many turns ago this was

        Returns:
            Formatted historical-turn prompt
        """
        return self.format_template(
            "historical_turn",
            game_screen=game_screen,
            last_result=last_result_text,
            turns_ago=turns_ago,
        )

    def format_decision_prompt(
        self,
        saved_skills: list[str],
        last_result_text: Optional[str] = None,
        game_screen: Optional[str] = None,
        current_position: Optional[Any] = None,
        hostile_monsters: Optional[list[Any]] = None,
        adjacent_tiles: Optional[dict[str, str]] = None,
        inventory: Optional[list[Any]] = None,
        items_on_map: Optional[list[Any]] = None,
        stairs_positions: Optional[tuple[Any, Any]] = None,
        altars: Optional[list[Any]] = None,
        reminders: Optional[list[str]] = None,
        notes: Optional[list[tuple[int, str]]] = None,
        dungeon_overview: Optional[str] = None,
    ) -> str:
        """
        Format a decision prompt with current game context.

        Args:
            saved_skills: List of skill names the agent has written
            last_result_text: Pre-formatted result text from format_last_result()
            game_screen: Full game screen (ASCII art showing what human would see)
            current_position: Current player Position (x, y)
            hostile_monsters: List of hostile Monster objects
            adjacent_tiles: Dict mapping direction names to tile descriptions
            inventory: List of Item objects in player's inventory
            items_on_map: List of Item objects visible on the map (with positions)
            stairs_positions: Tuple of (stairs_up_position, stairs_down_position)
            reminders: List of reminder messages that just fired
            notes: List of (note_id, message) tuples for active notes

        Returns:
            Formatted decision prompt
        """

        # Format saved skills (only when skills enabled)
        skills_text = ""
        if self.skills_enabled:
            if saved_skills:
                skills_text = "\n".join(f"- {name}" for name in saved_skills)
            else:
                skills_text = "None (use write_skill to create skills)"

        result_text = last_result_text if last_result_text else "None"

        # Format hostile monsters with relative directions only (no coordinates)
        # Include the display character so agent knows what to look for on map
        monsters_text = ""
        if hostile_monsters and current_position:
            monster_lines = []
            for m in hostile_monsters:
                direction = current_position.direction_to(m.position)
                distance = current_position.distance_to(m.position)
                dir_name = direction.name if direction else "?"
                # Include char so agent knows what to look for on map (e.g. fox='d', kitten='f')
                if distance == 1:
                    monster_lines.append(f"  - {m.name} '{m.char}' [{dir_name}, adjacent]")
                else:
                    monster_lines.append(f"  - {m.name} '{m.char}' [{dir_name}, {distance} tiles]")
            if monster_lines:
                monsters_text = "Hostile Monsters:\n" + "\n".join(monster_lines)

        # Build skills section (empty string when disabled)
        skills_section = ""
        if self.skills_enabled:
            skills_section = f"\nYour Saved Skills:\n{skills_text}\n"

        # Format position for display
        position_text = ""
        if current_position:
            position_text = f"Your position: ({current_position.x}, {current_position.y})"

        # Format adjacent tiles for display
        adjacent_text = ""
        if adjacent_tiles:
            adj_lines = ["Adjacent tiles:"]
            # Show in logical order: N, NE, E, SE, S, SW, W, NW
            direction_order = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
            for direction in direction_order:
                if direction in adjacent_tiles:
                    adj_lines.append(f"  {direction}: {adjacent_tiles[direction]}")
            adjacent_text = "\n".join(adj_lines)

        # Format inventory
        inventory_text = ""
        if inventory:
            inv_lines = ["Inventory:"]
            for item in inventory:
                if item.quantity > 1:
                    inv_lines.append(f"  {item.slot}: {item.quantity} {item.name}")
                else:
                    inv_lines.append(f"  {item.slot}: {item.name}")
            inventory_text = "\n".join(inv_lines)

        # Format items on map (visible items with coordinates)
        items_on_map_text = ""
        if items_on_map:
            item_lines = ["Items on map:"]
            for item in items_on_map:
                item_lines.append(f"  - {item.name} at ({item.position.x}, {item.position.y})")
            items_on_map_text = "\n".join(item_lines)

        # Format stairs positions (critical for navigation)
        stairs_text = ""
        if stairs_positions and len(stairs_positions) == 2:
            stairs_up, stairs_down = stairs_positions
            stairs_lines = ["Stairs:"]
            if stairs_up:
                stairs_lines.append(f"  - Stairs up (<) at ({stairs_up.x}, {stairs_up.y})")
            if stairs_down:
                stairs_lines.append(f"  - Stairs down (>) at ({stairs_down.x}, {stairs_down.y})")
            if len(stairs_lines) > 1:  # Only show if we found stairs
                stairs_text = "\n".join(stairs_lines)

        # Format altars
        altars_text = ""
        if altars:
            altar_lines = ["Altars:"]
            for pos in altars:
                altar_lines.append(f"  - Altar (_) at ({pos.x}, {pos.y})")
            altars_text = "\n".join(altar_lines)

        # Format reminders (one-time alerts that just fired)
        reminders_text = ""
        if reminders:
            reminder_lines = ["REMINDERS (just triggered):"]
            for r in reminders:
                reminder_lines.append(f"  - {r}")
            reminders_text = "\n".join(reminder_lines)

        # Format notes with IDs (for removal via remove_note())
        notes_text = ""
        if notes:
            note_lines = ["Notes (use nh.remove_note(id) to remove):"]
            for note_id, msg in notes:
                note_lines.append(f"  {note_id}. {msg}")
            notes_text = "\n".join(note_lines)

        # Format dungeon overview
        overview_text = ""
        if dungeon_overview:
            overview_text = f"Dungeon Overview:\n{dungeon_overview}"

        kwargs = {
            "game_screen": game_screen or "Screen not available",
            "position": position_text,
            "adjacent_tiles": adjacent_text,
            "last_result": result_text,
            "hostile_monsters": monsters_text,
            "inventory": inventory_text,
            "items_on_map": items_on_map_text,
            "stairs": stairs_text,
            "altars": altars_text,
            "skills_section": skills_section,
            "reminders": reminders_text,
            "notes": notes_text,
            "dungeon_overview": overview_text,
        }

        return self.format_template("decision", **kwargs)

    def format_skill_creation_prompt(
        self,
        situation: str,
        game_state: dict,
        existing_skills: list[str],
        failed_attempts: Optional[list[str]] = None,
    ) -> str:
        """
        Format a prompt for skill creation.

        Args:
            situation: Description of the situation needing a new skill
            game_state: Current game state
            existing_skills: List of existing skill names
            failed_attempts: Previous failed skill attempts

        Returns:
            Formatted skill creation prompt
        """
        state_text = self._format_game_state(game_state)
        skills_list = ", ".join(existing_skills) if existing_skills else "None"
        failed_text = "\n".join(failed_attempts) if failed_attempts else "None"

        return self.format_template(
            "skill_creation",
            situation=situation,
            game_state=state_text,
            existing_skills=skills_list,
            failed_attempts=failed_text,
        )

    def format_analysis_prompt(
        self,
        game_state: dict,
        question: str,
    ) -> str:
        """
        Format an analysis prompt for the agent.

        Args:
            game_state: Current game state
            question: Specific question to analyze

        Returns:
            Formatted analysis prompt
        """
        state_text = self._format_game_state(game_state)
        return self.format_template(
            "analysis",
            game_state=state_text,
            question=question,
        )

    def _format_game_state(self, state: dict) -> str:
        """Format game state dictionary into readable text.

        Note: HP, Turn, Dungeon Level, XP, Stats are already visible in the
        screen's status bar, so we only include info NOT on screen.
        """
        lines = []


        # Hunger (only shows on screen when hungry/weak/fainting)
        if "hunger_state" in state:
            lines.append(f"Hunger: {state['hunger_state']}")

        # Combat status indicator
        if state.get("in_combat"):
            lines.append("Status: IN COMBAT")
        elif state.get("hp_trend") == "critical":
            lines.append("Status: CRITICAL HP")

        # Hostile monsters (locations visible on map)
        if "hostile_monster_details" in state and state["hostile_monster_details"]:
            lines.append("Hostile Monsters:")
            for m in state["hostile_monster_details"]:
                lines.append(f"  - {m}")

        # Doors summary
        if "doors" in state:
            lines.append(f"Doors: {state['doors']}")

        # Stairs (locations visible on map as < or >)
        if "stairs_down" in state:
            lines.append(f"Stairs Down: {state['stairs_down']}")
        if "stairs_up" in state:
            lines.append(f"Stairs Up: {state['stairs_up']}")

        # Items at current position
        if "items_here" in state and state["items_here"] > 0:
            lines.append(f"Items Here: {state['items_here']}")

        return "\n".join(lines) if lines else "No additional context"

    def _format_skills(self, skills: list[dict]) -> str:
        """Format skills list into readable text."""
        if not skills:
            return "No skills available"

        lines = []
        for skill in skills[:15]:  # Limit to 15 skills
            name = skill.get("name", "unknown")
            category = skill.get("category", "")
            desc = skill.get("description", "")[:60]
            stops = skill.get("stops_when", [])
            stops_text = ", ".join(stops[:3]) if stops else "various"

            lines.append(f"- {name} ({category}): {desc}")
            lines.append(f"  Stops when: {stops_text}")

        if len(skills) > 15:
            lines.append(f"  ... and {len(skills) - 15} more skills")

        return "\n".join(lines)

    def _format_events(self, events: list[dict]) -> str:
        """Format events list into readable text."""
        if not events:
            return "No recent events"

        lines = []
        for event in events[-10:]:  # Last 10 events
            turn = event.get("turn", "?")
            etype = event.get("type", event.get("event_type", "event"))
            desc = event.get("desc", event.get("description", ""))
            lines.append(f"[Turn {turn}] {etype}: {desc}")

        return "\n".join(lines)


# ============================================================================
# Default Prompt Templates
# ============================================================================

# Tools section variants based on local_map_mode and skills_enabled
# When local_map_mode=True: agent sees cropped view, needs view_full_map tool
# When local_map_mode=False: agent sees full map each turn, no need for view_full_map

TOOLS_SECTION_LOCAL_SKILLS = """You have 4 tools available:
- **execute_code** - Run Python code to interact with the game. Batch multiple operations.
- **view_full_map** - See the ENTIRE dungeon level (21 rows). Use sparingly - only when local view is insufficient for planning exploration or finding distant features.
- **write_skill** - Save reusable code as a skill. Code must be: async def skill_name(nh, **params):
- **invoke_skill** - Run a previously saved skill."""

TOOLS_SECTION_LOCAL_NO_SKILLS = """You have 2 tools available:
- **execute_code** - Run Python code to interact with the game. Batch multiple operations.
- **view_full_map** - See the ENTIRE dungeon level (21 rows). Use sparingly - only when local view is insufficient for planning exploration or finding distant features."""

TOOLS_SECTION_FULL_SKILLS = """You have 3 tools available:
- **execute_code** - Run Python code to interact with the game. Batch multiple operations.
- **write_skill** - Save reusable code as a skill. Code must be: async def skill_name(nh, **params):
- **invoke_skill** - Run a previously saved skill."""

TOOLS_SECTION_FULL_NO_SKILLS = """You have 1 tool available:
- **execute_code** - Run Python code to interact with the game. Batch multiple operations."""

# Base system prompt with {tools_section} placeholder
SYSTEM_PROMPT_BASE = """You are an expert NetHack player. You interact with the game using Python code executed in a sandbox.

## Game View

The full game screen (what a human player would see) is provided at the start of each turn.
This includes the dungeon map, messages, and status bar with your stats.

## Available Tools

{tools_section}

## API Reference

Your code has access to `nh` (NetHackAPI) and these pre-loaded types:
- Direction: N, S, E, W, NE, NW, SE, SW
- Position: x, y coordinates with .distance_to(), .direction_to() methods
Do NOT import anything. All types are pre-loaded and imports will fail.

**nh.autoexplore()** - Explore the level automatically. Use for any exploration!
  result = nh.autoexplore()
  # Stops for: "hostile" (nearby), "low_hp", "hungry", "fully_explored", "blocked"
  # Does NOT stop for items, stairs, features - explores until done or danger
  if result.stop_reason == "hostile": nh.attack(direction)
  # ignore_monsters=True: ignore nearby enemies, only stop if attacked (HP drops)
  result = nh.autoexplore(ignore_monsters=True)
  if result.stop_reason == "attacked": ...  # took damage during exploration

**nh.move_to(Position)** - Pathfind to a specific coordinate
  nh.move_to(Position(42, 12))  # Walk to that spot

### Actions (all return ActionResult)

ActionResult has: .success (bool), .messages (list[str]), .turn_elapsed (bool)
Check .messages for feedback like "You hit the goblin!" or "It's a wall."

**Movement:**
nh.move(Direction, count=1)  # Move in direction (count=5 moves up to 5 tiles, auto-stops at walls/monsters)
nh.run(Direction)            # Run until wall/intersection/monster - fast corridor travel
nh.go_up()                   # Climb stairs up (<) - use AFTER travel_to('<')
nh.go_down()                 # Descend stairs (>) - use AFTER travel_to('>')

**Combat:**
nh.attack(Direction)         # Attack in direction
nh.kick(Direction)           # Kick (doors, monsters)
nh.fire(Direction)           # Fire wielded ranged weapon
nh.throw('a', Direction)     # Throw item by inventory letter

**Items:**
nh.get_inventory()           # List[Item] - your items (have .slot letter)
nh.get_items_here()          # List[Item] - items on ground at your position
nh.get_food()                # List[Item] - food in inventory
Item has: .name, .slot (inventory letter), .quantity

**Item Actions:**
nh.pickup()                  # Pick up all items at current position
nh.drop('a')                 # Drop item by inventory letter
nh.eat('a')                  # Eat food from inventory
nh.eat()                     # Eat from ground (prompts for corpse)
nh.quaff('a')                # Drink potion
nh.read('a')                 # Read scroll/spellbook
nh.wield('a')                # Wield weapon
nh.wear('a')                 # Wear armor
nh.take_off('a')             # Remove armor
nh.zap('a', Direction)       # Zap wand
nh.apply('a')                # Use tool (pickaxe, key, horn)

**Doors:**
nh.open_door(Direction)      # Open door
nh.close_door(Direction)     # Close door

**Magic & Special:**
nh.cast_spell('a', Direction) # Cast memorized spell
nh.pay()                     # Pay shopkeeper for picked-up items
nh.pray()                    # Pray to deity (has cooldown)
nh.engrave("Elbereth")       # Write on floor
nh.look()                    # Look at current square

**Utility (count uses NetHack's repeat prefix - auto-stops on monster/danger):**
nh.wait(count=1)             # Wait/rest turns (count=10 to rest safely)
nh.search(count=1)           # Search for secrets (count=20 to find hidden doors)
nh.add_reminder(turns, msg)  # One-time reminder after N turns
nh.add_note(turns, msg)      # Persistent note for N turns (0 = permanent)
nh.remove_note(note_id)      # Remove a note by ID

### State Queries (don't consume turns)

**Properties (use these for conditionals in loops):**
nh.hp                        # int - current hit points
nh.max_hp                    # int - maximum hit points
nh.is_hungry                 # bool - True if Hungry/Weak/Fainting
nh.is_weak                   # bool - True if Weak/Fainting (critical!)
nh.has_adjacent_hostile      # bool - True if hostile monster adjacent
nh.turns_since_last_prayer   # int - turns since last prayer (~500 needed)
nh.dungeon_level             # int - current dungeon level
nh.position                  # Position - current (x, y)
nh.turn                      # int - current game turn
nh.get_adjacent_hostiles()   # list[Monster] - hostiles in adjacent tiles
Monster has: .name, .position, .is_hostile

Example - combat loop:
  for monster in nh.get_adjacent_hostiles():
      direction = nh.position.direction_to(monster.position)
      while nh.hp > 15 and nh.get_adjacent_hostiles():
          nh.attack(direction)

## CRITICAL: Use Count Parameters Instead of Loops

For repeated actions, use the count parameter instead of Python loops.
NetHack's count prefix auto-interrupts if a monster appears or attacks - much safer!

BAD - Python loop won't stop if monster appears:
  for _ in range(10):
      nh.search()

GOOD - uses NetHack's built-in interrupt:
  nh.search(count=20)  # Auto-stops if monster appears

GOOD - single action per turn:
  nh.search()  # Just search once, you'll be called again next turn

The count parameter works for: search(count), wait(count), move(direction, count)

NOTE: HP, position, monsters are ALREADY SHOWN in the game view above.
DO NOT query for them just to print them - use the view you already have!

**Prompt Responses:** When you see "[ynq]" or "[yn]" in a message, game awaits input:
nh.confirm()                 # Send 'y' - accept
nh.deny()                    # Send 'n' - decline
nh.escape()                  # Send ESC - cancel
nh.space()                   # Send space - dismiss --More--

### Query Methods

nh.find_nearest_item()       # Returns TargetResult with .position and .success
nh.find_doors()              # list[(Position, is_open)] - all doors on level
nh.find_altars()             # list[Position] - all altars on level

### NAVIGATION REMINDER

- To reach stairs: `nh.travel_to('>')` then `nh.go_down()`
- To explore: `nh.autoexplore()`
- To reach a position: `nh.move_to(position)`

You must engage in strategic, long-term planning to survive.
- Pick up food if you don't have enough. Even if not hungry, you should plan ahead and have enough food for later.
- Focus on leveling up and getting stronger. Don't just rush headlong into the next level of the dungeon; if you do, you will be too weak and will die.
- Generally speaking, corpses are only safe to eat if you've just killed them. Otherwise they will be rotted and give you food poisoning, resulting in certain death. One exception is Lichen corpses which are always safe to eat. If you are fainting and have no other option, prefer prayer as a last resort.
- If you find yourself on a fully explored level with no staircase down, think critically about where the most likely location of the hidden room may be. Search along the walls and corridors leading to the map position you believe this room is most likely around. Do not continue to use autoexplore in this scenario.
- NetHack is a permadeath game. If you fail, you will not have a chance to recover. You MUST think critically and plan ahead.
"""

DECISION_PROMPT = """=== CURRENT GAME VIEW ===
{position}
{game_screen}
{adjacent_tiles}
{hostile_monsters}
{inventory}
{items_on_map}
{stairs}
{altars}
{reminders}
{notes}
{dungeon_overview}
{skills_section}
Last Result:
{last_result}

What action will you take?"""

PAST_TURN_PROMPT = """[Previous turn]
Last Result:
{last_result}"""

HISTORICAL_TURN_PROMPT = """=== HISTORICAL GAME VIEW ({turns_ago} turn(s) ago) ===
{game_screen}

Last Result:
{last_result}"""

SKILL_CREATION_PROMPT = """You need to create a new skill to handle this situation:

Situation: {situation}

Current Game State:
{game_state}

Existing Skills: {existing_skills}

Previous Failed Attempts:
{failed_attempts}

Create a new skill that handles this situation. The skill must:
1. Be an async function with signature: async def skill_name(nh, **params)
2. Return SkillResult.stopped(reason, success=bool, ...) when done
3. Check nh.is_done to detect game over
4. Include safety checks (HP threshold, turn limits)
5. Have a clear stopping condition

Available API methods on `nh`:
- State: get_stats(), get_position(), get_message(), get_visible_monsters(), get_adjacent_hostiles(), get_inventory(), turn, is_done
- Movement: move(direction, count=1), go_up(), go_down()
- Combat: attack(direction)
- Items: pickup(), eat(slot), quaff(slot), wield(slot), wear(slot)
- Utility: wait(count=1), search(count=1), open_door(direction)
- Navigation: move_to(target), travel_to(char), autoexplore()
Note: count parameter uses NetHack's repeat prefix - auto-stops on monster/danger

Respond with a JSON decision including the full skill code in the "code" field."""

ANALYSIS_PROMPT = """Current Game State:
{game_state}

Question: {question}

Analyze the situation and provide your assessment. Consider:
- Immediate threats and opportunities
- Resource status (HP, food, items)
- Strategic options available
- Recommended next steps

Provide a detailed analysis."""

