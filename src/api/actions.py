"""
Action execution for NetHack.

Maps high-level actions to NLE action indices and handles multi-step commands.
"""

from typing import TYPE_CHECKING, Optional

from nle import nethack

from .models import ActionResult, Direction, Position

if TYPE_CHECKING:
    from .environment import NLEWrapper


class ActionExecutor:
    """
    Executes actions in the NLE environment.

    Handles the mapping from high-level action names to NLE action indices,
    and manages multi-step commands that require multiple keypresses.
    """

    def __init__(self, env: "NLEWrapper"):
        """
        Initialize the action executor.

        Args:
            env: The NLE environment wrapper
        """
        self.env = env
        self._build_action_map()

    def _build_action_map(self):
        """Build mapping from characters/commands to action indices."""
        actions = self.env.action_space
        # Get the raw action tuple from the environment
        raw_actions = self.env._env.unwrapped.actions if self.env._env else ()

        self._char_to_idx = {}
        for idx, action_byte in enumerate(raw_actions):
            self._char_to_idx[action_byte] = idx

        # Direction mappings (NLE uses vi keys)
        self._direction_keys = {
            Direction.N: ord("k"),
            Direction.S: ord("j"),
            Direction.E: ord("l"),
            Direction.W: ord("h"),
            Direction.NE: ord("u"),
            Direction.NW: ord("y"),
            Direction.SE: ord("n"),
            Direction.SW: ord("b"),
            Direction.UP: ord("<"),
            Direction.DOWN: ord(">"),
            Direction.SELF: ord("."),
        }

    def _get_action_idx(self, char: int) -> Optional[int]:
        """Get action index for a character code."""
        return self._char_to_idx.get(char)

    def _is_more_prompt(self) -> bool:
        """Check if the game is showing a --More-- prompt."""
        obs = self.env.last_observation
        if obs is None:
            return False
        # Check both the message and the screen for --More--
        # (long messages like item listings show --More-- in screen, not message)
        message = obs.get_message()
        if "--More--" in message:
            return True
        screen = obs.get_screen()
        return "--More--" in screen

    def _dismiss_more_prompts(self, max_prompts: int = 10) -> list[str]:
        """
        Dismiss any --More-- prompts by sending space.

        Returns:
            List of messages collected while dismissing prompts
        """
        messages = []
        space_idx = self._get_action_idx(ord(" "))
        if space_idx is None:
            return messages

        for _ in range(max_prompts):
            if not self._is_more_prompt():
                break
            try:
                obs, _, _, _, _ = self.env.step(space_idx)
                if obs:
                    msg = obs.get_message()
                    if msg and msg not in messages:
                        messages.append(msg)
            except Exception:
                break
        return messages

    def _execute_single(self, char: int) -> ActionResult:
        """Execute a single action by character code."""
        # First, dismiss any pending --More-- prompts
        more_messages = self._dismiss_more_prompts()

        idx = self._get_action_idx(char)
        if idx is None:
            return ActionResult.failure(f"Unknown action character: {chr(char)}")

        try:
            obs, reward, terminated, truncated, info = self.env.step(idx)
            message = obs.get_message() if obs else ""

            # Dismiss any --More-- prompts that appeared after our action
            post_messages = self._dismiss_more_prompts()

            all_messages = more_messages + ([message] if message else []) + post_messages

            return ActionResult(
                success=True,
                messages=all_messages,
                turn_elapsed=True,
                state_changed=True,
            )
        except Exception as e:
            return ActionResult.failure(str(e))

    def _execute_sequence(self, chars: list[int]) -> ActionResult:
        """Execute a sequence of actions."""
        messages = []
        for char in chars:
            result = self._execute_single(char)
            if result.messages:
                messages.extend(result.messages)
            if not result.success:
                result.messages = messages
                return result
        return ActionResult(success=True, messages=messages)

    # ==================== Movement ====================

    def move(self, direction: Direction) -> ActionResult:
        """
        Move in a direction.

        Args:
            direction: Direction to move (N, S, E, W, NE, NW, SE, SW)

        Returns:
            ActionResult indicating success/failure (success=True only if position changed)
        """
        key = self._direction_keys.get(direction)
        if key is None:
            return ActionResult.failure(f"Invalid direction: {direction}")

        # Record position before move
        obs_before = self.env.last_observation
        pos_before = None
        if obs_before:
            pos_before = (obs_before.player_x, obs_before.player_y)

        result = self._execute_single(key)

        # Check if position actually changed
        obs_after = self.env.last_observation
        if obs_after and pos_before:
            pos_after = (obs_after.player_x, obs_after.player_y)
            if pos_before == pos_after:
                # Position didn't change - move failed (hit wall, etc.)
                result.success = False
                result.turn_elapsed = False

        return result

    def move_toward(self, target: Position) -> ActionResult:
        """
        Move one step toward a target position.

        Args:
            target: Target position to move toward

        Returns:
            ActionResult indicating success/failure
        """
        if self.env.last_observation is None:
            return ActionResult.failure("No observation available")

        current = Position(
            self.env.last_observation.player_x, self.env.last_observation.player_y
        )

        direction = current.direction_to(target)
        if direction is None or direction == Direction.SELF:
            return ActionResult(
                success=True, messages=["Already at target"], turn_elapsed=False
            )

        return self.move(direction)

    def go_up(self) -> ActionResult:
        """Ascend stairs (<). Returns success=True only if dungeon level changed."""
        # Record level before
        obs_before = self.env.last_observation
        level_before = None
        if obs_before:
            level_before = int(obs_before.blstats[12])  # BL_DEPTH

        result = self._execute_single(ord("<"))

        # Check if level actually changed
        obs_after = self.env.last_observation
        if obs_after and level_before is not None:
            level_after = int(obs_after.blstats[12])
            if level_before == level_after:
                result.success = False
                result.turn_elapsed = False

        return result

    def go_down(self) -> ActionResult:
        """Descend stairs (>). Returns success=True only if dungeon level changed."""
        # Record level before
        obs_before = self.env.last_observation
        level_before = None
        if obs_before:
            level_before = int(obs_before.blstats[12])  # BL_DEPTH

        result = self._execute_single(ord(">"))

        # Check if level actually changed
        obs_after = self.env.last_observation
        if obs_after and level_before is not None:
            level_after = int(obs_after.blstats[12])
            if level_before == level_after:
                result.success = False
                result.turn_elapsed = False

        return result

    # ==================== Combat ====================

    def attack(self, direction: Direction) -> ActionResult:
        """
        Attack in a direction (force fight with F prefix).

        Args:
            direction: Direction to attack

        Returns:
            ActionResult
        """
        key = self._direction_keys.get(direction)
        if key is None:
            return ActionResult.failure(f"Invalid direction: {direction}")

        # F prefix forces fight even if no visible monster
        return self._execute_sequence([ord("F"), key])

    def kick(self, direction: Direction) -> ActionResult:
        """
        Kick in a direction (Ctrl+D then direction).

        Args:
            direction: Direction to kick

        Returns:
            ActionResult
        """
        key = self._direction_keys.get(direction)
        if key is None:
            return ActionResult.failure(f"Invalid direction: {direction}")

        # Ctrl+D is character code 4
        return self._execute_sequence([4, key])

    def fire(self, direction: Direction) -> ActionResult:
        """
        Fire wielded ranged weapon.

        Args:
            direction: Direction to fire

        Returns:
            ActionResult
        """
        key = self._direction_keys.get(direction)
        if key is None:
            return ActionResult.failure(f"Invalid direction: {direction}")

        return self._execute_sequence([ord("f"), key])

    def throw(self, item_letter: str, direction: Direction) -> ActionResult:
        """
        Throw an item.

        Args:
            item_letter: Inventory letter of item to throw
            direction: Direction to throw

        Returns:
            ActionResult
        """
        key = self._direction_keys.get(direction)
        if key is None:
            return ActionResult.failure(f"Invalid direction: {direction}")

        return self._execute_sequence([ord("t"), ord(item_letter), key])

    # ==================== Items ====================

    def pickup(self, item_letter: Optional[str] = None) -> ActionResult:
        """
        Pick up items.

        Args:
            item_letter: If specified, pick up specific item. Otherwise pick up all.

        Returns:
            ActionResult
        """
        if item_letter:
            # Pick up specific item from pile
            return self._execute_sequence([ord(","), ord(item_letter)])
        else:
            # Pick up all or single item
            return self._execute_single(ord(","))

    def drop(self, item_letter: str) -> ActionResult:
        """
        Drop an item.

        Args:
            item_letter: Inventory letter of item to drop

        Returns:
            ActionResult
        """
        return self._execute_sequence([ord("d"), ord(item_letter)])

    def eat(self, item_letter: Optional[str] = None) -> ActionResult:
        """
        Eat food.

        Args:
            item_letter: Single-character inventory letter of food to eat,
                        or None to eat from ground/prompt

        Returns:
            ActionResult
        """
        if item_letter:
            if len(item_letter) != 1:
                return ActionResult.failure(
                    f"item_letter must be a single character, got '{item_letter}'. "
                    "Use nh.eat() with no arguments to eat from ground."
                )
            return self._execute_sequence([ord("e"), ord(item_letter)])
        else:
            # Eat from ground or prompt
            return self._execute_single(ord("e"))

    def quaff(self, item_letter: str) -> ActionResult:
        """
        Drink a potion.

        Args:
            item_letter: Inventory letter of potion

        Returns:
            ActionResult
        """
        return self._execute_sequence([ord("q"), ord(item_letter)])

    def read(self, item_letter: str) -> ActionResult:
        """
        Read a scroll or spellbook.

        Args:
            item_letter: Inventory letter of scroll/book

        Returns:
            ActionResult
        """
        return self._execute_sequence([ord("r"), ord(item_letter)])

    def zap(self, item_letter: str, direction: Direction) -> ActionResult:
        """
        Zap a wand.

        Args:
            item_letter: Inventory letter of wand
            direction: Direction to zap

        Returns:
            ActionResult
        """
        key = self._direction_keys.get(direction)
        if key is None:
            return ActionResult.failure(f"Invalid direction: {direction}")

        return self._execute_sequence([ord("z"), ord(item_letter), key])

    def wear(self, item_letter: str) -> ActionResult:
        """
        Wear armor.

        Args:
            item_letter: Inventory letter of armor

        Returns:
            ActionResult
        """
        return self._execute_sequence([ord("W"), ord(item_letter)])

    def wield(self, item_letter: str) -> ActionResult:
        """
        Wield a weapon.

        Args:
            item_letter: Inventory letter of weapon

        Returns:
            ActionResult
        """
        return self._execute_sequence([ord("w"), ord(item_letter)])

    def take_off(self, item_letter: str) -> ActionResult:
        """
        Remove worn armor.

        Args:
            item_letter: Inventory letter of armor to remove

        Returns:
            ActionResult
        """
        return self._execute_sequence([ord("T"), ord(item_letter)])

    def apply(self, item_letter: str) -> ActionResult:
        """
        Apply/use a tool.

        Args:
            item_letter: Inventory letter of tool

        Returns:
            ActionResult
        """
        return self._execute_sequence([ord("a"), ord(item_letter)])

    # ==================== Doors ====================

    def open_door(self, direction: Direction) -> ActionResult:
        """
        Open a door.

        Args:
            direction: Direction of door

        Returns:
            ActionResult
        """
        key = self._direction_keys.get(direction)
        if key is None:
            return ActionResult.failure(f"Invalid direction: {direction}")

        return self._execute_sequence([ord("o"), key])

    def close_door(self, direction: Direction) -> ActionResult:
        """
        Close a door.

        Args:
            direction: Direction of door

        Returns:
            ActionResult
        """
        key = self._direction_keys.get(direction)
        if key is None:
            return ActionResult.failure(f"Invalid direction: {direction}")

        return self._execute_sequence([ord("c"), key])

    # ==================== Utility ====================

    def wait(self) -> ActionResult:
        """Wait/search in place (.)."""
        return self._execute_single(ord("."))

    def search(self) -> ActionResult:
        """Search adjacent squares for secrets (s)."""
        return self._execute_single(ord("s"))

    def rest(self) -> ActionResult:
        """Rest until healed (synonym for wait)."""
        return self.wait()

    def pray(self) -> ActionResult:
        """Pray to your deity."""
        # Note: 'p' is PAY (pay shopkeeper), PRAY is a separate extended command
        # NetHack asks "Are you sure you want to pray? [yn]" - we confirm with 'y'
        return self._execute_sequence([nethack.Command.PRAY, ord("y")])

    def look(self) -> ActionResult:
        """Look at what's here (:)."""
        return self._execute_single(ord(":"))

    # ==================== Special ====================

    def cast_spell(self, spell_letter: str, direction: Optional[Direction] = None) -> ActionResult:
        """
        Cast a memorized spell.

        Args:
            spell_letter: Letter of spell to cast
            direction: Direction for directional spells

        Returns:
            ActionResult
        """
        if direction:
            key = self._direction_keys.get(direction)
            if key is None:
                return ActionResult.failure(f"Invalid direction: {direction}")
            return self._execute_sequence([ord("Z"), ord(spell_letter), key])
        else:
            return self._execute_sequence([ord("Z"), ord(spell_letter)])

    def engrave(self, text: str = "Elbereth") -> ActionResult:
        """
        Engrave on the floor.

        Handles both new engravings and adding to existing ones.
        Uses finger to write in dust (safe, no item consumption).

        Args:
            text: Text to engrave (default: "Elbereth")

        Returns:
            ActionResult
        """
        # E to engrave, - for finger
        # If there's an existing engraving, NetHack asks "add to writing?"
        # We send the text regardless - it handles both cases
        # End with Enter to submit, then multiple Escapes to clear any prompts
        chars = [ord("E"), ord("-")]
        for c in text:
            chars.append(ord(c))
        chars.append(13)  # Enter to submit

        result = self._execute_sequence(chars)

        # Clear any remaining prompts by sending escapes
        for _ in range(3):
            self._execute_single(27)  # Escape

        return result

    # ==================== Raw ====================

    def send_keys(self, keys: str) -> ActionResult:
        """
        Send raw keystrokes.

        Args:
            keys: String of keys to send

        Returns:
            ActionResult
        """
        chars = [ord(c) for c in keys]
        return self._execute_sequence(chars)

    def send_action(self, action_idx: int) -> ActionResult:
        """
        Send a raw action index.

        Args:
            action_idx: NLE action index

        Returns:
            ActionResult
        """
        try:
            obs, reward, terminated, truncated, info = self.env.step(action_idx)
            message = obs.get_message() if obs else ""
            return ActionResult(
                success=True,
                messages=[message] if message else [],
                turn_elapsed=True,
                state_changed=True,
            )
        except Exception as e:
            return ActionResult.failure(str(e))

    def escape(self) -> ActionResult:
        """Send escape key (cancel current action)."""
        return self._execute_single(27)  # ESC

    def confirm(self) -> ActionResult:
        """Send 'y' for yes confirmation."""
        return self._execute_single(ord("y"))

    def deny(self) -> ActionResult:
        """Send 'n' for no confirmation."""
        return self._execute_single(ord("n"))

    def space(self) -> ActionResult:
        """Send space (continue/dismiss message)."""
        return self._execute_single(ord(" "))
