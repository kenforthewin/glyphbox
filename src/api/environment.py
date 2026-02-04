"""
NLE Environment wrapper.

Provides a clean interface to the NetHack Learning Environment with
proper observation parsing and action handling.
"""

import logging
from dataclasses import dataclass
from typing import Any, Optional

import gymnasium as gym
import numpy as np

logger = logging.getLogger(__name__)

# NLE observation keys we need for the agent
OBSERVATION_KEYS = (
    "glyphs",  # 21x79 grid of glyph IDs
    "chars",  # 21x79 grid of ASCII characters
    "colors",  # 21x79 grid of color codes
    "specials",  # 21x79 grid of special attributes
    "blstats",  # Bottom-line stats (HP, AC, etc.)
    "message",  # Game messages
    "misc",  # Prompt state flags: [in_yn_function, in_getlin, xwaitforspace]
    "inv_glyphs",  # Inventory glyph IDs
    "inv_strs",  # Inventory item strings
    "inv_letters",  # Inventory slot letters
    "inv_oclasses",  # Inventory object classes
    "tty_chars",  # Full terminal output (24x80)
    "tty_colors",  # Terminal colors
    "tty_cursor",  # Cursor position
    "screen_descriptions",  # Text descriptions per tile
)

# Indices into blstats array
BLSTAT_X = 0
BLSTAT_Y = 1
BLSTAT_STR25 = 2
BLSTAT_STR125 = 3
BLSTAT_DEX = 4
BLSTAT_CON = 5
BLSTAT_INT = 6
BLSTAT_WIS = 7
BLSTAT_CHA = 8
BLSTAT_SCORE = 9
BLSTAT_HP = 10
BLSTAT_HPMAX = 11
BLSTAT_DEPTH = 12
BLSTAT_GOLD = 13
BLSTAT_ENE = 14  # Power/Mana
BLSTAT_ENEMAX = 15
BLSTAT_AC = 16
BLSTAT_HD = 17  # Hit dice (monster level)
BLSTAT_XP = 18
BLSTAT_EXP = 19
BLSTAT_TIME = 20
BLSTAT_HUNGER = 21
BLSTAT_CAP = 22  # Carrying capacity
BLSTAT_DNUM = 23  # Dungeon number
BLSTAT_DLEVEL = 24  # Dungeon level
BLSTAT_CONDITION = 25
BLSTAT_ALIGN = 26


@dataclass
class Observation:
    """Parsed NLE observation."""

    # Map data
    glyphs: np.ndarray  # (21, 79) int16
    chars: np.ndarray  # (21, 79) uint8
    colors: np.ndarray  # (21, 79) uint8
    specials: np.ndarray  # (21, 79) uint8

    # Player stats
    blstats: np.ndarray  # (27,) int64

    # Messages
    message: bytes  # Raw message bytes

    # Prompt state flags from NLE misc observation
    # misc[0] = in_yn_function: game waiting for single char (y/n, menu letter)
    # misc[1] = in_getlin: game waiting for text input (e.g., engrave text)
    # misc[2] = xwaitforspace: game waiting for space/enter (--More--, menus)
    misc: np.ndarray  # (3,) prompt state flags

    # Inventory
    inv_glyphs: np.ndarray
    inv_strs: np.ndarray
    inv_letters: np.ndarray
    inv_oclasses: np.ndarray

    # Terminal
    tty_chars: np.ndarray  # (24, 80) uint8
    tty_colors: np.ndarray  # (24, 80) int8
    tty_cursor: np.ndarray  # (2,) cursor position

    # Descriptions
    screen_descriptions: np.ndarray  # (21, 79, 80) per-tile descriptions

    @property
    def player_x(self) -> int:
        """Player X position."""
        return int(self.blstats[BLSTAT_X])

    @property
    def player_y(self) -> int:
        """Player Y position."""
        return int(self.blstats[BLSTAT_Y])

    @property
    def hp(self) -> int:
        """Current HP."""
        return int(self.blstats[BLSTAT_HP])

    @property
    def max_hp(self) -> int:
        """Maximum HP."""
        return int(self.blstats[BLSTAT_HPMAX])

    @property
    def dungeon_level(self) -> int:
        """Current dungeon level."""
        return int(self.blstats[BLSTAT_DLEVEL])

    @property
    def turn(self) -> int:
        """Current game turn."""
        return int(self.blstats[BLSTAT_TIME])

    @property
    def score(self) -> int:
        """Current score."""
        return int(self.blstats[BLSTAT_SCORE])

    @property
    def in_yn_prompt(self) -> bool:
        """True if game is waiting for a single character response (y/n, menu letter)."""
        return bool(self.misc[0])

    @property
    def in_getlin_prompt(self) -> bool:
        """True if game is waiting for text input (e.g., engrave text, wish)."""
        return bool(self.misc[1])

    @property
    def in_more_prompt(self) -> bool:
        """True if game is waiting for space/enter to continue (--More--, menus)."""
        return bool(self.misc[2])

    @property
    def in_any_prompt(self) -> bool:
        """True if game is in any prompt state that requires input to continue."""
        return self.in_yn_prompt or self.in_getlin_prompt or self.in_more_prompt

    def get_message(self) -> str:
        """Get decoded message string."""
        # Message is null-terminated bytes
        msg_bytes = bytes(self.message)
        null_idx = msg_bytes.find(b"\x00")
        if null_idx >= 0:
            msg_bytes = msg_bytes[:null_idx]
        return msg_bytes.decode("latin-1", errors="replace").strip()

    def get_screen(self) -> str:
        """Get ASCII representation of the screen as a single string."""
        return "\n".join(self.get_screen_lines())

    def get_screen_lines(self) -> list[str]:
        """Get ASCII screen as a list of 24 strings (one per row)."""
        lines = []
        for row in self.tty_chars:
            line = bytes(row).decode("latin-1", errors="replace").rstrip()
            lines.append(line)
        return lines

    def get_screen_colors_base64(self) -> str:
        """Get tty_colors as a base64-encoded string (24x80 = 1920 bytes -> 2560 chars)."""
        import base64

        return base64.b64encode(self.tty_colors.astype(np.uint8).tobytes()).decode("ascii")


class NLEWrapper:
    """
    Wrapper around the NetHack Learning Environment.

    Provides a cleaner interface for the agent to interact with the game.
    """

    def __init__(
        self,
        env_name: str = "NetHackChallenge-v0",
        max_episode_steps: int = 1_000_000,
        render_mode: Optional[str] = None,
        character: str = "val-hum-fem-law",
    ):
        """
        Initialize the NLE wrapper.

        Args:
            env_name: Name of the gymnasium environment
            max_episode_steps: Maximum steps per episode
            render_mode: Render mode ("human", "ansi", or None)
            character: NetHack character spec (e.g. "random", "val-hum-fem-law")
        """
        self.env_name = env_name
        self.max_episode_steps = max_episode_steps
        self.render_mode = render_mode

        self._env: Optional[gym.Env] = None
        self._last_obs: Optional[Observation] = None
        self._done: bool = True
        self._episode_step: int = 0
        self._total_reward: float = 0.0
        self._character: str = character

        logger.info(f"NLEWrapper initialized with env={env_name}")

    def _create_env(self) -> gym.Env:
        """Create and configure the NLE environment."""
        try:
            import nle  # noqa: F401 - needed for gym registration

            # Custom options: disable autopickup so agent makes explicit pickup decisions
            # Based on nle.nethack.NETHACKOPTIONS but with !autopickup
            options = (
                "!autopickup",  # Disable auto pickup - agent should decide what to pick up
                "color",
                "disclose:+i +a +v +g +c +o",
                "mention_walls",
                "nobones",
                "nocmdassist",
                "nolegacy",
                "nosparkle",
                "runmode:teleport",
                "showexp",
                "showscore",
                "time",
            )

            env = gym.make(
                self.env_name,
                observation_keys=OBSERVATION_KEYS,
                max_episode_steps=self.max_episode_steps,
                allow_all_yn_questions=True,
                allow_all_modes=True,
                render_mode=self.render_mode,
                options=options,
                character=self._character,
            )
            return env
        except Exception as e:
            logger.error(f"Failed to create NLE environment: {e}")
            raise

    def _parse_observation(self, obs: dict[str, Any]) -> Observation:
        """Parse raw NLE observation into Observation dataclass."""
        return Observation(
            glyphs=obs["glyphs"],
            chars=obs["chars"],
            colors=obs["colors"],
            specials=obs["specials"],
            blstats=obs["blstats"],
            message=obs["message"],
            misc=obs["misc"],
            inv_glyphs=obs["inv_glyphs"],
            inv_strs=obs["inv_strs"],
            inv_letters=obs["inv_letters"],
            inv_oclasses=obs["inv_oclasses"],
            tty_chars=obs["tty_chars"],
            tty_colors=obs["tty_colors"],
            tty_cursor=obs["tty_cursor"],
            screen_descriptions=obs["screen_descriptions"],
        )

    def reset(self) -> Observation:
        """
        Reset the environment and start a new episode.

        Returns:
            Initial observation
        """
        if self._env is None:
            self._env = self._create_env()

        obs, info = self._env.reset()
        self._last_obs = self._parse_observation(obs)
        self._done = False
        self._episode_step = 0
        self._total_reward = 0.0

        logger.info("Episode started")
        return self._last_obs

    def step(self, action: int) -> tuple[Observation, float, bool, bool, dict[str, Any]]:
        """
        Take a step in the environment.

        Args:
            action: Action index to execute

        Returns:
            Tuple of (observation, reward, terminated, truncated, info)
        """
        if self._env is None or self._done:
            raise RuntimeError("Environment not initialized or episode ended. Call reset() first.")

        obs, reward, terminated, truncated, info = self._env.step(action)
        self._last_obs = self._parse_observation(obs)
        self._done = terminated or truncated
        self._episode_step += 1
        self._total_reward += reward

        if self._done:
            logger.info(
                f"Episode ended: steps={self._episode_step}, "
                f"score={self._last_obs.score}, reward={self._total_reward}"
            )

        return self._last_obs, reward, terminated, truncated, info

    def render(self) -> Optional[str]:
        """Render the current game state."""
        if self._env is not None:
            return self._env.render()
        return None

    def close(self) -> None:
        """Close the environment."""
        if self._env is not None:
            self._env.close()
            self._env = None
            logger.info("Environment closed")

    @property
    def last_observation(self) -> Optional[Observation]:
        """Get the last observation."""
        return self._last_obs

    @property
    def is_done(self) -> bool:
        """Check if the episode has ended."""
        return self._done

    @property
    def episode_step(self) -> int:
        """Get the current episode step count."""
        return self._episode_step

    @property
    def action_space(self) -> gym.Space:
        """Get the action space."""
        if self._env is None:
            self._env = self._create_env()
        return self._env.action_space

    def get_action_meanings(self) -> list[str]:
        """Get human-readable action names."""
        if self._env is None:
            self._env = self._create_env()
        # NLE provides action meanings
        if hasattr(self._env, "get_action_meanings"):
            return self._env.get_action_meanings()
        return [f"action_{i}" for i in range(self.action_space.n)]

    @property
    def role(self) -> str:
        """Get the player's role (class) name."""
        # Map character codes to full role names
        role_map = {
            "arc": "Archeologist",
            "bar": "Barbarian",
            "cav": "Caveman",
            "hea": "Healer",
            "kni": "Knight",
            "mon": "Monk",
            "pri": "Priest",
            "ran": "Ranger",
            "rog": "Rogue",
            "sam": "Samurai",
            "tou": "Tourist",
            "val": "Valkyrie",
            "wiz": "Wizard",
        }
        # Character string format: "role-race-gender-alignment" e.g. "val-hum-fem-law"
        role_code = self._character.split("-")[0].lower()
        return role_map.get(role_code, "Unknown")

    def __enter__(self) -> "NLEWrapper":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()
