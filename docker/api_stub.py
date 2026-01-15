"""
API stub for sandbox - forwards calls to proxy server.

This module runs inside the Docker container and provides a NetHackAPI-like
interface that forwards all calls to the proxy server via Unix socket.
"""

import json
import socket
from dataclasses import dataclass, field
from typing import Any, Optional

SOCKET_PATH = "/sandbox/api.sock"


@dataclass
class SkillResult:
    """Result returned by a skill execution."""

    stopped_reason: str
    data: dict = field(default_factory=dict)
    actions_taken: int = 0
    turns_elapsed: int = 0
    success: bool = False

    @classmethod
    def stopped(
        cls,
        reason: str,
        success: bool = False,
        actions: int = 0,
        turns: int = 0,
        **data,
    ) -> "SkillResult":
        """Create a skill result."""
        return cls(
            stopped_reason=reason,
            success=success,
            actions_taken=actions,
            turns_elapsed=turns,
            data=data,
        )


@dataclass
class Position:
    """Position wrapper for API responses."""

    x: int
    y: int

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> Optional["Position"]:
        if d is None:
            return None
        return cls(x=d["x"], y=d["y"])


class APIStub:
    """Client stub that forwards API calls to the proxy."""

    def __init__(self):
        self._socket: Optional[socket.socket] = None
        self._request_id = 0

    def _connect(self):
        """Connect to the API proxy socket."""
        if self._socket is None:
            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._socket.connect(SOCKET_PATH)

    def _send(self, method: str, **params) -> Any:
        """Send an RPC request and return the result."""
        self._connect()
        self._request_id += 1

        # Build request
        request = {
            "id": self._request_id,
            "method": method,
            "params": params,
        }

        # Send with length prefix
        data = json.dumps(request).encode("utf-8")
        self._socket.sendall(len(data).to_bytes(4, "big") + data)

        # Read response length
        length_bytes = self._socket.recv(4)
        if len(length_bytes) < 4:
            raise RuntimeError("Connection closed by proxy")
        length = int.from_bytes(length_bytes, "big")

        # Read response body
        response_data = b""
        while len(response_data) < length:
            chunk = self._socket.recv(length - len(response_data))
            if not chunk:
                raise RuntimeError("Connection closed by proxy")
            response_data += chunk

        response = json.loads(response_data.decode("utf-8"))

        if "error" in response and response["error"]:
            raise RuntimeError(f"API error: {response['error']}")

        return response.get("result")

    # ==================== State Queries ====================

    def get_stats(self) -> dict:
        """Get current player statistics."""
        return self._send("get_stats")

    def get_position(self) -> Optional[Position]:
        """Get player's current position."""
        result = self._send("get_position")
        return Position.from_dict(result)

    def get_screen(self) -> str:
        """Get the raw ASCII screen."""
        return self._send("get_screen")

    def get_message(self) -> str:
        """Get the current game message."""
        return self._send("get_message")

    def get_inventory(self) -> list[dict]:
        """Get current inventory."""
        return self._send("get_inventory")

    def get_visible_monsters(self) -> list[dict]:
        """Get all monsters currently visible."""
        return self._send("get_visible_monsters")

    def get_adjacent_monsters(self) -> list[dict]:
        """Get monsters in the 8 adjacent tiles."""
        return self._send("get_adjacent_monsters")

    def get_hostile_monsters(self) -> list[dict]:
        """Get only hostile monsters."""
        return self._send("get_hostile_monsters")

    def get_items_here(self) -> list[dict]:
        """Get items at player's current position."""
        return self._send("get_items_here")

    def get_food(self) -> list[dict]:
        """Get food items from inventory."""
        return self._send("get_food")

    def get_weapons(self) -> list[dict]:
        """Get weapons from inventory."""
        return self._send("get_weapons")

    def find_stairs(self) -> dict:
        """Find stairs up and down positions."""
        return self._send("find_stairs")

    @property
    def is_done(self) -> bool:
        """Check if the episode has ended."""
        return self._send("is_done")

    @property
    def turn(self) -> int:
        """Get the current game turn."""
        return self._send("turn")

    # ==================== Actions ====================

    def move(self, direction: str) -> dict:
        """Move in a direction."""
        return self._send("move", direction=direction)

    def attack(self, direction: str) -> dict:
        """Attack in a direction."""
        return self._send("attack", direction=direction)

    def kick(self, direction: str) -> dict:
        """Kick in a direction."""
        return self._send("kick", direction=direction)

    def wait(self) -> dict:
        """Wait one turn."""
        return self._send("wait")

    def search(self) -> dict:
        """Search adjacent tiles."""
        return self._send("search")

    def pickup(self, item_letter: Optional[str] = None) -> dict:
        """Pick up items."""
        return self._send("pickup", item_letter=item_letter)

    def drop(self, item_letter: str) -> dict:
        """Drop an item."""
        return self._send("drop", item_letter=item_letter)

    def eat(self, item_letter: Optional[str] = None) -> dict:
        """Eat food."""
        return self._send("eat", item_letter=item_letter)

    def quaff(self, item_letter: str) -> dict:
        """Drink a potion."""
        return self._send("quaff", item_letter=item_letter)

    def read(self, item_letter: str) -> dict:
        """Read a scroll or spellbook."""
        return self._send("read", item_letter=item_letter)

    def wear(self, item_letter: str) -> dict:
        """Wear armor."""
        return self._send("wear", item_letter=item_letter)

    def wield(self, item_letter: str) -> dict:
        """Wield a weapon."""
        return self._send("wield", item_letter=item_letter)

    def open_door(self, direction: str) -> dict:
        """Open a door."""
        return self._send("open_door", direction=direction)

    def go_up(self) -> dict:
        """Ascend stairs."""
        return self._send("go_up")

    def go_down(self) -> dict:
        """Descend stairs."""
        return self._send("go_down")

    def pray(self) -> dict:
        """Pray to your deity."""
        return self._send("pray")

    def engrave(self, text: str = "Elbereth") -> dict:
        """Engrave text on the floor."""
        return self._send("engrave", text=text)

    # ==================== Pathfinding ====================

    def find_path(
        self,
        x: int,
        y: int,
        avoid_monsters: bool = True,
        avoid_traps: bool = True,
    ) -> list[str]:
        """Find path to a target position."""
        return self._send(
            "find_path",
            x=x,
            y=y,
            avoid_monsters=avoid_monsters,
            avoid_traps=avoid_traps,
        )

    def find_unexplored(self) -> Optional[Position]:
        """Find nearest unexplored walkable tile."""
        result = self._send("find_unexplored")
        return Position.from_dict(result)

    def find_stairs_up(self) -> Optional[Position]:
        """Find stairs up position."""
        result = self._send("find_stairs_up")
        return Position.from_dict(result)

    def find_stairs_down(self) -> Optional[Position]:
        """Find stairs down position."""
        result = self._send("find_stairs_down")
        return Position.from_dict(result)

    def find_nearest_monster(self) -> Optional[Position]:
        """Find nearest hostile monster."""
        result = self._send("find_nearest_monster")
        return Position.from_dict(result)

    # ==================== Knowledge ====================

    def lookup_monster(self, name: str) -> Optional[dict]:
        """Look up monster information."""
        return self._send("lookup_monster", name=name)

    def is_dangerous_melee(self, name: str) -> bool:
        """Check if monster is dangerous to attack in melee."""
        return self._send("is_dangerous_melee", name=name)

    def is_corpse_safe(self, name: str) -> bool:
        """Check if monster corpse is safe to eat."""
        return self._send("is_corpse_safe", name=name)

    def is_prayer_safe(self) -> bool:
        """Check if prayer timeout has passed."""
        return self._send("is_prayer_safe")

    def close(self):
        """Close the connection."""
        if self._socket:
            self._socket.close()
            self._socket = None


# Create global instance for skill code to use
nh = APIStub()
