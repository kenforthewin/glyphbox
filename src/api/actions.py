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
        """Check if the game is showing a --More-- prompt using NLE misc flags."""
        obs = self.env.last_observation
        if obs is None:
            return False
        return obs.in_more_prompt

    def _is_yn_prompt(self) -> bool:
        """
        Check if the game is showing a yes/no confirmation prompt.

        Uses NLE misc flags combined with message analysis to distinguish between:
        - Actual y/n prompts: "Eat it? [ynq]", "Really attack? [yn]"
        - Menu selection prompts: "What do you want to eat? [fgh or ?*]"

        Both set misc[0] (in_yn_function), but only y/n prompts should be auto-confirmed.
        """
        obs = self.env.last_observation
        if obs is None:
            return False
        if not obs.in_yn_prompt:
            return False

        # Check message to distinguish y/n from menu selection
        message = obs.get_message()
        # Menu selection prompts have "[letter or ?*]" pattern
        if "or ?*]" in message or "?*]" in message:
            return False
        # Actual y/n prompts have "[yn", "[ynq", "[ynaq" etc.
        return "[yn" in message or "[ynaq" in message

    def _is_attack_prompt(self) -> bool:
        """
        Check if the current y/n prompt is asking to confirm an attack.

        These prompts appear when trying to move into a peaceful creature:
        - "Really attack <monster>? [yn] (n)"

        Returns:
            True if this is an attack confirmation prompt
        """
        obs = self.env.last_observation
        if obs is None:
            return False
        if not obs.in_yn_prompt:
            return False
        message = obs.get_message()
        return "Really attack" in message

    def _is_dangerous_prompt(self) -> bool:
        """
        Check if the current y/n prompt would end or ruin the game if confirmed.

        These prompts should always be declined. Patterns:
        - "Beware, there will be no return!  Still climb? [yn] (n)"
          → going up stairs on Dlvl:1 exits the dungeon and ends the game
        """
        obs = self.env.last_observation
        if obs is None:
            return False
        if not obs.in_yn_prompt:
            return False
        message = obs.get_message()
        return "no return" in message

    def _is_menu_prompt(self) -> bool:
        """
        Check if the game is showing a menu selection prompt.

        Menu prompts ask for a letter selection, e.g., "What do you want to eat? [fgh or ?*]"
        These should be escaped, not auto-confirmed.
        """
        obs = self.env.last_observation
        if obs is None:
            return False
        if not obs.in_yn_prompt:
            return False
        message = obs.get_message()
        return "or ?*]" in message or "?*]" in message

    def _is_getlin_prompt(self) -> bool:
        """Check if the game is waiting for text input using NLE misc flags."""
        obs = self.env.last_observation
        if obs is None:
            return False
        return obs.in_getlin_prompt

    def _is_any_prompt(self) -> bool:
        """Check if the game is in any prompt state."""
        obs = self.env.last_observation
        if obs is None:
            return False
        return obs.in_any_prompt

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

    def _auto_confirm_yn_prompts(self, max_prompts: int = 5) -> list[str]:
        """
        Auto-confirm any y/n prompts by sending 'y'.

        This handles prompts like:
        - "Eat the corpse? [ynq]"
        - "Really attack? [yn]"
        - "Drink from fountain? [yn]"

        Returns:
            List of messages collected while confirming prompts
        """
        messages = []
        y_idx = self._get_action_idx(ord("y"))
        if y_idx is None:
            return messages

        for _ in range(max_prompts):
            if not self._is_yn_prompt():
                break
            try:
                obs, _, _, _, _ = self.env.step(y_idx)
                if obs:
                    msg = obs.get_message()
                    if msg and msg not in messages:
                        messages.append(msg)
                    # After confirming, there might be --More-- prompts
                    more_msgs = self._dismiss_more_prompts()
                    messages.extend(more_msgs)
            except Exception:
                break
        return messages

    def _decline_prompt(self) -> list[str]:
        """
        Decline the current y/n prompt by sending 'n'.

        Returns:
            List of messages collected
        """
        messages = []
        n_idx = self._get_action_idx(ord("n"))
        if n_idx is None:
            return messages

        try:
            obs, _, _, _, _ = self.env.step(n_idx)
            if obs:
                msg = obs.get_message()
                if msg:
                    messages.append(msg)
        except Exception:
            pass
        return messages

    def _decline_attack_prompt(self) -> list[str]:
        """
        Decline an attack confirmation prompt by sending 'n'.

        Returns:
            List of messages collected
        """
        if self._is_attack_prompt():
            return self._decline_prompt()
        return []

    def _handle_all_prompts(
        self, max_iterations: int = 20, decline_attacks: bool = False
    ) -> tuple[list[str], bool]:
        """
        Handle any pending prompts (y/n, --More--, menus) until game is ready for action.

        Auto-confirms y/n prompts and dismisses --More-- prompts.
        For menu selection prompts and getlin prompts, sends ESC to cancel.

        Args:
            max_iterations: Maximum number of prompts to handle
            decline_attacks: If True, decline "Really attack?" prompts instead of confirming

        Returns:
            Tuple of (messages collected, attack_declined) where attack_declined is True
            if an attack prompt was declined
        """
        messages = []
        attack_declined = False

        for _ in range(max_iterations):
            if not self._is_any_prompt():
                break

            # Handle --More-- first (most common)
            if self._is_more_prompt():
                more_msgs = self._dismiss_more_prompts(max_prompts=1)
                messages.extend(more_msgs)
                continue

            # Check for attack prompts before general y/n handling
            if decline_attacks and self._is_attack_prompt():
                decline_msgs = self._decline_attack_prompt()
                messages.extend(decline_msgs)
                attack_declined = True
                continue

            # Decline dangerous prompts (e.g. leaving dungeon) — always
            if self._is_dangerous_prompt():
                decline_msgs = self._decline_prompt()
                messages.extend(decline_msgs)
                continue

            # Auto-confirm y/n prompts (but not menu selection prompts)
            if self._is_yn_prompt():
                yn_msgs = self._auto_confirm_yn_prompts(max_prompts=1)
                messages.extend(yn_msgs)
                continue

            # Escape from menu selection prompts (e.g., "What do you want to eat? [fgh or ?*]")
            if self._is_menu_prompt():
                esc_idx = self._get_action_idx(27)  # ESC
                if esc_idx is not None:
                    try:
                        obs, _, _, _, _ = self.env.step(esc_idx)
                        if obs:
                            msg = obs.get_message()
                            if msg:
                                messages.append(msg)
                    except Exception:
                        pass
                continue

            # Escape from getlin prompts (text input we can't handle)
            if self._is_getlin_prompt():
                esc_idx = self._get_action_idx(27)  # ESC
                if esc_idx is not None:
                    try:
                        obs, _, _, _, _ = self.env.step(esc_idx)
                        if obs:
                            msg = obs.get_message()
                            if msg:
                                messages.append(msg)
                    except Exception:
                        pass
                continue

            # Unknown prompt type - try escape as fallback
            obs = self.env.last_observation
            if obs and obs.in_yn_prompt:
                esc_idx = self._get_action_idx(27)  # ESC
                if esc_idx is not None:
                    try:
                        obs, _, _, _, _ = self.env.step(esc_idx)
                        if obs:
                            msg = obs.get_message()
                            if msg:
                                messages.append(msg)
                    except Exception:
                        pass
                continue

        return messages, attack_declined

    def _execute_single(
        self, char: int, handle_prompts: bool = True, decline_attacks: bool = False
    ) -> ActionResult:
        """
        Execute a single action by character code.

        Args:
            char: The character code to send
            handle_prompts: If True, auto-handle prompts before and after.
            decline_attacks: If True, decline "Really attack?" prompts instead of confirming.
                           Set to False when executing as part of a sequence
                           where prompts are expected (e.g., menu selections).
        """
        pre_messages = []
        attack_declined = False
        if handle_prompts:
            # Handle any pending prompts from previous actions
            pre_messages, _ = self._handle_all_prompts(decline_attacks=decline_attacks)

        idx = self._get_action_idx(char)
        if idx is None:
            return ActionResult.failure(f"Unknown action character: {chr(char)}")

        try:
            obs, reward, terminated, truncated, info = self.env.step(idx)
            message = obs.get_message() if obs else ""

            post_messages = []
            if handle_prompts:
                # Handle any prompts triggered by our action (auto-confirm y/n, dismiss --More--)
                post_messages, attack_declined = self._handle_all_prompts(
                    decline_attacks=decline_attacks
                )

            all_messages = pre_messages + ([message] if message else []) + post_messages

            # If we declined an attack, the action failed
            if attack_declined:
                return ActionResult(
                    success=False,
                    messages=all_messages,
                    turn_elapsed=False,
                    state_changed=False,
                )

            return ActionResult(
                success=True,
                messages=all_messages,
                turn_elapsed=True,
                state_changed=True,
            )
        except Exception as e:
            return ActionResult.failure(str(e))

    def _count_prefix(self, count: int) -> list[int]:
        """
        Build the character sequence for a count prefix.

        NetHack allows prefixing commands with a number (e.g., '20s' to search 20 times).
        The game handles interrupts automatically (monster appears, etc.).

        Args:
            count: The repeat count (1-99 typical, higher values allowed)

        Returns:
            List of character codes for the digits
        """
        if count <= 1:
            return []
        return [ord(c) for c in str(count)]

    def _execute_sequence(
        self, chars: list[int], decline_attacks: bool = False
    ) -> ActionResult:
        """
        Execute a sequence of actions.

        Prompt handling is disabled for intermediate steps (since prompts like
        "What do you want to eat?" are expected and need the next character as response).
        Prompts are only handled at the start (to clear any leftover state) and
        at the end (to handle any resulting prompts like --More--).

        Args:
            chars: List of character codes to execute
            decline_attacks: If True, decline "Really attack?" prompts instead of confirming
        """
        messages = []

        # Handle any leftover prompts before starting
        pre_messages, _ = self._handle_all_prompts(decline_attacks=decline_attacks)
        messages.extend(pre_messages)

        # Execute each character without intermediate prompt handling
        for i, char in enumerate(chars):
            is_last = i == len(chars) - 1
            # Only handle prompts on the last step
            result = self._execute_single(char, handle_prompts=False)
            if result.messages:
                messages.extend(result.messages)
            if not result.success:
                result.messages = messages
                return result

        # Handle any prompts triggered by the sequence (e.g., --More--, y/n confirmations)
        post_messages, attack_declined = self._handle_all_prompts(
            decline_attacks=decline_attacks
        )
        messages.extend(post_messages)

        # If we declined an attack, the action failed
        if attack_declined:
            return ActionResult(
                success=False,
                messages=messages,
                turn_elapsed=False,
                state_changed=False,
            )

        return ActionResult(success=True, messages=messages)

    # ==================== Movement ====================

    def move(self, direction: Direction, count: int = 1) -> ActionResult:
        """
        Move in a direction.

        Uses NetHack's count prefix for multiple moves (e.g., '5l' moves east up to 5 times).
        The game automatically stops at walls, doorways, or if a monster appears.

        Args:
            direction: Direction to move (N, S, E, W, NE, NW, SE, SW)
            count: Number of tiles to move (default 1). Use higher counts to
                   travel quickly through known corridors.

        Returns:
            ActionResult indicating success/failure (success=True if position changed at all)
        """
        key = self._direction_keys.get(direction)
        if key is None:
            return ActionResult.failure(f"Invalid direction: {direction}")

        # Record position before move
        obs_before = self.env.last_observation
        pos_before = None
        if obs_before:
            pos_before = (obs_before.player_x, obs_before.player_y)

        # Execute with count prefix if count > 1
        # decline_attacks=True prevents accidentally attacking peaceful creatures
        prefix = self._count_prefix(count)
        if prefix:
            result = self._execute_sequence(prefix + [key], decline_attacks=True)
        else:
            result = self._execute_single(key, decline_attacks=True)

        # Check if position actually changed
        obs_after = self.env.last_observation
        if obs_after and pos_before:
            pos_after = (obs_after.player_x, obs_after.player_y)
            if pos_before == pos_after:
                # Position didn't change - move failed (hit wall, etc.)
                result.success = False
                result.turn_elapsed = False

        return result

    def run(self, direction: Direction) -> ActionResult:
        """
        Run in a direction until interrupted.

        Uses NetHack's 'g' (go) prefix which runs until:
        - Hitting a wall or obstacle
        - Reaching an intersection or doorway
        - Seeing a monster or other interesting feature
        - Taking damage

        This is faster than move() with count for long-distance travel through
        known safe corridors, and safer because NetHack handles all interrupts.

        Args:
            direction: Direction to run (N, S, E, W, NE, NW, SE, SW)

        Returns:
            ActionResult indicating success/failure (success=True if position changed)
        """
        key = self._direction_keys.get(direction)
        if key is None:
            return ActionResult.failure(f"Invalid direction: {direction}")

        # Record position before running
        obs_before = self.env.last_observation
        pos_before = None
        if obs_before:
            pos_before = (obs_before.player_x, obs_before.player_y)

        # Use 'g' prefix for running (more reliable than capital letters)
        # decline_attacks=True prevents accidentally attacking peaceful creatures
        result = self._execute_sequence([ord("g"), key], decline_attacks=True)

        # Check if position actually changed
        obs_after = self.env.last_observation
        if obs_after and pos_before:
            pos_after = (obs_after.player_x, obs_after.player_y)
            if pos_before == pos_after:
                # Position didn't change - immediately hit wall
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

    def _is_pickup_menu(self) -> tuple[bool, list[str]]:
        """Check if the game is showing a 'Pick up what?' menu.

        Returns:
            (is_menu, item_lines) - True if in pickup menu, plus list of item descriptions
        """
        obs = self.env.last_observation
        if obs is None:
            return False, []

        screen = obs.get_screen()
        if "Pick up what?" not in screen:
            return False, []

        # Extract item lines from the menu (format: "a - item name")
        items = []
        for line in screen.split("\n"):
            line = line.strip()
            # Match pattern like "a - an orcish helm" or "b - a hobgoblin corpse"
            if len(line) >= 4 and line[1:4] == " - " and line[0].isalpha():
                items.append(line)

        return True, items

    def pickup(self, item_letter: Optional[str] = None) -> ActionResult:
        """
        Pick up items from the ground.

        With no arguments, picks up all items on the tile.
        With an item letter, picks up just that item from a multi-item pile.

        Args:
            item_letter: If specified, pick up that specific item from a pile.

        Returns:
            ActionResult
        """
        if item_letter:
            # Pick up specific item from pile: comma opens menu, letter selects, enter confirms
            return self._execute_sequence([ord(","), ord(item_letter), ord("\r")])

        # Send comma to initiate pickup
        idx = self._get_action_idx(ord(","))
        if idx is None:
            return ActionResult.failure("Pickup action not available")

        try:
            obs, reward, terminated, truncated, info = self.env.step(idx)
            message = obs.get_message() if obs else ""

            # Check if we're now in a pickup menu (multiple items)
            is_menu, items = self._is_pickup_menu()
            if is_menu:
                # Select all items with comma, then confirm with Enter
                comma_idx = self._get_action_idx(ord(","))
                enter_idx = self._get_action_idx(13)
                if comma_idx is not None and enter_idx is not None:
                    self.env.step(comma_idx)  # select all
                    obs, _, _, _, _ = self.env.step(enter_idx)  # confirm
                    message = obs.get_message() if obs else ""

                # Dismiss any --More-- prompts from pickup messages
                post_messages = self._dismiss_more_prompts()
                all_messages = ([message] if message else []) + post_messages
                return ActionResult(
                    success=True,
                    messages=all_messages,
                    turn_elapsed=True,
                    state_changed=True,
                )

            # Single item or no items - pickup completed normally
            post_messages = self._dismiss_more_prompts()
            all_messages = ([message] if message else []) + post_messages

            return ActionResult(
                success=True,
                messages=all_messages,
                turn_elapsed=True,
                state_changed=True,
            )
        except Exception as e:
            return ActionResult.failure(str(e))

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

    def wait(self, count: int = 1) -> ActionResult:
        """
        Wait/rest in place.

        Uses NetHack's count prefix for multiple waits (e.g., '10.' waits up to 10 turns).
        The game automatically interrupts if a monster appears or attacks.

        Args:
            count: Number of turns to wait (default 1). Use count=10 or count=20
                   to rest for multiple turns safely.

        Returns:
            ActionResult with messages from the wait period.
        """
        prefix = self._count_prefix(count)
        if prefix:
            return self._execute_sequence(prefix + [ord(".")])
        return self._execute_single(ord("."))

    def search(self, count: int = 1) -> ActionResult:
        """
        Search adjacent squares for secret doors and traps.

        Uses NetHack's count prefix for multiple searches (e.g., '20s' searches up to 20 times).
        The game automatically interrupts if a monster appears or attacks.

        Args:
            count: Number of times to search (default 1). Use count=20 to thoroughly
                   search an area. Secret doors typically require 10-20 searches to find.

        Returns:
            ActionResult with messages (e.g., "You find a hidden door!")
        """
        prefix = self._count_prefix(count)
        if prefix:
            return self._execute_sequence(prefix + [ord("s")])
        return self._execute_single(ord("s"))

    def rest(self, count: int = 1) -> ActionResult:
        """
        Rest in place (synonym for wait).

        Args:
            count: Number of turns to rest (default 1).

        Returns:
            ActionResult
        """
        return self.wait(count)

    def pay(self) -> ActionResult:
        """Pay a shopkeeper for items ('p' command)."""
        return self._execute_single(ord("p"))

    def pray(self) -> ActionResult:
        """Pray to your deity."""
        # Note: 'p' is PAY (pay shopkeeper), PRAY is a separate extended command
        # The "Are you sure you want to pray? [yn]" prompt is auto-confirmed
        return self._execute_single(nethack.Command.PRAY)

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
        messages: list[str] = []

        # Clear any pre-existing prompts
        pre_msgs, _ = self._handle_all_prompts()
        messages.extend(pre_msgs)

        # Send E to start engraving, then - to select finger.
        # All sent with handle_prompts=False because the engrave dialog
        # involves a chain of prompts (menu, yn, getlin) that we must
        # navigate manually — _handle_all_prompts would ESC the getlin.
        for char in [ord("E"), ord("-")]:
            result = self._execute_single(char, handle_prompts=False)
            if result.messages:
                messages.extend(result.messages)
            if not result.success:
                result.messages = messages
                return result

        # Handle intermediate prompts before text input.
        # If there's an existing engraving, NetHack asks "Do you want to add
        # to it? [ynq]" — a y/n prompt that would swallow the first text char.
        # There may also be --More-- prompts to dismiss.
        # Do NOT use _handle_all_prompts — it would ESC the getlin prompt.
        for _ in range(10):
            if self._is_more_prompt():
                more_msgs = self._dismiss_more_prompts(max_prompts=1)
                messages.extend(more_msgs)
            elif self._is_yn_prompt() and not self._is_menu_prompt():
                yn_msgs = self._auto_confirm_yn_prompts(max_prompts=1)
                messages.extend(yn_msgs)
            else:
                break

        # Send text characters + Enter. Game should be in getlin mode now.
        for c in text:
            result = self._execute_single(ord(c), handle_prompts=False)
            if result.messages:
                messages.extend(result.messages)
        result = self._execute_single(13, handle_prompts=False)
        if result.messages:
            messages.extend(result.messages)

        # Clear any remaining prompts
        cleanup_msgs, _ = self._handle_all_prompts()
        messages.extend(cleanup_msgs)

        return ActionResult(success=True, messages=messages)

    # ==================== Raw ====================

    def send_keys(self, keys: str) -> ActionResult:
        """
        Send raw keystrokes.

        Args:
            keys: String of keys to send (newlines are converted to carriage returns)

        Returns:
            ActionResult
        """
        # Convert \n to \r (Enter key) since NLE doesn't recognize \n
        keys = keys.replace('\n', '\r')
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
        """
        Send 'y' for yes confirmation.

        IMPORTANT: Only sends 'y' if there's an active [yn] prompt.
        This prevents accidental movement since 'y' is also the NW direction key.
        Returns success=False if no prompt is active.
        """
        if not self._is_yn_prompt():
            return ActionResult(
                success=False,
                messages=["No confirmation prompt active"],
                turn_elapsed=False,
                state_changed=False,
            )
        return self._execute_single(ord("y"))

    def deny(self) -> ActionResult:
        """
        Send 'n' for no confirmation.

        IMPORTANT: Only sends 'n' if there's an active [yn] prompt.
        This prevents accidental movement since 'n' is also the SE direction key.
        Returns success=False if no prompt is active.
        """
        if not self._is_yn_prompt():
            return ActionResult(
                success=False,
                messages=["No confirmation prompt active"],
                turn_elapsed=False,
                state_changed=False,
            )
        return self._execute_single(ord("n"))

    def space(self) -> ActionResult:
        """Send space (continue/dismiss message)."""
        return self._execute_single(ord(" "))

    # ==================== Screen Capture ====================

    def get_overview_screen(self) -> str:
        """
        Execute #overview and capture the paged screen output.

        This is a free action (doesn't consume a game turn). Uses a screen
        diff approach: compares tty_chars before and after the command to
        isolate the overview text from the underlying game map.
        Returns empty string if the command is not available.
        """
        import numpy as np

        # Clear pending prompts
        self._handle_all_prompts()

        # Send the #overview command
        idx = self._get_action_idx(nethack.Command.OVERVIEW)
        if idx is None:
            return ""

        # Snapshot the screen before the overlay
        pre_obs = self.env.last_observation
        if pre_obs is None:
            return ""
        base_chars = pre_obs.tty_chars.copy()

        try:
            self.env.step(idx)
        except Exception:
            return ""

        # Capture overview text from each page by diffing against
        # the base game screen. The overview is rendered as an overlay,
        # so changed characters are the overview text.
        overview_lines = []
        space_idx = self._get_action_idx(ord(" "))

        for _ in range(10):  # max pages
            obs = self.env.last_observation
            if obs is None or not obs.in_more_prompt:
                break

            # Find characters that differ from the base screen
            diff_mask = obs.tty_chars != base_chars
            for row in range(24):
                if not diff_mask[row].any():
                    continue
                # Extract the changed portion of this row
                changed_cols = np.where(diff_mask[row])[0]
                start = int(changed_cols[0])
                end = int(changed_cols[-1]) + 1
                text = bytes(obs.tty_chars[row, start:end]).decode(
                    "latin-1", errors="replace"
                ).strip()
                if text and "--More--" not in text:
                    overview_lines.append(text)

            # Advance past --More--
            if space_idx is not None:
                self.env.step(space_idx)
            else:
                break

        # Dismiss if still in a prompt (ESC to close)
        obs = self.env.last_observation
        if obs and obs.in_any_prompt:
            esc_idx = self._get_action_idx(27)
            if esc_idx is not None:
                self.env.step(esc_idx)

        return "\n".join(overview_lines)
