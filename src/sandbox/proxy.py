"""
API proxy for sandbox communication.

This module provides:
1. APIProxy - Server-side proxy that runs outside the sandbox and handles API calls
2. APIStub - Client-side stub that runs inside the sandbox and forwards calls

Communication uses JSON-RPC style messages over Unix domain sockets.
"""

import asyncio
import json
import logging
import os
import socket
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .exceptions import SandboxCommunicationError

logger = logging.getLogger(__name__)

# Message format version
PROTOCOL_VERSION = 1

# Maximum message size (1MB)
MAX_MESSAGE_SIZE = 1024 * 1024


@dataclass
class RPCRequest:
    """JSON-RPC style request."""

    id: int
    method: str
    params: dict[str, Any]


@dataclass
class RPCResponse:
    """JSON-RPC style response."""

    id: int
    result: Optional[Any] = None
    error: Optional[str] = None


def encode_message(data: dict) -> bytes:
    """Encode a message for transmission."""
    json_data = json.dumps(data).encode("utf-8")
    # Prefix with 4-byte length
    length = len(json_data)
    return length.to_bytes(4, "big") + json_data


def decode_message(data: bytes) -> dict:
    """Decode a received message."""
    return json.loads(data.decode("utf-8"))


async def read_message(reader: asyncio.StreamReader) -> Optional[dict]:
    """Read a length-prefixed JSON message from stream."""
    try:
        # Read 4-byte length prefix
        length_bytes = await reader.readexactly(4)
        length = int.from_bytes(length_bytes, "big")

        if length > MAX_MESSAGE_SIZE:
            raise SandboxCommunicationError(f"Message too large: {length} bytes")

        # Read message body
        data = await reader.readexactly(length)
        return decode_message(data)

    except asyncio.IncompleteReadError:
        return None
    except Exception as e:
        logger.error(f"Error reading message: {e}")
        return None


async def write_message(writer: asyncio.StreamWriter, data: dict) -> None:
    """Write a length-prefixed JSON message to stream."""
    encoded = encode_message(data)
    writer.write(encoded)
    await writer.drain()


class APIProxy:
    """
    Server-side API proxy that handles calls from sandbox.

    This runs outside the sandbox and receives API calls from the
    sandboxed skill code, executes them against the real NetHackAPI,
    and returns results.

    Example usage:
        api = NetHackAPI()
        api.reset()

        proxy = APIProxy(api)
        await proxy.serve("/tmp/api.sock")
    """

    def __init__(self, api: Any):
        """
        Initialize the proxy.

        Args:
            api: NetHackAPI instance to proxy calls to
        """
        self.api = api
        self._server: Optional[asyncio.Server] = None
        self._running = False
        self._request_count = 0

        # Build method dispatch table
        self._methods = self._build_method_table()

    def _build_method_table(self) -> dict[str, Callable]:
        """Build dispatch table for API methods."""
        methods = {}

        # State query methods
        methods["get_stats"] = lambda: self._serialize_stats(self.api.get_stats())
        methods["get_position"] = lambda: self._serialize_position(self.api.get_position())
        methods["get_screen"] = lambda: self.api.get_screen()
        methods["get_message"] = lambda: self.api.get_message()
        methods["get_inventory"] = lambda: [self._serialize_item(i) for i in self.api.get_inventory()]
        methods["get_visible_monsters"] = lambda: [
            self._serialize_monster(m) for m in self.api.get_visible_monsters()
        ]
        methods["get_adjacent_monsters"] = lambda: [
            self._serialize_monster(m) for m in self.api.get_adjacent_monsters()
        ]
        methods["get_hostile_monsters"] = lambda: [
            self._serialize_monster(m) for m in self.api.get_hostile_monsters()
        ]
        methods["get_items_here"] = lambda: [self._serialize_item(i) for i in self.api.get_items_here()]
        methods["get_food"] = lambda: [self._serialize_item(i) for i in self.api.get_food()]
        methods["get_weapons"] = lambda: [self._serialize_item(i) for i in self.api.get_weapons()]
        methods["find_stairs"] = lambda: self._serialize_stairs(self.api.find_stairs())
        methods["is_done"] = lambda: self.api.is_done
        methods["turn"] = lambda: self.api.turn

        # Action methods
        methods["move"] = lambda direction: self._serialize_result(
            self.api.move(self._parse_direction(direction))
        )
        methods["attack"] = lambda direction: self._serialize_result(
            self.api.attack(self._parse_direction(direction))
        )
        methods["kick"] = lambda direction: self._serialize_result(
            self.api.kick(self._parse_direction(direction))
        )
        methods["wait"] = lambda: self._serialize_result(self.api.wait())
        methods["search"] = lambda: self._serialize_result(self.api.search())
        methods["pickup"] = lambda item_letter=None: self._serialize_result(
            self.api.pickup(item_letter)
        )
        methods["drop"] = lambda item_letter: self._serialize_result(
            self.api.drop(item_letter)
        )
        methods["eat"] = lambda item_letter=None: self._serialize_result(
            self.api.eat(item_letter)
        )
        methods["quaff"] = lambda item_letter: self._serialize_result(
            self.api.quaff(item_letter)
        )
        methods["read"] = lambda item_letter: self._serialize_result(
            self.api.read(item_letter)
        )
        methods["wear"] = lambda item_letter: self._serialize_result(
            self.api.wear(item_letter)
        )
        methods["wield"] = lambda item_letter: self._serialize_result(
            self.api.wield(item_letter)
        )
        methods["open_door"] = lambda direction: self._serialize_result(
            self.api.open_door(self._parse_direction(direction))
        )
        methods["go_up"] = lambda: self._serialize_result(self.api.go_up())
        methods["go_down"] = lambda: self._serialize_result(self.api.go_down())
        methods["pray"] = lambda: self._serialize_result(self.api.pray())
        methods["engrave"] = lambda text="Elbereth": self._serialize_result(
            self.api.engrave(text)
        )

        # Navigation methods
        methods["move_to"] = lambda x, y, allow_with_hostiles=False: self._serialize_result(
            self.api.move_to(self._make_position(x, y), allow_with_hostiles)
        )
        methods["find_unexplored"] = lambda: self._serialize_position(
            self.api.find_unexplored()
        )
        methods["find_stairs_up"] = lambda: self._serialize_position(
            self.api.find_stairs_up()
        )
        methods["find_stairs_down"] = lambda: self._serialize_position(
            self.api.find_stairs_down()
        )
        methods["find_nearest_monster"] = lambda: self._serialize_position(
            self.api.find_nearest_monster()
        )

        # Knowledge methods
        methods["lookup_monster"] = lambda name: self._serialize_monster_info(
            self.api.lookup_monster(name)
        )
        methods["is_dangerous_melee"] = lambda name: self.api.is_dangerous_melee(name)
        methods["is_corpse_safe"] = lambda name: self.api.is_corpse_safe(name)
        methods["is_prayer_safe"] = lambda: self.api.is_prayer_safe()

        return methods

    def _serialize_stats(self, stats) -> dict:
        """Serialize Stats to dict."""
        return {
            "hp": stats.hp,
            "max_hp": stats.max_hp,
            "pw": stats.pw,
            "max_pw": stats.max_pw,
            "ac": stats.ac,
            "xp_level": stats.xp_level,
            "xp_points": stats.xp_points,
            "gold": stats.gold,
            "strength": stats.strength,
            "dexterity": stats.dexterity,
            "constitution": stats.constitution,
            "intelligence": stats.intelligence,
            "wisdom": stats.wisdom,
            "charisma": stats.charisma,
            "hunger": stats.hunger.value,
            "encumbrance": stats.encumbrance.value,
            "alignment": stats.alignment.value,
            "dungeon_level": stats.dungeon_level,
            "dungeon_number": stats.dungeon_number,
            "turn": stats.turn,
            "score": stats.score,
            "position": self._serialize_position(stats.position),
        }

    def _serialize_position(self, pos) -> Optional[dict]:
        """Serialize Position to dict."""
        if pos is None:
            return None
        return {"x": pos.x, "y": pos.y}

    def _serialize_monster(self, monster) -> dict:
        """Serialize Monster to dict."""
        return {
            "glyph": monster.glyph,
            "char": monster.char,
            "name": monster.name,
            "position": self._serialize_position(monster.position),
            "color": monster.color,
            "is_peaceful": monster.is_peaceful,
            "is_tame": monster.is_tame,
            "is_hostile": monster.is_hostile,
            "threat_level": monster.threat_level,
        }

    def _serialize_item(self, item) -> dict:
        """Serialize Item to dict."""
        return {
            "glyph": item.glyph,
            "name": item.name,
            "char": item.char,
            "position": self._serialize_position(item.position),
            "slot": item.slot,
            "quantity": item.quantity,
            "buc_status": item.buc_status.value,
            "identified": item.identified,
            "object_class": item.object_class.value,
            "equipped": item.equipped,
            "is_weapon": item.is_weapon,
            "is_armor": item.is_armor,
            "is_food": item.is_food,
        }

    def _serialize_result(self, result) -> dict:
        """Serialize ActionResult to dict."""
        return {
            "success": result.success,
            "messages": result.messages,
            "turn_elapsed": result.turn_elapsed,
            "state_changed": result.state_changed,
            "error": result.error,
        }

    def _serialize_stairs(self, stairs_tuple) -> dict:
        """Serialize stairs tuple to dict."""
        up, down = stairs_tuple
        return {
            "up": self._serialize_position(up),
            "down": self._serialize_position(down),
        }

    def _serialize_monster_info(self, info) -> Optional[dict]:
        """Serialize MonsterInfo to dict."""
        if info is None:
            return None
        return {
            "name": info.name,
            "symbol": info.symbol,
            "difficulty": info.difficulty,
            "speed": info.speed,
            "ac": info.ac,
            "mr": info.mr,
            "attacks": info.attacks,
            "resistances": info.resistances,
            "flags": info.flags,
            "corpse_safe": info.corpse_safe,
            "corpse_effects": info.corpse_effects,
        }

    def _parse_direction(self, direction_str: str):
        """Parse direction string to Direction enum."""
        from src.api.models import Direction

        direction_map = {
            "n": Direction.N,
            "s": Direction.S,
            "e": Direction.E,
            "w": Direction.W,
            "ne": Direction.NE,
            "nw": Direction.NW,
            "se": Direction.SE,
            "sw": Direction.SW,
            "up": Direction.UP,
            "down": Direction.DOWN,
            "self": Direction.SELF,
        }
        return direction_map.get(direction_str.lower(), Direction.SELF)

    def _make_position(self, x: int, y: int):
        """Create Position from coordinates."""
        from src.api.models import Position

        return Position(x, y)

    async def serve(self, socket_path: str) -> None:
        """
        Start the proxy server.

        Args:
            socket_path: Path to Unix domain socket
        """
        # Remove existing socket if present
        if os.path.exists(socket_path):
            os.unlink(socket_path)

        self._running = True

        try:
            self._server = await asyncio.start_unix_server(
                self._handle_client,
                path=socket_path,
            )

            # Set socket permissions
            os.chmod(socket_path, 0o600)

            logger.info(f"API proxy listening on {socket_path}")

            async with self._server:
                await self._server.serve_forever()

        except asyncio.CancelledError:
            logger.info("API proxy shutting down")
        finally:
            self._running = False
            if os.path.exists(socket_path):
                os.unlink(socket_path)

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a client connection."""
        try:
            while self._running:
                message = await read_message(reader)
                if message is None:
                    break

                response = await self._handle_request(message)
                await write_message(writer, response)

        except Exception as e:
            logger.exception(f"Error handling client: {e}")
        finally:
            writer.close()
            await writer.wait_closed()

    async def _handle_request(self, message: dict) -> dict:
        """Handle a single RPC request."""
        request_id = message.get("id", 0)
        method = message.get("method", "")
        params = message.get("params", {})

        self._request_count += 1
        logger.debug(f"Request #{self._request_count}: {method}({params})")

        if method not in self._methods:
            return {
                "id": request_id,
                "error": f"Unknown method: {method}",
            }

        try:
            # Get the method
            handler = self._methods[method]

            # Call with params
            if isinstance(params, dict):
                result = handler(**params)
            elif isinstance(params, list):
                result = handler(*params)
            else:
                result = handler()

            return {
                "id": request_id,
                "result": result,
            }

        except Exception as e:
            logger.exception(f"Error executing {method}: {e}")
            return {
                "id": request_id,
                "error": str(e),
            }

    def stop(self) -> None:
        """Stop the proxy server."""
        self._running = False
        if self._server:
            self._server.close()


# API stub code that runs inside the sandbox
API_STUB_CODE = '''
"""
API stub for sandbox - forwards calls to proxy server.
"""
import json
import socket
import os

SOCKET_PATH = "/sandbox/api.sock"

class APIStub:
    """Client stub that forwards API calls to the proxy."""

    def __init__(self):
        self._socket = None
        self._request_id = 0

    def _connect(self):
        if self._socket is None:
            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._socket.connect(SOCKET_PATH)

    def _send(self, method: str, **params):
        self._connect()
        self._request_id += 1

        # Send request
        request = {
            "id": self._request_id,
            "method": method,
            "params": params,
        }
        data = json.dumps(request).encode("utf-8")
        self._socket.sendall(len(data).to_bytes(4, "big") + data)

        # Read response
        length_bytes = self._socket.recv(4)
        length = int.from_bytes(length_bytes, "big")
        response_data = self._socket.recv(length)
        response = json.loads(response_data.decode("utf-8"))

        if "error" in response and response["error"]:
            raise RuntimeError(f"API error: {response['error']}")

        return response.get("result")

    # State queries
    def get_stats(self):
        return self._send("get_stats")

    def get_position(self):
        return self._send("get_position")

    def get_screen(self):
        return self._send("get_screen")

    def get_screen_lines(self):
        return self._send("get_screen_lines")

    def get_message(self):
        return self._send("get_message")

    def get_inventory(self):
        return self._send("get_inventory")

    def get_visible_monsters(self):
        return self._send("get_visible_monsters")

    def get_adjacent_monsters(self):
        return self._send("get_adjacent_monsters")

    def get_hostile_monsters(self):
        return self._send("get_hostile_monsters")

    def get_items_here(self):
        return self._send("get_items_here")

    def get_items_on_map(self):
        return self._send("get_items_on_map")

    def get_food(self):
        return self._send("get_food")

    def get_weapons(self):
        return self._send("get_weapons")

    def find_stairs(self):
        return self._send("find_stairs")

    @property
    def is_done(self):
        return self._send("is_done")

    @property
    def turn(self):
        return self._send("turn")

    # Actions
    def move(self, direction):
        return self._send("move", direction=direction)

    def attack(self, direction):
        return self._send("attack", direction=direction)

    def kick(self, direction):
        return self._send("kick", direction=direction)

    def wait(self):
        return self._send("wait")

    def search(self):
        return self._send("search")

    def pickup(self, item_letter=None):
        return self._send("pickup", item_letter=item_letter)

    def drop(self, item_letter):
        return self._send("drop", item_letter=item_letter)

    def eat(self, item_letter=None):
        return self._send("eat", item_letter=item_letter)

    def quaff(self, item_letter):
        return self._send("quaff", item_letter=item_letter)

    def read(self, item_letter):
        return self._send("read", item_letter=item_letter)

    def wear(self, item_letter):
        return self._send("wear", item_letter=item_letter)

    def wield(self, item_letter):
        return self._send("wield", item_letter=item_letter)

    def open_door(self, direction):
        return self._send("open_door", direction=direction)

    def go_up(self):
        return self._send("go_up")

    def go_down(self):
        return self._send("go_down")

    def pray(self):
        return self._send("pray")

    def engrave(self, text="Elbereth"):
        return self._send("engrave", text=text)

    # Navigation
    def move_to(self, x, y, allow_with_hostiles=False):
        return self._send("move_to", x=x, y=y, allow_with_hostiles=allow_with_hostiles)

    def find_unexplored(self):
        return self._send("find_unexplored")

    def find_stairs_up(self):
        return self._send("find_stairs_up")

    def find_stairs_down(self):
        return self._send("find_stairs_down")

    def find_nearest_monster(self):
        return self._send("find_nearest_monster")

    def find_nearest_item(self):
        return self._send("find_nearest_item")

    # Knowledge
    def lookup_monster(self, name):
        return self._send("lookup_monster", name=name)

    def is_dangerous_melee(self, name):
        return self._send("is_dangerous_melee", name=name)

    def is_corpse_safe(self, name):
        return self._send("is_corpse_safe", name=name)

    def is_prayer_safe(self):
        return self._send("is_prayer_safe")

    def close(self):
        if self._socket:
            self._socket.close()
            self._socket = None


# Create global instance
nh = APIStub()
'''


def get_api_stub_code() -> str:
    """Get the API stub code for use inside sandbox."""
    return API_STUB_CODE
