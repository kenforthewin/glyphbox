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
        # Use skill-aware system prompt
        system_prompt = SYSTEM_PROMPT if self.skills_enabled else SYSTEM_PROMPT_NO_SKILLS
        self._templates = {
            "system": system_prompt,
            "decision": DECISION_PROMPT if self.skills_enabled else DECISION_PROMPT_NO_SKILLS,
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
        return self._templates.get("system", SYSTEM_PROMPT)

    def format_decision_prompt(
        self,
        game_state: dict,
        saved_skills: list[str],
        recent_events: list[dict],
        last_result: Optional[dict] = None,
        game_screen: Optional[str] = None,
    ) -> str:
        """
        Format a decision prompt with current game context.

        Args:
            game_state: Current game state summary
            saved_skills: List of skill names the agent has written
            recent_events: Recent game events
            last_result: Result of the last tool execution
            game_screen: Full game screen (ASCII art showing what human would see)

        Returns:
            Formatted decision prompt
        """
        # Format game state
        state_text = self._format_game_state(game_state)

        # Format saved skills (only when skills enabled)
        skills_text = ""
        if self.skills_enabled:
            if saved_skills:
                skills_text = "\n".join(f"- {name}" for name in saved_skills)
            else:
                skills_text = "None (use write_skill to create skills)"

        # Format events
        events_text = self._format_events(recent_events)

        # Format last result
        if last_result:
            result_lines = []

            # Show success/error first
            if "success" in last_result:
                result_lines.append(f"success: {last_result['success']}")
            if last_result.get("error"):
                result_lines.append(f"error: {last_result['error']}")

            # Show game messages prominently (these tell the LLM what happened)
            messages = last_result.get("messages", [])
            if messages:
                result_lines.append("game_messages:")
                for msg in messages:
                    if msg:  # Skip empty messages
                        result_lines.append(f"  - {msg}")

                # Interpret common message patterns for agent guidance
                for msg in messages:
                    if not msg:
                        continue
                    msg_lower = msg.lower()
                    if "you kill" in msg_lower or "you destroy" in msg_lower:
                        result_lines.append("  >>> ENEMY KILLED - may have dropped corpse or items")
                    elif "you see here" in msg_lower:
                        result_lines.append("  HINT: Item AT YOUR FEET - use nh.pickup() or nh.eat() with NO arguments")
                    elif "it's solid stone" in msg_lower or "it's a wall" in msg_lower:
                        result_lines.append("  HINT: Movement blocked - try different direction")
                    elif "locked" in msg_lower and "door" in msg_lower:
                        result_lines.append("  HINT: Door locked - use kick() or find key")
                    elif "there is nothing here to pick up" in msg_lower:
                        result_lines.append("  HINT: No items at current position")
                    elif "hidden rooms may exist" in msg_lower:
                        result_lines.append("  HINT: Level may have secret doors hiding rooms/stairs")
                    # Detect pickup messages like "e - a kobold corpse" (item now in inventory)
                    elif len(msg) > 4 and msg[1:4] == " - " and msg[0].isalpha():
                        result_lines.append(f"  >>> PICKED UP into slot '{msg[0]}' - item is now in INVENTORY, not on ground")

            # Show hint if present (from look_around)
            if last_result.get("hint"):
                result_lines.append(last_result["hint"])

            # Show FAILED API calls prominently - critical feedback for the agent
            failed_calls = last_result.get("failed_api_calls", [])
            if failed_calls:
                result_lines.append("FAILED API CALLS (actions that did not succeed):")
                for call in failed_calls:
                    method = call.get("method", "unknown")
                    error = call.get("error", "unknown error")
                    result_lines.append(f"  - {method}() FAILED: {error}")

            # Show return value if meaningful
            rv = last_result.get("return_value")
            if rv is not None and rv != {}:
                result_lines.append(f"return_value: {rv}")

            # Show output if present
            if last_result.get("output"):
                result_lines.append(f"output: {last_result['output']}")

            result_text = "\n".join(result_lines) if result_lines else "None"
        else:
            result_text = "None"

        # Build kwargs - only include saved_skills when skills enabled
        kwargs = {
            "game_screen": game_screen or "Screen not available",
            "game_state": state_text,
            "recent_events": events_text,
            "last_result": result_text,
        }
        if self.skills_enabled:
            kwargs["saved_skills"] = skills_text

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

        # Position (coordinates not visible on screen, only @ symbol)
        if "position_x" in state and "position_y" in state:
            lines.append(f"Position: ({state['position_x']}, {state['position_y']})")

        # Hunger (only shows on screen when hungry/weak/fainting)
        if "hunger_state" in state:
            lines.append(f"Hunger: {state['hunger_state']}")

        # Combat status indicator
        if state.get("in_combat"):
            lines.append("Status: IN COMBAT")
        elif state.get("hp_trend") == "critical":
            lines.append("Status: CRITICAL HP")

        # Hostile monsters with details (distances, directions)
        if "hostile_monster_details" in state and state["hostile_monster_details"]:
            lines.append("Hostile Monsters:")
            for m in state["hostile_monster_details"]:
                lines.append(f"  - {m}")

        # Doors with state and distance
        if "door_details" in state and state["door_details"]:
            lines.append("Doors:")
            for d in state["door_details"][:5]:  # Limit to 5 doors
                lines.append(f"  - {d}")

        # Stairs locations
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

SYSTEM_PROMPT = """You are an expert NetHack player. You interact with the game using Python code executed in a sandbox.

## Game View

The full game screen (what a human player would see) is provided at the start of each turn.
This includes the dungeon map, messages, and status bar with your stats.

## Available Tools

You have 3 tools available:
- **execute_code** - Run Python code to interact with the game. Batch multiple operations.
- **write_skill** - Save reusable code as a skill. Code must be: async def skill_name(nh, **params):
- **invoke_skill** - Run a previously saved skill.

## API Reference

Your code has access to `nh` (NetHackAPI) and these pre-loaded types:
- Direction: N, S, E, W, NE, NW, SE, SW
- Position: x, y coordinates with .distance_to(), .direction_to() methods

IMPORTANT: All API calls are SYNCHRONOUS. Do NOT use await or async. Do NOT use imports.
Use dir(nh) to explore available methods if needed.

### Actions (all return ActionResult)

ActionResult has: .success (bool), .messages (list[str]), .turn_elapsed (bool)
Check .messages for feedback like "You hit the goblin!" or "It's a wall."

**Movement:**
nh.move(Direction)           # Move in direction, fails if blocked
nh.move_toward(Position)     # Move one step toward target
nh.go_up()                   # Climb stairs up (<)
nh.go_down()                 # Descend stairs (>)

**Combat:**
nh.attack(Direction)         # Attack in direction
nh.kick(Direction)           # Kick (doors, monsters)
nh.fire(Direction)           # Fire wielded ranged weapon
nh.throw('a', Direction)     # Throw item by inventory letter

**Items (ground items have slot=None, use pickup() without args):**
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

**Stats:**
stats = nh.get_stats()
  stats.hp, stats.max_hp         # Hit points
  stats.position.x, stats.position.y  # Coordinates (NOT stats.x!)
  stats.dungeon_level            # Current level
  stats.hunger                   # HungerState enum (see below)
  stats.gold, stats.ac, stats.xp_level  # Gold, armor class, experience
  stats.is_hungry                # bool - True if Hungry/Weak/Fainting (USE THIS!)
  stats.is_weak                  # bool - True if Weak/Fainting (critical!)

Hunger: Use stats.is_hungry (True if HUNGRY+) or stats.is_weak (True if WEAK+)

**Monsters:**
nh.get_visible_monsters()    # List[Monster] - all visible
nh.get_adjacent_monsters()   # List[Monster] - next to you
nh.get_hostile_monsters()    # List[Monster] - hostile only

Monster has: .name, .position, .is_hostile, .is_peaceful, .is_tame

**Items:**
nh.get_inventory()           # List[Item] - your items (have .slot)
nh.get_items_here()          # List[Item] - items on ground (slot=None, use pickup())
nh.get_food()                # List[Item] - food in inventory
nh.get_weapons()             # List[Item] - weapons in inventory

Item has: .name, .slot (inventory letter), .quantity

**Environment:**
nh.get_message()             # Latest game message
nh.get_messages(10)          # Last 10 messages
nh.get_screen()              # ASCII screen as single string
nh.get_screen_lines()        # list[str] - 24 rows, useful for parsing
nh.get_position()            # Current Position
nh.get_tile(Position)        # Tile at position (see Tile below)
nh.get_items_on_map()        # List[Item] - items visible on map (not inventory)

**Tile** (from get_tile):
  tile.char                    # str - the ASCII character
  tile.is_walkable             # bool - can walk here?
  tile.is_explored             # bool - have we seen this tile?
  tile.position                # Position

**Position**: nh.position returns Position(x, y). Methods: pos.distance_to(other), pos.direction_to(other)

**Prompt Responses (for [ynq] and similar prompts):**
nh.confirm()                 # Send 'y' - accept/confirm
nh.deny()                    # Send 'n' - decline/cancel
nh.escape()                  # Send ESC - cancel action
nh.space()                   # Send space - dismiss message
nh.send_keys("abc")          # Send raw keys (advanced)

IMPORTANT: When you see "[ynq]" or "[yn]" in a message, the game is waiting for input!
  msg = nh.get_message()
  if "[yn" in msg or "[ynq]" in msg:
      nh.confirm()  # or nh.deny() depending on what you want

### Movement & Navigation

nh.move_to(target)           # Move to position (pathfinds automatically). Returns ActionResult.
nh.find_stairs_down()        # Returns TargetResult with position of stairs
nh.find_stairs_up()          # Returns TargetResult
nh.find_nearest_item()       # Returns TargetResult with nearest item position
nh.find_nearest_monster()    # Position or None
nh.find_doors()              # list[(Position, is_open)] - all doors on level

Note: move_to() works even with hostile monsters visible - it will stop if a hostile appears during movement.

Example - moving to stairs:
  target = nh.find_stairs_down()
  if target.success:
      result = nh.move_to(target.position)
      if result.success:
          nh.go_down()

Example - opening a door after finding it:
  doors = nh.find_doors()
  for pos, is_open in doors:
      if not is_open:  # Found closed door
          # Move adjacent to door, then open it
          result = nh.move_to(pos)  # Will stop adjacent since door is unwalkable
          if nh.position.distance_to(pos) == 1:
              nh.open_door(nh.position.direction_to(pos))

**TargetResult** - returned by find_stairs/find_nearest_item:
  result.position   # Position or None
  result.success    # bool - True if target found
  result.message    # Human-readable explanation
  if result:        # Truthy if position found

### Autoexplore (USE THIS for exploration)

nh.autoexplore()  # Explore until interrupted, returns AutoexploreResult

**AutoexploreResult**:
  result.stop_reason   # Why it stopped (see below)
  result.steps_taken   # Number of movement steps
  result.turns_elapsed # Game turns elapsed
  result.position      # Final position
  result.message       # Human-readable explanation
  result.success       # True if fully_explored/feature/stairs

**stop_reason values**:
  "fully_explored" - All VISIBLE areas explored (hidden rooms may exist)
  "hostile"        - Hostile monster appeared
  "low_hp"         - HP dropped below 30%
  "hungry"         - Hunger worsened (HUNGRY if started not-hungry, WEAK if started hungry)
  "feature"        - Found altar, throne, fountain, etc.
  "stairs"         - Found stairs
  "item"           - Found item on ground
  "dead_end"       - Reached dead end (3+ adjacent walls)
  "max_steps"      - Hit max_steps limit (default 500)
  "blocked"        - Cannot move into unexplored area

**PREFER autoexplore() over manual exploration loops!**
It handles pathfinding, movement, and stopping automatically:
  result = nh.autoexplore()
  if result.stop_reason == "hostile":
      # Fight the monster
  elif result.stop_reason == "stairs":
      # Decide whether to descend
  elif result.stop_reason == "fully_explored":
      # Visible areas done - check for hidden rooms or go down

### Knowledge (monster/item info)

nh.is_dangerous_melee(name)  # bool - dangerous to fight?
nh.is_corpse_safe(name)      # bool - safe to eat?
nh.is_prayer_safe()          # bool - can pray now?
nh.estimate_difficulty(name) # int 0-10

### Properties

nh.is_done                   # bool - game over?
nh.turn                      # int - current turn
nh.position                  # Position - current location

## Key Principles

1. BATCH WITH CHECKS - Multiple moves in one execute_code, but CHECK results:
   Good: for _ in range(5):
           res = nh.move(Direction.E)
           if not res.success: break  # Stop if blocked
   Bad: nh.move(Direction.E); nh.move(Direction.E); nh.move(Direction.E)  # Blind batching

2. USE move_to() - Don't guess directions. Use the API:
   result = nh.move_to(target_position)
   if not result.success:
       print(f"Couldn't reach target: {result.messages}")

3. CHECK MESSAGES - ActionResult.messages tells you what happened ("It's solid stone", etc.)

4. SURVIVAL FIRST - Check HP AND hunger. Eat when Hungry/Weak. Retreat if HP < 50%.

5. TAKE ACTION - Always make game progress. Move, fight, explore."""

DECISION_PROMPT = """=== CURRENT GAME VIEW ===
{game_screen}

=== GAME STATE ===
{game_state}

Your Saved Skills:
{saved_skills}

Recent Events:
{recent_events}

Last Result:
{last_result}

What action do you want to take?"""

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
- State: get_stats(), get_position(), get_message(), get_visible_monsters(), get_adjacent_monsters(), get_inventory(), turn, is_done
- Movement: move(direction), go_up(), go_down()
- Combat: attack(direction)
- Items: pickup(), eat(slot), quaff(slot), wield(slot), wear(slot)
- Utility: wait(), search(), open_door(direction)
- Navigation: move_to(target), autoexplore(), find_stairs_up(), find_stairs_down()
- Knowledge: is_dangerous_melee(name), is_corpse_safe(name)

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

# ============================================================================
# No-Skills Prompt Templates (when skills_enabled=False)
# ============================================================================

SYSTEM_PROMPT_NO_SKILLS = """You are an expert NetHack player. You interact with the game using Python code executed in a sandbox.

## Game View

The full game screen (what a human player would see) is provided at the start of each turn.
This includes the dungeon map, messages, and status bar with your stats.

## Available Tools

You have 1 tool available:
- **execute_code** - Run Python code to interact with the game. Batch multiple operations.

## API Reference

Your code has access to `nh` (NetHackAPI) and these pre-loaded types:
- Direction: N, S, E, W, NE, NW, SE, SW
- Position: x, y coordinates with .distance_to(), .direction_to() methods

IMPORTANT: All API calls are SYNCHRONOUS. Do NOT use await or async. Do NOT use imports.
Use dir(nh) to explore available methods if needed.

### Actions (all return ActionResult)

ActionResult has: .success (bool), .messages (list[str]), .turn_elapsed (bool)
Check .messages for feedback like "You hit the goblin!" or "It's a wall."

**Movement:**
nh.move(Direction)           # Move in direction, fails if blocked
nh.move_toward(Position)     # Move one step toward target
nh.go_up()                   # Climb stairs up (<)
nh.go_down()                 # Descend stairs (>)

**Combat:**
nh.attack(Direction)         # Attack in direction
nh.kick(Direction)           # Kick (doors, monsters)
nh.fire(Direction)           # Fire wielded ranged weapon
nh.throw('a', Direction)     # Throw item by inventory letter

**Items (ground items have slot=None, use pickup() without args):**
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

**Stats:**
stats = nh.get_stats()
  stats.hp, stats.max_hp         # Hit points
  stats.position.x, stats.position.y  # Coordinates (NOT stats.x!)
  stats.dungeon_level            # Current level
  stats.hunger                   # HungerState enum (see below)
  stats.gold, stats.ac, stats.xp_level  # Gold, armor class, experience
  stats.is_hungry                # bool - True if Hungry/Weak/Fainting (USE THIS!)
  stats.is_weak                  # bool - True if Weak/Fainting (critical!)

Hunger: Use stats.is_hungry (True if HUNGRY+) or stats.is_weak (True if WEAK+)

**Monsters:**
nh.get_visible_monsters()    # List[Monster] - all visible
nh.get_adjacent_monsters()   # List[Monster] - next to you
nh.get_hostile_monsters()    # List[Monster] - hostile only

Monster has: .name, .position, .is_hostile, .is_peaceful, .is_tame

**Items:**
nh.get_inventory()           # List[Item] - your items (have .slot)
nh.get_items_here()          # List[Item] - items on ground (slot=None, use pickup())
nh.get_food()                # List[Item] - food in inventory
nh.get_weapons()             # List[Item] - weapons in inventory

Item has: .name, .slot (inventory letter), .quantity

**Environment:**
nh.get_message()             # Latest game message
nh.get_messages(10)          # Last 10 messages
nh.get_screen()              # ASCII screen as single string
nh.get_screen_lines()        # list[str] - 24 rows, useful for parsing
nh.get_position()            # Current Position
nh.get_tile(Position)        # Tile at position (see Tile below)
nh.get_items_on_map()        # List[Item] - items visible on map (not inventory)

**Tile** (from get_tile):
  tile.char                    # str - the ASCII character
  tile.is_walkable             # bool - can walk here?
  tile.is_explored             # bool - have we seen this tile?
  tile.position                # Position

**Position**: nh.position returns Position(x, y). Methods: pos.distance_to(other), pos.direction_to(other)

**Prompt Responses (for [ynq] and similar prompts):**
nh.confirm()                 # Send 'y' - accept/confirm
nh.deny()                    # Send 'n' - decline/cancel
nh.escape()                  # Send ESC - cancel action
nh.space()                   # Send space - dismiss message
nh.send_keys("abc")          # Send raw keys (advanced)

IMPORTANT: When you see "[ynq]" or "[yn]" in a message, the game is waiting for input!
  msg = nh.get_message()
  if "[yn" in msg or "[ynq]" in msg:
      nh.confirm()  # or nh.deny() depending on what you want

### Movement & Navigation

nh.move_to(target)           # Move to position (pathfinds automatically). Returns ActionResult.
nh.find_stairs_down()        # Returns TargetResult with position of stairs
nh.find_stairs_up()          # Returns TargetResult
nh.find_nearest_item()       # Returns TargetResult with nearest item position
nh.find_nearest_monster()    # Position or None
nh.find_doors()              # list[(Position, is_open)] - all doors on level

Note: move_to() works even with hostile monsters visible - it will stop if a hostile appears during movement.

Example - moving to stairs:
  target = nh.find_stairs_down()
  if target.success:
      result = nh.move_to(target.position)
      if result.success:
          nh.go_down()

Example - opening a door after finding it:
  doors = nh.find_doors()
  for pos, is_open in doors:
      if not is_open:  # Found closed door
          # Move adjacent to door, then open it
          result = nh.move_to(pos)  # Will stop adjacent since door is unwalkable
          if nh.position.distance_to(pos) == 1:
              nh.open_door(nh.position.direction_to(pos))

**TargetResult** - returned by find_stairs/find_nearest_item:
  result.position   # Position or None
  result.success    # bool - True if target found
  result.message    # Human-readable explanation
  if result:        # Truthy if position found

### Autoexplore (USE THIS for exploration)

nh.autoexplore()  # Explore until interrupted, returns AutoexploreResult

**AutoexploreResult**:
  result.stop_reason   # Why it stopped (see below)
  result.steps_taken   # Number of movement steps
  result.turns_elapsed # Game turns elapsed
  result.position      # Final position
  result.message       # Human-readable explanation
  result.success       # True if fully_explored/feature/stairs

**stop_reason values**:
  "fully_explored" - All VISIBLE areas explored (hidden rooms may exist)
  "hostile"        - Hostile monster appeared
  "low_hp"         - HP dropped below 30%
  "hungry"         - Hunger worsened (HUNGRY if started not-hungry, WEAK if started hungry)
  "feature"        - Found altar, throne, fountain, etc.
  "stairs"         - Found stairs
  "item"           - Found item on ground
  "dead_end"       - Reached dead end (3+ adjacent walls)
  "max_steps"      - Hit max_steps limit (default 500)
  "blocked"        - Cannot move into unexplored area

**PREFER autoexplore() over manual exploration loops!**
It handles pathfinding, movement, and stopping automatically:
  result = nh.autoexplore()
  if result.stop_reason == "hostile":
      # Fight the monster
  elif result.stop_reason == "stairs":
      # Decide whether to descend
  elif result.stop_reason == "fully_explored":
      # Visible areas done - check for hidden rooms or go down

### Knowledge (monster/item info)

nh.is_dangerous_melee(name)  # bool - dangerous to fight?
nh.is_corpse_safe(name)      # bool - safe to eat?
nh.is_prayer_safe()          # bool - can pray now?
nh.estimate_difficulty(name) # int 0-10

### Properties

nh.is_done                   # bool - game over?
nh.turn                      # int - current turn
nh.position                  # Position - current location

## Key Principles

1. BATCH WITH CHECKS - Multiple moves in one execute_code, but CHECK results:
   Good: for _ in range(5):
           res = nh.move(Direction.E)
           if not res.success: break  # Stop if blocked
   Bad: nh.move(Direction.E); nh.move(Direction.E); nh.move(Direction.E)  # Blind batching

2. USE move_to() - Don't guess directions. Use the API:
   result = nh.move_to(target_position)
   if not result.success:
       print(f"Couldn't reach target: {result.messages}")

3. CHECK MESSAGES - ActionResult.messages tells you what happened ("It's solid stone", etc.)

4. SURVIVAL FIRST - Check HP AND hunger. Eat when Hungry/Weak. Retreat if HP < 50%.

5. TAKE ACTION - Always make game progress. Move, fight, explore."""

DECISION_PROMPT_NO_SKILLS = """=== CURRENT GAME VIEW ===
{game_screen}

=== GAME STATE ===
{game_state}

Recent Events:
{recent_events}

Last Result:
{last_result}

What action do you want to take?"""
