# Self-Programming NetHack Agent Harness

## Implementation Specification v1.0

**Author:** Claude (Anthropic)  
**Date:** January 2026  
**Status:** Draft Specification

---

## Executive Summary

This document specifies a novel architecture for a NetHack-playing agent that dynamically generates its own behavioral skills through code synthesis. Unlike traditional hardcoded skill systems (e.g., NetPlay [1], AutoAscend [2]), this system allows the LLM agent to write, execute, and persist Python functions that implement "do X until Y" loops with arbitrarily complex trigger conditions.

The architecture draws inspiration from Anthropic's code execution with MCP approach [3], which demonstrates that LLM agents can interact more efficiently with external systems by writing code rather than making individual tool calls.

---

## Table of Contents

1. [Background and Motivation](#1-background-and-motivation)
2. [System Architecture](#2-system-architecture)
3. [NetHack Environment Layer](#3-nethack-environment-layer)
4. [NetHack API Design](#4-nethack-api-design)
5. [Code Execution Sandbox](#5-code-execution-sandbox)
6. [Skill System](#6-skill-system)
7. [Agent Orchestration Loop](#7-agent-orchestration-loop)
8. [Memory and Persistence](#8-memory-and-persistence)
9. [Implementation Recommendations](#9-implementation-recommendations)
10. [Testing and Evaluation](#10-testing-and-evaluation)
11. [References](#11-references)

---

## 1. Background and Motivation

### 1.1 The NetHack Challenge

NetHack is one of the most challenging games for AI agents due to:

- **Procedural generation**: Every run creates a unique dungeon
- **Partial observability**: Limited field of view, hidden traps, unidentified items
- **Complex interactions**: 400+ item types, 350+ monster types, intricate mechanics
- **Long-horizon planning**: Ascension requires ~50,000+ actions across 50+ dungeon levels
- **Permadeath**: A single mistake can end hours of progress

The NeurIPS 2021 NetHack Challenge demonstrated that symbolic bots (AutoAscend) significantly outperform neural approaches [4]. However, symbolic bots require extensive hand-engineering—AutoAscend comprises thousands of lines of carefully crafted rules.

### 1.2 Limitations of Current LLM Approaches

**NetPlay** [1] represents the state-of-the-art for LLM agents on NetHack. Key findings:

- Uses GPT-4 with predefined skills (explore, fight, pickup, etc.)
- Struggles with ambiguous instructions and lack of explicit feedback
- Far outperformed by AutoAscend when playing autonomously
- Performs best "when provided with concrete instructions"

The fundamental limitation: **skills are static**. NetPlay cannot adapt its behavioral repertoire to novel situations not anticipated by its designers.

### 1.3 The Self-Programming Paradigm

Our insight: Instead of hardcoding skills, **let the agent write them**.

This approach offers several advantages:

1. **Adaptability**: Skills can be tailored to the current game state
2. **Composability**: Complex behaviors emerge from simple primitives
3. **Efficiency**: Long-running loops execute without LLM inference per action
4. **Learning**: Successful skills can be persisted and reused across runs

The agent becomes a *programmer of its own behavior*, with the LLM serving as a strategic planner that delegates tactical execution to generated code.

---

## 2. System Architecture

### 2.1 High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         STRATEGIC LAYER (LLM)                           │
│  Claude/GPT-4 reasons about game state, decides what to do, writes     │
│  Python skills to accomplish goals                                      │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │ writes/invokes skills
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      SKILL EXECUTION LAYER                              │
│  Sandboxed Python environment executes agent-written code               │
│  Skills call the NetHack API and return structured results              │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │ API calls
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        NETHACK API LAYER                                │
│  High-level Python interface wrapping NLE observations and actions      │
│  Provides state queries, action execution, knowledge base access        │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │ gymnasium interface
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    NETHACK LEARNING ENVIRONMENT                         │
│  NLE v1.2+ wrapping NetHack 3.6.7                                       │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Component Summary

| Component | Responsibility | Technology |
|-----------|---------------|------------|
| Strategic Layer | High-level planning, skill synthesis | Claude API / GPT-4 |
| Skill Execution | Run agent-generated Python safely | Docker + seccomp / E2B |
| NetHack API | Structured game interface | Python wrapper over NLE |
| NLE | Game simulation | NetHack 3.6.7 + gymnasium |
| Skill Storage | Persist successful skills | Filesystem + SQLite |
| Memory System | Track game history, dungeon maps | SQLite + vector store |

---

## 3. NetHack Environment Layer

### 3.1 Environment Selection: NLE vs MiniHack

**Recommendation: Use NLE directly for full gameplay, MiniHack for development/testing.**

| Aspect | NLE | MiniHack |
|--------|-----|----------|
| Scope | Full NetHack game | Customizable scenarios |
| Complexity | High | Configurable |
| Use Case | Production evaluation | Skill development, unit tests |
| Installation | `pip install nle` | `pip install minihack` |

**Rationale**: The full NLE provides the authentic NetHack experience needed to evaluate agent capabilities. MiniHack allows isolated testing of specific skills (e.g., combat, navigation, Sokoban).

### 3.2 NLE Configuration

```python
import gymnasium as gym
import nle

env = gym.make(
    "NetHackChallenge-v0",  # Full game, random character
    observation_keys=(
        "glyphs",           # 21x79 grid of glyph IDs
        "chars",            # 21x79 grid of ASCII characters  
        "colors",           # 21x79 grid of color codes
        "specials",         # 21x79 grid of special attributes
        "blstats",          # Bottom-line stats (HP, AC, etc.)
        "message",          # Game messages
        "inv_glyphs",       # Inventory glyph IDs
        "inv_strs",         # Inventory item strings
        "inv_letters",      # Inventory slot letters
        "inv_oclasses",     # Inventory object classes
        "tty_chars",        # Full terminal output (24x80)
        "tty_colors",       # Terminal colors
        "tty_cursor",       # Cursor position
        "screen_descriptions",  # Text descriptions per tile
    ),
    actions=nle.env.NLE_DEFAULT_ACTIONS,  # 98 actions
    max_episode_steps=1_000_000,
    allow_all_yn_questions=True,
    allow_all_modes=True,
)
```

### 3.3 Key Observation Spaces

| Observation | Shape | Description |
|-------------|-------|-------------|
| `glyphs` | (21, 79) | Unique ID for each entity (monster, item, terrain) |
| `blstats` | (27,) | Player stats: HP, MaxHP, Str, Dex, AC, XP, Gold, etc. |
| `message` | (256,) | Null-terminated game message string |
| `inv_strs` | (55, 80) | Inventory item descriptions |
| `screen_descriptions` | (21, 79, 80) | Per-tile text descriptions |
| `tty_chars` | (24, 80) | Raw terminal ASCII output |

### 3.4 Action Space

NLE provides 98 discrete actions. Key categories:

| Category | Actions | Examples |
|----------|---------|----------|
| Movement | 16 | North, South, Up stairs, Down stairs |
| Combat | 4 | Fight, Fire, Throw, Kick |
| Items | 20+ | Pickup, Drop, Eat, Quaff, Read, Zap |
| Magic | 6 | Cast spell, Pray, Turn undead |
| Meta | 10+ | Search, Wait, Look, Inventory |

---

## 4. NetHack API Design

### 4.1 Design Principles

The API exposed to agent-generated code must be:

1. **Safe**: No access to filesystem, network, or dangerous operations
2. **Intuitive**: Match how humans think about the game
3. **Rich**: Expose enough state for sophisticated decision-making
4. **Async**: Support long-running skills with interruptibility

### 4.2 Core API Specification

```python
from dataclasses import dataclass
from typing import Optional, Callable, Any
from enum import Enum


class HungerState(Enum):
    SATIATED = "Satiated"
    NOT_HUNGRY = "Not Hungry"
    HUNGRY = "Hungry"
    WEAK = "Weak"
    FAINTING = "Fainting"
    FAINTED = "Fainted"


class Alignment(Enum):
    LAWFUL = "Lawful"
    NEUTRAL = "Neutral"
    CHAOTIC = "Chaotic"


@dataclass
class Position:
    x: int
    y: int
    
    def distance_to(self, other: "Position") -> int:
        """Manhattan distance."""
        return abs(self.x - other.x) + abs(self.y - other.y)
    
    def direction_to(self, other: "Position") -> str:
        """Returns compass direction (n, s, e, w, ne, nw, se, sw)."""
        ...


@dataclass
class Stats:
    hp: int
    max_hp: int
    pw: int  # Power (mana)
    max_pw: int
    ac: int  # Armor class (lower is better)
    xp_level: int
    xp_points: int
    gold: int
    strength: int
    dexterity: int
    constitution: int
    intelligence: int
    wisdom: int
    charisma: int
    hunger: HungerState
    encumbrance: str  # "Unencumbered", "Burdened", "Stressed", etc.
    alignment: Alignment
    dungeon_level: int
    turn: int


@dataclass
class Monster:
    glyph: int
    char: str
    name: str
    position: Position
    color: int
    is_peaceful: bool
    is_tame: bool
    threat_level: int  # Estimated from knowledge base


@dataclass
class Item:
    glyph: int
    name: str
    position: Position  # For items on ground
    slot: Optional[str]  # For inventory items (a-zA-Z)
    quantity: int
    blessed_cursed_unknown: str  # "blessed", "cursed", "uncursed", "unknown"
    identified: bool
    object_class: str  # "weapon", "armor", "food", "potion", etc.


@dataclass
class Tile:
    char: str
    glyph: int
    position: Position
    description: str
    is_walkable: bool
    is_explored: bool
    has_trap: bool
    trap_type: Optional[str]
    feature: Optional[str]  # "door", "altar", "fountain", "throne", etc.


@dataclass 
class DungeonLevel:
    level_number: int
    branch: str  # "Dungeons of Doom", "Gnomish Mines", "Sokoban", etc.
    tiles: list[list[Tile]]
    explored_percentage: float


@dataclass
class ActionResult:
    success: bool
    messages: list[str]
    turn_elapsed: bool
    state_changed: bool
    error: Optional[str]


class NetHackAPI:
    """
    High-level API for interacting with NetHack.
    Exposed to agent-generated skill code.
    """
    
    # ==================== STATE QUERIES ====================
    
    async def get_stats(self) -> Stats:
        """Get current player statistics."""
        ...
    
    async def get_position(self) -> Position:
        """Get player's current position."""
        ...
    
    async def get_screen(self) -> str:
        """Get the raw ASCII screen (24x80)."""
        ...
    
    async def get_messages(self, n: int = 10) -> list[str]:
        """Get the last n game messages."""
        ...
    
    async def get_current_level(self) -> DungeonLevel:
        """Get parsed representation of current dungeon level."""
        ...
    
    async def get_visible_monsters(self) -> list[Monster]:
        """Get all monsters currently visible."""
        ...
    
    async def get_adjacent_monsters(self) -> list[Monster]:
        """Get monsters in the 8 adjacent tiles."""
        ...
    
    async def get_items_at(self, pos: Position) -> list[Item]:
        """Get items at a specific position."""
        ...
    
    async def get_items_here(self) -> list[Item]:
        """Get items at player's current position."""
        ...
    
    async def get_inventory(self) -> list[Item]:
        """Get current inventory."""
        ...
    
    async def get_equipment(self) -> dict[str, Optional[Item]]:
        """Get equipped items by slot."""
        ...
    
    async def get_status_effects(self) -> list[str]:
        """Get active status effects (Blind, Confused, etc.)."""
        ...
    
    # ==================== ACTIONS ====================
    
    async def move(self, direction: str) -> ActionResult:
        """
        Move in a direction.
        direction: 'n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw'
        """
        ...
    
    async def move_to(self, target: Position) -> ActionResult:
        """
        Move one step toward target position.
        Uses pathfinding to determine best direction.
        """
        ...
    
    async def attack(self, direction: str) -> ActionResult:
        """Attack in a direction (force attack even if no monster)."""
        ...
    
    async def wait(self) -> ActionResult:
        """Wait one turn (search in place)."""
        ...
    
    async def search(self) -> ActionResult:
        """Search adjacent tiles for secrets."""
        ...
    
    async def pickup(self, item_letter: Optional[str] = None) -> ActionResult:
        """
        Pick up items. 
        If item_letter is None, picks up everything.
        """
        ...
    
    async def drop(self, item_letter: str) -> ActionResult:
        """Drop an inventory item."""
        ...
    
    async def eat(self, item_letter: Optional[str] = None) -> ActionResult:
        """
        Eat food.
        If item_letter is None, eats from ground or prompts.
        """
        ...
    
    async def quaff(self, item_letter: str) -> ActionResult:
        """Drink a potion."""
        ...
    
    async def read(self, item_letter: str) -> ActionResult:
        """Read a scroll or spellbook."""
        ...
    
    async def zap(self, item_letter: str, direction: str) -> ActionResult:
        """Zap a wand in a direction."""
        ...
    
    async def wear(self, item_letter: str) -> ActionResult:
        """Wear armor."""
        ...
    
    async def wield(self, item_letter: str) -> ActionResult:
        """Wield a weapon."""
        ...
    
    async def take_off(self, item_letter: str) -> ActionResult:
        """Remove worn armor."""
        ...
    
    async def open_door(self, direction: str) -> ActionResult:
        """Open a door."""
        ...
    
    async def kick(self, direction: str) -> ActionResult:
        """Kick in a direction (can break doors)."""
        ...
    
    async def go_up(self) -> ActionResult:
        """Ascend stairs."""
        ...
    
    async def go_down(self) -> ActionResult:
        """Descend stairs."""
        ...
    
    async def pray(self) -> ActionResult:
        """Pray to your deity."""
        ...
    
    async def cast_spell(self, spell_letter: str, direction: Optional[str] = None) -> ActionResult:
        """Cast a memorized spell."""
        ...
    
    async def send_keys(self, keys: str) -> ActionResult:
        """
        Send raw keystrokes to the game.
        Use for complex menu navigation.
        """
        ...
    
    # ==================== PATHFINDING ====================
    
    async def find_path(self, target: Position) -> list[str]:
        """
        Find path to target position.
        Returns list of direction strings.
        """
        ...
    
    async def find_nearest(
        self, 
        predicate: Callable[[Tile], bool]
    ) -> Optional[Position]:
        """Find nearest tile matching predicate."""
        ...
    
    async def find_unexplored(self) -> Optional[Position]:
        """Find nearest unexplored walkable tile."""
        ...
    
    # ==================== KNOWLEDGE BASE ====================
    
    async def lookup_monster(self, name: str) -> dict:
        """
        Look up monster information from NetHack wiki data.
        Returns: difficulty, attacks, resistances, speed, etc.
        """
        ...
    
    async def lookup_item(self, name: str) -> dict:
        """
        Look up item information.
        Returns: type, weight, price, effects, etc.
        """
        ...
    
    async def is_safe_to_eat(self, corpse_name: str, turns_old: int) -> bool:
        """Check if a corpse is safe to eat."""
        ...
    
    async def get_prayer_timeout(self) -> int:
        """Get turns until prayer is available again."""
        ...
```

### 4.3 API Implementation Notes

1. **Async Design**: All methods are async to support cooperative multitasking and skill interruption

2. **Caching**: State queries should cache results within a single game turn to avoid redundant NLE calls

3. **Error Handling**: Methods return `ActionResult` with success status and error messages

4. **Glyph Parsing**: Convert NLE's glyph IDs to human-readable entity information using NLE's glyph tables

5. **Pathfinding**: Implement A* over the explored map, considering walkability and known dangers

---

## 5. Code Execution Sandbox

### 5.1 Security Requirements

Agent-generated code must execute in a restricted environment:

| Requirement | Rationale |
|-------------|-----------|
| No filesystem access | Prevent data exfiltration/corruption |
| No network access | Prevent information leakage |
| No process spawning | Prevent escape attempts |
| CPU/memory limits | Prevent resource exhaustion |
| Timeout enforcement | Prevent infinite loops |

### 5.2 Recommended Approach: Docker + gVisor

**Primary Recommendation**: Use Docker containers with gVisor for kernel-level isolation.

```dockerfile
# Dockerfile for skill execution sandbox
FROM python:3.10-slim

# Install only required packages
RUN pip install --no-cache-dir numpy

# Create non-root user
RUN useradd -m sandbox
USER sandbox
WORKDIR /home/sandbox

# Copy API stubs (the actual NetHack runs outside the container)
COPY --chown=sandbox api_interface.py .

# Entry point runs skill code
ENTRYPOINT ["python", "-u", "run_skill.py"]
```

**Container Configuration**:
```python
import docker

client = docker.from_env()

container = client.containers.run(
    "nethack-skill-sandbox",
    detach=True,
    mem_limit="256m",
    cpu_period=100000,
    cpu_quota=50000,  # 50% of one CPU
    network_disabled=True,
    read_only=True,
    security_opt=["no-new-privileges"],
    runtime="runsc",  # gVisor
)
```

### 5.3 Alternative: E2B Sandboxes

For cloud deployment, consider E2B [7], which provides:

- ~150ms sandbox startup
- Per-execution isolation
- Built-in Python environment
- API-based interaction

```python
from e2b_code_interpreter import Sandbox

with Sandbox() as sandbox:
    # Inject the NetHack API proxy
    sandbox.run_code(api_proxy_code)
    
    # Execute agent-generated skill
    result = sandbox.run_code(skill_code)
```

### 5.4 API Proxy Pattern

The sandbox cannot directly access the NLE environment. Instead, use a proxy:

```
┌─────────────────┐      JSON/msgpack       ┌─────────────────┐
│  Skill Code     │◄─────────────────────►│  API Server     │
│  (in sandbox)   │                        │  (NLE access)   │
└─────────────────┘                        └─────────────────┘
```

**Inside Sandbox** - API Stub:
```python
class NetHackAPI:
    """Proxy that forwards calls to the external server."""
    
    def __init__(self, socket_path: str):
        self._socket = connect(socket_path)
    
    async def get_stats(self) -> Stats:
        response = await self._call("get_stats", {})
        return Stats(**response)
    
    async def _call(self, method: str, params: dict) -> dict:
        self._socket.send(json.dumps({"method": method, "params": params}))
        return json.loads(self._socket.recv())
```

**Outside Sandbox** - API Server:
```python
class NetHackAPIServer:
    """Handles requests from sandboxed skill code."""
    
    def __init__(self, env: NLE):
        self.env = env
        self.api = NetHackAPIImplementation(env)
    
    async def handle_request(self, request: dict) -> dict:
        method = getattr(self.api, request["method"])
        result = await method(**request["params"])
        return asdict(result)
```

---

## 6. Skill System

### 6.1 Skill Structure

A skill is a Python async function with a specific signature:

```python
async def skill_name(nh: NetHackAPI, **params) -> SkillResult:
    """
    Docstring describing what the skill does.
    
    Args:
        nh: The NetHack API instance
        **params: Skill-specific parameters
    
    Returns:
        SkillResult with termination reason and relevant data
    """
    ...
```

**SkillResult Definition**:
```python
@dataclass
class SkillResult:
    stopped_reason: str  # Why the skill terminated
    data: dict           # Relevant data for the agent
    actions_taken: int   # Number of game actions executed
    turns_elapsed: int   # Number of game turns elapsed
    success: bool        # Whether the skill achieved its goal
```

### 6.2 Example: Cautious Exploration Skill

```python
async def cautious_explore(nh: NetHackAPI, hp_threshold: float = 0.5) -> SkillResult:
    """
    Explore the current level while monitoring for dangers.
    
    Stops when:
    - Monster spotted
    - HP drops below threshold
    - Hunger becomes Hungry or worse
    - Found stairs
    - Fully explored
    
    Args:
        nh: NetHack API
        hp_threshold: Stop if HP falls below this fraction of max HP
    """
    actions = 0
    max_actions = 500
    
    while actions < max_actions:
        stats = await nh.get_stats()
        
        # Check HP
        if stats.hp < stats.max_hp * hp_threshold:
            return SkillResult(
                stopped_reason="low_hp",
                data={"hp": stats.hp, "max_hp": stats.max_hp},
                actions_taken=actions,
                turns_elapsed=stats.turn,
                success=False
            )
        
        # Check hunger
        if stats.hunger in [HungerState.HUNGRY, HungerState.WEAK, HungerState.FAINTING]:
            return SkillResult(
                stopped_reason="hungry",
                data={"hunger": stats.hunger.value},
                actions_taken=actions,
                turns_elapsed=stats.turn,
                success=False
            )
        
        # Check for monsters
        monsters = await nh.get_visible_monsters()
        if monsters:
            return SkillResult(
                stopped_reason="monster_spotted",
                data={"monsters": [(m.name, m.position.x, m.position.y) for m in monsters]},
                actions_taken=actions,
                turns_elapsed=stats.turn,
                success=False
            )
        
        # Check for stairs
        level = await nh.get_current_level()
        for row in level.tiles:
            for tile in row:
                if tile.char in ['<', '>'] and tile.is_explored:
                    return SkillResult(
                        stopped_reason="found_stairs",
                        data={"stairs_pos": (tile.position.x, tile.position.y), 
                              "stairs_type": "up" if tile.char == '<' else "down"},
                        actions_taken=actions,
                        turns_elapsed=stats.turn,
                        success=True
                    )
        
        # Find unexplored area
        target = await nh.find_unexplored()
        if target is None:
            return SkillResult(
                stopped_reason="fully_explored",
                data={"explored_pct": level.explored_percentage},
                actions_taken=actions,
                turns_elapsed=stats.turn,
                success=True
            )
        
        # Move toward unexplored
        result = await nh.move_to(target)
        actions += 1
        
        if not result.success:
            # Blocked, try a different direction
            await nh.search()
            actions += 1
    
    return SkillResult(
        stopped_reason="action_limit",
        data={},
        actions_taken=actions,
        turns_elapsed=stats.turn,
        success=False
    )
```

### 6.3 Skill Categories

| Category | Examples | Typical Triggers |
|----------|----------|------------------|
| Exploration | `cautious_explore`, `speed_explore`, `search_for_secrets` | Fully explored, monster, danger |
| Combat | `melee_fight`, `ranged_kite`, `tactical_retreat` | Target dead, HP low, out of ammo |
| Resource | `eat_when_hungry`, `heal_up`, `rest_until_full` | Not hungry, HP full, PWR full |
| Navigation | `go_to_stairs`, `return_to_stash`, `pathfind_to` | Arrived, blocked, danger |
| Inventory | `manage_inventory`, `identify_items`, `organize_bag` | Inventory full, all identified |
| Special | `solve_sokoban`, `navigate_mines`, `prepare_for_quest` | Puzzle solved, objective reached |

### 6.4 Skill Persistence

Successful skills are saved to a skill library:

```
/skills
├── exploration/
│   ├── SKILL.md                  # Category description
│   ├── cautious_explore.py       # Skill implementation
│   ├── speed_explore.py
│   └── search_corridor.py
├── combat/
│   ├── SKILL.md
│   ├── melee_generic.py
│   ├── handle_floating_eye.py    # Special case
│   └── retreat_and_heal.py
├── sokoban/
│   ├── SKILL.md
│   └── solve_sokoban.py
└── meta.json                     # Skill metadata and statistics
```

**SKILL.md Format**:
```markdown
# Exploration Skills

Skills for navigating and exploring dungeon levels.

## Available Skills

### cautious_explore
- **Triggers**: monster, low_hp, hungry, found_stairs, fully_explored
- **Parameters**: hp_threshold (float, default 0.5)
- **Success Rate**: 78% (based on 1,247 executions)

### speed_explore  
- **Triggers**: monster, very_low_hp, found_stairs
- **Parameters**: none
- **Notes**: Ignores hunger, moves faster but more dangerous
```

---

## 7. Agent Orchestration Loop

### 7.1 Main Loop Structure

```python
async def run_agent(env: NLE, llm: LLMClient, skill_library: SkillLibrary):
    """Main agent loop."""
    
    api = NetHackAPI(env)
    sandbox = SkillSandbox()
    memory = AgentMemory()
    
    obs, info = env.reset()
    done = False
    
    while not done:
        # 1. Gather current state
        state = await api.get_comprehensive_state()
        memory.update(state)
        
        # 2. Ask LLM for decision
        prompt = build_prompt(state, memory, skill_library)
        response = await llm.complete(prompt)
        
        # 3. Parse LLM response
        decision = parse_decision(response)
        
        if decision.type == "invoke_skill":
            # Run existing skill
            skill_code = skill_library.get(decision.skill_name)
            result = await sandbox.execute(skill_code, api, decision.params)
            memory.record_skill_execution(decision.skill_name, result)
            
        elif decision.type == "create_skill":
            # LLM wrote new skill code
            skill_code = decision.code
            
            # Validate syntax
            if not validate_skill_syntax(skill_code):
                memory.record_error("Invalid skill syntax")
                continue
            
            # Execute in sandbox
            result = await sandbox.execute(skill_code, api, decision.params)
            
            # If successful, offer to save
            if result.success:
                skill_library.save(decision.skill_name, skill_code, result)
            
            memory.record_skill_execution(decision.skill_name, result)
            
        elif decision.type == "direct_action":
            # Single action (fallback for simple cases)
            result = await execute_action(api, decision.action)
            memory.record_action(decision.action, result)
        
        # 4. Check game state
        done = env.game_over or result.stopped_reason == "death"
    
    return memory.get_summary()
```

### 7.2 Prompt Engineering

The prompt to the LLM should include:

1. **System Context**: Role description, available actions, output format
2. **Current State**: HP, position, visible entities, recent messages
3. **Memory Summary**: Important past events, known map features
4. **Available Skills**: List of skills with descriptions and trigger conditions
5. **Recent History**: Last few skill executions and their results

**Example Prompt Structure**:
```
You are playing NetHack as a {role}. Your goal is to retrieve the Amulet of Yendor and ascend.

CURRENT STATE:
- Position: Dungeon Level 3, (34, 12)  
- HP: 18/24 (75%)
- Hunger: Not Hungry
- AC: 4
- Visible: grid bug (2 tiles east), door (north)

RECENT MESSAGES:
- "You see here a +0 dagger."
- "The grid bug bites!"

AVAILABLE SKILLS:
1. cautious_explore(hp_threshold=0.5) - Explore until danger
2. melee_fight(target_position) - Fight adjacent monster
3. pickup_items() - Collect items at current position

You can either:
A) Invoke an existing skill: {"action": "invoke", "skill": "name", "params": {...}}
B) Write a new skill: {"action": "create", "name": "...", "code": "..."}
C) Take a direct action: {"action": "direct", "key": "h"} (move west)

What do you do?
```

### 7.3 Decision Parsing

```python
@dataclass
class AgentDecision:
    type: str  # "invoke_skill", "create_skill", "direct_action"
    skill_name: Optional[str]
    code: Optional[str]
    params: dict
    action: Optional[str]
    reasoning: str


def parse_decision(llm_response: str) -> AgentDecision:
    """Parse LLM response into structured decision."""
    
    # Extract JSON from response (handle markdown code blocks)
    json_str = extract_json(llm_response)
    data = json.loads(json_str)
    
    if data["action"] == "invoke":
        return AgentDecision(
            type="invoke_skill",
            skill_name=data["skill"],
            params=data.get("params", {}),
            reasoning=data.get("reasoning", "")
        )
    elif data["action"] == "create":
        return AgentDecision(
            type="create_skill",
            skill_name=data["name"],
            code=data["code"],
            params=data.get("params", {}),
            reasoning=data.get("reasoning", "")
        )
    elif data["action"] == "direct":
        return AgentDecision(
            type="direct_action",
            action=data["key"],
            reasoning=data.get("reasoning", "")
        )
```

---

## 8. Memory and Persistence

### 8.1 Memory Components

| Component | Scope | Purpose |
|-----------|-------|---------|
| Working Memory | Current turn | Cached state queries |
| Short-term Memory | Current episode | Recent events, messages |
| Episodic Memory | Current episode | Skill executions, outcomes |
| Dungeon Memory | Current episode | Explored maps, item locations |
| Skill Library | Cross-episode | Successful skill implementations |
| Statistics | Cross-episode | Skill success rates, common failures |

### 8.2 Dungeon Memory Schema

```python
@dataclass
class DungeonMemory:
    """Persistent memory of dungeon exploration."""
    
    levels: dict[int, LevelMemory]  # level_num -> memory
    current_level: int
    stash_locations: list[tuple[int, Position]]  # (level, pos) of item stashes
    altar_locations: list[tuple[int, Position, str]]  # (level, pos, alignment)
    shop_locations: list[tuple[int, Position, str]]  # (level, pos, shop_type)
    

@dataclass  
class LevelMemory:
    """Memory of a single dungeon level."""
    
    tiles: dict[tuple[int, int], TileMemory]
    explored_mask: np.ndarray  # 21x79 bool
    last_visited: int  # game turn
    stairs_up: Optional[Position]
    stairs_down: Optional[Position]
    branch: Optional[str]


@dataclass
class TileMemory:
    """Memory of a single tile."""
    
    last_seen: int  # game turn
    char: str
    feature: Optional[str]
    items_seen: list[str]  # item names observed here
    monster_seen: Optional[str]  # last monster type seen here
    searched_count: int  # times we've searched this tile
```

### 8.3 Memory Database

Use SQLite for persistent storage:

```sql
-- Skill execution history
CREATE TABLE skill_executions (
    id INTEGER PRIMARY KEY,
    timestamp TEXT,
    skill_name TEXT,
    params TEXT,  -- JSON
    stopped_reason TEXT,
    success INTEGER,
    actions_taken INTEGER,
    turns_elapsed INTEGER,
    game_state_before TEXT,  -- JSON snapshot
    game_state_after TEXT    -- JSON snapshot
);

-- Skill definitions
CREATE TABLE skills (
    name TEXT PRIMARY KEY,
    code TEXT,
    description TEXT,
    category TEXT,
    created_at TEXT,
    updated_at TEXT,
    execution_count INTEGER,
    success_count INTEGER
);

-- Game episodes
CREATE TABLE episodes (
    id INTEGER PRIMARY KEY,
    started_at TEXT,
    ended_at TEXT,
    final_score INTEGER,
    final_dlvl INTEGER,
    death_reason TEXT,
    total_turns INTEGER,
    skills_used TEXT  -- JSON list
);
```

---

## 9. Implementation Recommendations

### 9.1 Development Phases

**Phase 1: Foundation (2-3 weeks)**
- Set up NLE environment with full observation keys
- Implement NetHack API wrapper
- Create basic sandbox execution
- Build simple orchestration loop with hardcoded skills

**Phase 2: Skill System (2-3 weeks)**
- Implement skill parsing and validation
- Add skill persistence to filesystem
- Create skill library loader
- Implement basic LLM integration for skill selection

**Phase 3: Self-Programming (3-4 weeks)**
- Enable LLM to write new skills
- Implement skill testing and validation
- Add skill statistics tracking
- Create feedback loop for skill improvement

**Phase 4: Advanced Features (2-3 weeks)**
- Implement dungeon memory system
- Add knowledge base integration (NetHack wiki data)
- Create specialized skills (Sokoban solver, etc.)
- Performance optimization

**Phase 5: Evaluation (2-3 weeks)**
- Run BALROG benchmark comparisons [5]
- Compare against NetPlay and AutoAscend baselines
- Analyze skill generation patterns
- Document findings

### 9.2 Technology Stack

| Component | Recommendation | Alternatives |
|-----------|---------------|--------------|
| LLM | Claude API (claude-sonnet-4-20250514) | GPT-4, Claude Opus |
| Environment | NLE 1.2+ | MiniHack for testing |
| Sandbox | Docker + gVisor | E2B, Firecracker |
| Database | SQLite | PostgreSQL for scale |
| Async | asyncio + uvloop | trio |
| Testing | pytest + pytest-asyncio | unittest |

### 9.3 Configuration

```yaml
# config.yaml
agent:
  model: "claude-sonnet-4-20250514"
  max_tokens: 4096
  temperature: 0.7

environment:
  name: "NetHackChallenge-v0"
  max_episode_steps: 1000000
  render_mode: null  # "human" for debugging

sandbox:
  type: "docker"
  image: "nethack-skill-sandbox:latest"
  memory_limit: "256m"
  cpu_limit: 0.5
  timeout_seconds: 30

skills:
  library_path: "./skills"
  auto_save: true
  min_success_rate_to_save: 0.3

memory:
  database_path: "./data/memory.db"
  max_short_term_items: 100
  dungeon_map_resolution: [21, 79]
```

### 9.4 Error Handling

```python
class SkillExecutionError(Exception):
    """Error during skill execution."""
    pass

class SkillTimeoutError(SkillExecutionError):
    """Skill exceeded time limit."""
    pass

class SkillSyntaxError(SkillExecutionError):
    """Invalid skill code."""
    pass

class APIError(Exception):
    """Error in NetHack API."""
    pass

async def safe_skill_execution(sandbox, skill_code, api, params):
    """Execute skill with comprehensive error handling."""
    try:
        result = await asyncio.wait_for(
            sandbox.execute(skill_code, api, params),
            timeout=30.0
        )
        return result
    except asyncio.TimeoutError:
        raise SkillTimeoutError("Skill execution timed out")
    except SyntaxError as e:
        raise SkillSyntaxError(f"Invalid syntax: {e}")
    except Exception as e:
        # Log full traceback for debugging
        logging.exception("Skill execution failed")
        raise SkillExecutionError(f"Execution failed: {e}")
```

---

## 10. Testing and Evaluation

### 10.1 Unit Tests

```python
# test_api.py
import pytest
from nethack_api import NetHackAPI

@pytest.mark.asyncio
async def test_get_stats(mock_nle_env):
    api = NetHackAPI(mock_nle_env)
    stats = await api.get_stats()
    assert stats.hp > 0
    assert stats.max_hp >= stats.hp
    assert stats.dungeon_level >= 1

@pytest.mark.asyncio  
async def test_move(mock_nle_env):
    api = NetHackAPI(mock_nle_env)
    initial_pos = await api.get_position()
    result = await api.move('n')
    new_pos = await api.get_position()
    # Position should change (or action should fail with explanation)
    assert result.success or result.error is not None
```

### 10.2 Integration Tests with MiniHack

```python
# test_skills_minihack.py
import minihack

@pytest.mark.asyncio
async def test_exploration_skill():
    """Test exploration in a simple room."""
    env = gym.make("MiniHack-Room-5x5-v0")
    api = NetHackAPI(env)
    sandbox = SkillSandbox()
    
    skill_code = load_skill("cautious_explore")
    result = await sandbox.execute(skill_code, api, {"hp_threshold": 0.5})
    
    assert result.stopped_reason in ["fully_explored", "found_stairs"]
    assert result.actions_taken > 0

@pytest.mark.asyncio
async def test_combat_skill():
    """Test combat against a single monster."""
    env = gym.make("MiniHack-Corridor-R2-v0")  # Has a monster
    api = NetHackAPI(env)
    sandbox = SkillSandbox()
    
    skill_code = load_skill("melee_fight")
    result = await sandbox.execute(skill_code, api, {})
    
    assert result.stopped_reason in ["target_dead", "low_hp", "target_fled"]
```

### 10.3 Evaluation Metrics

| Metric | Description | Target |
|--------|-------------|--------|
| Median Score | In-game score across episodes | > NetPlay baseline |
| Median Depth | Deepest dungeon level reached | > 10 |
| Survival Rate | Episodes lasting > 1000 turns | > 50% |
| Skill Reuse | % of actions from persistent skills | > 70% |
| Novel Skills | Unique skills created per episode | < 10 |
| BALROG Score | Progression metric [5] | Improve over baseline |

### 10.4 Baseline Comparisons

1. **Random Agent**: Uniform random action selection
2. **NetPlay** [1]: GPT-4 with predefined skills
3. **AutoAscend** [2]: State-of-the-art symbolic bot
4. **BALROG Baselines** [5]: Various LLMs in naive agent mode

---

## 11. References

[1] Jeurissen, D., Perez-Liebana, D., Gow, J., Çakmak, D., & Kwan, J. (2024). Playing NetHack with LLMs: Potential & Limitations as Zero-Shot Agents. *IEEE Conference on Games (CoG)*. https://arxiv.org/abs/2403.00690

[2] Sypetkowski, M. et al. (2021). AutoAscend. *NeurIPS 2021 NetHack Challenge, 1st Place*. https://github.com/maciej-sypetkowski/autoascend

[3] Jones, A. & Kelly, C. (2025). Code execution with MCP: Building more efficient agents. *Anthropic Engineering Blog*. https://www.anthropic.com/engineering/code-execution-with-mcp

[4] Hambro, E. et al. (2022). Insights from the NeurIPS 2021 NetHack Challenge. *Proceedings of Machine Learning Research*. https://proceedings.mlr.press/v176/hambro22a.html

[5] Paglieri, D. et al. (2024). BALROG: Benchmarking Agentic LLM and VLM Reasoning On Games. *ICLR 2025*. https://arxiv.org/abs/2411.13543

[6] Küttler, H. et al. (2020). The NetHack Learning Environment. *NeurIPS 2020*. https://arxiv.org/abs/2006.13760

[7] E2B. (2025). Code Interpreters for AI Apps. https://e2b.dev/docs

[8] Samvelyan, M. et al. (2021). MiniHack the Planet: A Sandbox for Open-Ended Reinforcement Learning Research. *NeurIPS 2021*. https://arxiv.org/abs/2109.13202

[9] Piterbarg, U., Pinto, L., & Fergus, R. (2023). NetHack is Hard to Hack. https://arxiv.org/abs/2305.19240

---

## Appendix A: Full API Method Signatures

See Section 4.2 for the complete NetHackAPI class specification.

## Appendix B: Sample Skills

Additional skill implementations are available in the `/skills` directory of the reference implementation.

## Appendix C: Prompt Templates

Full prompt templates for skill selection and generation are available in `/prompts`.

---

*This specification is a living document. Updates will be tracked in version control.*