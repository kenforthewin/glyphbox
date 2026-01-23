"""
Prompt system for the NetHack agent.

Manages prompt templates and context formatting for LLM interactions.
"""

import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default prompts directory
DEFAULT_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"


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

    Loads templates from files and provides methods to format
    prompts with game context.

    Example usage:
        prompts = PromptManager(skills_enabled=False)
        prompts.load_templates()

        # Format a decision prompt
        prompt = prompts.format_decision_prompt(
            game_state=state_summary,
            available_skills=skill_list,
            recent_events=events,
        )
    """

    def __init__(self, prompts_dir: Optional[str] = None, skills_enabled: bool = False):
        """
        Initialize the prompt manager.

        Args:
            prompts_dir: Directory containing prompt templates
            skills_enabled: Whether skill tools are enabled
        """
        self.prompts_dir = Path(prompts_dir) if prompts_dir else DEFAULT_PROMPTS_DIR
        self.skills_enabled = skills_enabled
        self._templates: dict[str, str] = {}
        self._load_default_templates()

    def _load_default_templates(self) -> None:
        """Load default embedded templates."""
        # Build system prompt with appropriate tools section
        # Use replace() instead of format() to avoid issues with { } in code examples
        tools_section = TOOLS_SECTION_SKILLS if self.skills_enabled else TOOLS_SECTION_NO_SKILLS
        system_prompt = SYSTEM_PROMPT_BASE.replace("{tools_section}", tools_section)

        self._templates = {
            "system": system_prompt,
            "decision": DECISION_PROMPT,
            "skill_creation": SKILL_CREATION_PROMPT,
            "analysis": ANALYSIS_PROMPT,
        }

    def load_templates(self) -> int:
        """
        Load templates from the prompts directory.

        Returns:
            Number of templates loaded
        """
        if not self.prompts_dir.exists():
            logger.warning(f"Prompts directory not found: {self.prompts_dir}")
            return 0

        count = 0
        for template_file in self.prompts_dir.glob("*.txt"):
            name = template_file.stem
            self._templates[name] = template_file.read_text()
            count += 1
            logger.debug(f"Loaded template: {name}")

        logger.info(f"Loaded {count} prompt templates")
        return count

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

    def format_decision_prompt(
        self,
        saved_skills: list[str],
        last_result: Optional[dict] = None,
        game_screen: Optional[str] = None,
        current_position: Optional[Any] = None,
        hostile_monsters: Optional[list[Any]] = None,
        adjacent_tiles: Optional[dict[str, str]] = None,
        inventory: Optional[list[Any]] = None,
    ) -> str:
        """
        Format a decision prompt with current game context.

        Args:
            saved_skills: List of skill names the agent has written
            last_result: Result of the last tool execution
            game_screen: Full game screen (ASCII art showing what human would see)
            current_position: Current player Position (x, y)
            hostile_monsters: List of hostile Monster objects
            adjacent_tiles: Dict mapping direction names to tile descriptions
            inventory: List of Item objects in player's inventory

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

        # Format last result
        if last_result:
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

            result_text = "\n".join(result_lines) if result_lines else "None"
        else:
            result_text = "None"

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

        kwargs = {
            "game_screen": game_screen or "Screen not available",
            "position": position_text,
            "adjacent_tiles": adjacent_text,
            "last_result": result_text,
            "hostile_monsters": monsters_text,
            "inventory": inventory_text,
            "skills_section": skills_section,
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

# Tools section variants
TOOLS_SECTION_SKILLS = """You have 3 tools available:
- **execute_code** - Run Python code to interact with the game. Batch multiple operations.
- **write_skill** - Save reusable code as a skill. Code must be: async def skill_name(nh, **params):
- **invoke_skill** - Run a previously saved skill."""

TOOLS_SECTION_NO_SKILLS = """You have 1 tool available:
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

**Note:** Blank spaces on the map are UNEXPLORED STONE - not walkable!

IMPORTANT: All API calls are SYNCHRONOUS. Do NOT use await or async. Do NOT use imports.
Use dir(nh) to explore available methods if needed.

### Navigation (USE THESE - they handle pathfinding for you!)

**nh.travel_to(char)** - Travel to a map feature. This is your PRIMARY movement tool!
  result = nh.travel_to('>')  # Go to stairs down
  result = nh.travel_to('<')  # Go to stairs up
  result = nh.travel_to('+')  # Go to a door
  result = nh.travel_to('$')  # Go to gold
  if result.success: nh.go_down()  # Then use stairs

**nh.autoexplore()** - Explore the level automatically. Use for any exploration!
  result = nh.autoexplore()
  # Stops for: "hostile" (nearby), "low_hp", "hungry", "fully_explored", "blocked"
  # Does NOT stop for items, stairs, features - explores until done or danger
  if result.stop_reason == "hostile": nh.attack(direction)

**nh.move_to(Position)** - Pathfind to a specific coordinate
  nh.move_to(Position(42, 12))  # Walk to that spot

PREFER navigation tools over manual movement! They handle doors, corridors, etc.

### Actions (all return ActionResult)

ActionResult has: .success (bool), .messages (list[str]), .turn_elapsed (bool)
Check .messages for feedback like "You hit the goblin!" or "It's a wall."

**Movement (only for single-step moves when you know the way is clear):**
nh.move(Direction)           # Single step - use travel_to() instead for multi-step!
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
nh.pray()                    # Pray to deity (has cooldown)
nh.engrave("Elbereth")       # Write on floor
nh.look()                    # Look at current square

**Utility:**
nh.wait()                    # Wait one turn
nh.search()                  # Search for secrets

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

Example - combat loop:
  while nh.hp > nh.max_hp * 0.3 and nh.has_adjacent_hostile:
      nh.attack(direction)

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

### NAVIGATION REMINDER

DO NOT manually navigate with move(Direction) unless target is 1 tile away!
- To reach stairs: `nh.travel_to('>')` then `nh.go_down()`
- To explore: `nh.autoexplore()`
- To reach a position: `nh.move_to(position)`

Manual move() is ONLY for:
- Attacking adjacent enemies: `nh.attack(Direction.W)`
- Moving one tile when you can SEE it's clear

## Reading the Map

The map shows what's on the level:
- Doors ('+' closed), stairs ('<' up, '>' down)
- Items on the ground ('$' gold, '%' food, ')' weapons, etc.)
- Monsters (letters like 'g' goblin, 'o' orc, 'd' dog)
- Blank spaces are UNEXPLORED STONE - not empty walkable area!

**IMPORTANT: Do NOT try to manually navigate by reading the map!**
You cannot reliably determine paths from ASCII text. Instead:
- Use `travel_to('>')` to reach stairs, doors, items
- Use `autoexplore()` to find unexplored areas
- Use `move_to(position)` if you have exact coordinates

Only use `move(Direction)` for adjacent targets you can verify in "Adjacent tiles".

## EFFICIENCY - Keep Code Minimal

The game view already shows HP, position, monsters. DO NOT print redundant info!
BAD: `stats = nh.get_stats(); print(f"HP: {stats.hp}")` - already in status bar!
GOOD: `nh.attack(Direction.W)` - just take the action

## LOOPS MUST CHECK FOR DANGER

Any loop that takes multiple actions MUST check for hostiles between iterations.
Monsters can appear or wake up at any time - blind loops will get you killed!

BAD:
  for _ in range(15): nh.search()  # Could die if monster appears!

GOOD:
  for _ in range(15):
      if nh.has_adjacent_hostile: break
      nh.search()

ALSO GOOD: Just call autoexplore() or let the outer agent loop handle it - you'll get
called again next turn with updated state."""

DECISION_PROMPT = """=== CURRENT GAME VIEW ===
{position}
{game_screen}
{adjacent_tiles}
{hostile_monsters}
{inventory}
{skills_section}
Last Result:
{last_result}

Study the map. What do you observe, and what action will you take?"""

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
- Movement: move(direction), go_up(), go_down()
- Combat: attack(direction)
- Items: pickup(), eat(slot), quaff(slot), wield(slot), wear(slot)
- Utility: wait(), search(), open_door(direction)
- Navigation: move_to(target), travel_to(char), autoexplore()

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

