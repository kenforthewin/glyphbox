# CLAUDE.md

## Project Overview

Self-programming NetHack agent that uses an LLM to write and execute Python code to play NetHack. The LLM uses the `execute_code` tool call to interact with the game through a high-level Python API. The full game screen is automatically provided before each turn.

Two interfaces for observing the agent:
- **TUI** (`watch`): Terminal UI built with Textual for real-time monitoring
- **Web** (`serve`): FastAPI backend + React frontend for live streaming and historical run replay

## Commands

```bash
# Install dependencies
uv sync

# Run agent in TUI watch mode
uv run python -m src.cli watch

# Record TUI session with asciinema
uv run python -m src.cli watch --record

# Use a different model (cheaper for testing)
uv run python -m src.cli watch --model anthropic/claude-3-haiku-20240307

# Start web server with live agent
uv run python -m src.cli serve
uv run python -m src.cli serve --port 8000 --model google/gemini-3-flash-preview

# Development mode: backend + frontend dev servers with hot reload
./dev.sh  # Starts FastAPI on :8000, Vite on :3000

# Build frontend for production (served by FastAPI from frontend/dist/)
cd frontend && npm install && npx vite build

# Verify setup
uv run python -m src.cli verify

# Run tests (skips integration tests by default)
uv run pytest

# Run specific test file
uv run pytest tests/test_agent_agent.py -v

# Run integration tests (requires API key)
uv run pytest -m integration

# Lint
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

## Architecture

```
LLM (strategic layer)
    | receives: game screen, inventory, monsters, adjacent tiles each turn
    | tool calls: execute_code, view_full_map, write_skill, invoke_skill
    v
NetHackAgent (src/agent/agent.py)
    | orchestrates: step loop, context compression, error recovery
    v
SkillSandbox (src/sandbox/manager.py)
    | validates & executes Python code (AST checks, forbidden imports)
    v
NetHackAPI (src/api/nethack_api.py)          Persistence (src/persistence/)
    | high-level game interface                 | SQLite: runs + turns
    v                                           v
NLE (NetHack Learning Environment)           Web API (src/web/)
                                               | FastAPI REST + WebSocket
                                               v
                                             Frontend (frontend/)
                                               | React + TypeScript + Vite
```

### Core Components

- **`src/cli.py`**: Entry point. Commands: `watch` (TUI mode), `serve` (web server), `verify`
- **`src/agent/agent.py`**: `NetHackAgent` class - main orchestration loop. Calls `step()` repeatedly which gets LLM decision and executes it. Manages conversation history with context compression
- **`src/agent/llm_client.py`**: `LLMClient` using OpenAI-compatible API. Supports OpenRouter and direct Anthropic providers. Defines tools and handles extended thinking/reasoning
- **`src/agent/prompts.py`**: `PromptManager` - builds system prompts, decision prompts, and formats last_result feedback. Handles deduplication of repeated game messages
- **`src/agent/parser.py`**: Parses LLM tool call responses, extracts JSON from markdown code blocks
- **`src/sandbox/manager.py`**: `SkillSandbox.execute_code()` runs agent-generated Python in restricted namespace with `nh` (NetHackAPI) available. `APICallTracker` wraps the API to record all action calls
- **`src/api/nethack_api.py`**: High-level NetHack interface wrapping NLE observations/actions
- **`src/memory/`**: Episode memory system - `EpisodeMemory` coordinates `WorkingMemory` (current state), `DungeonMemory` (per-level exploration), and `MemoryManager` (SQLite persistence)
- **`src/persistence/`**: Turn-level persistence layer - `TurnRepository` protocol with `SQLiteTurnRepository` implementation. Stores `RunRecord` and `TurnRecord` in `data/turns.db`
- **`src/scoring/progress.py`**: BALROG progression scoring - estimates win probability based on dungeon depth and XP level using historical human gameplay data
- **`src/tui/app.py`**: Textual TUI for watching agent play. Keybindings: S=start, Space=pause, Q=quit
- **`src/web/`**: FastAPI web server with REST API and WebSocket live streaming
- **`frontend/`**: React TypeScript SPA with Vite build tooling

### Data Flow

1. `NetHackAgent.step()` builds game state context (screen, position, inventory, monsters, adjacent tiles, stairs, reminders/notes)
2. `PromptManager` formats the decision prompt and compresses conversation history
3. LLM receives context and returns tool call (`execute_code` with Python code)
4. `SkillSandbox.execute_code()` validates code (AST checks, forbidden imports) and runs it
5. Code has access to `nh` (NetHackAPI), `Direction`, `Position`, and other pre-loaded types - all calls are synchronous
6. `APICallTracker` records every action call with success/failure status
7. Results (game messages, API call log, autoexplore results) returned to agent for next LLM context

**Web path (when using `serve`):**
1. `WebAgentRunner` wraps the agent loop, captures pre-decision game state each turn
2. After each step, builds a `TurnRecord` and saves to `SQLiteTurnRepository`
3. REST API serves historical runs/turns; WebSocket streams live turns (0.3s polling)
4. React frontend displays game screen, LLM reasoning, executed code, and stats

### LLM Context Structure

The agent receives context in this structure:

**System Prompt** (once per session, via `PromptManager`):
- Full NetHackAPI documentation with all available methods
- Tool descriptions based on configuration (skills enabled, local map mode)
- Strategic gameplay advice (food management, corpse safety, hidden room searching)

**Message History** (per turn, managed by `_build_messages_with_compression`):
- Old user messages: Compressed to just `Last Result:` section (game screen stripped)
- Recent user messages: Keep full game screen (controlled by `maps_in_history`)
- Old assistant messages: Tool call arguments compacted to `[compacted]` (controlled by `tool_calls_in_history`)
- Reasoning details (`reasoning_details`) always preserved across all messages for chain-of-thought continuity

**Current User Message** (full content each turn):
```
=== CURRENT GAME VIEW ===
Your position: (x, y)
{24x80 ASCII game screen with status bar}
Adjacent tiles:
  N: dark area
  E: open door
  S: wall
Hostile Monsters:
  - goblin 'G' [E, adjacent]
Inventory:
  a: +1 long sword (weapon in hand)
  b: 2 food rations
Items on map:
  - dagger at (42, 12)
Stairs:
  - Stairs down (>) at (55, 8)
Notes (use nh.remove_note(id) to remove):
  1. Check Mines entrance on DL3

Last Result:
game_messages:
  - You hit the goblin!
  - The goblin hits! (x3)
actions:
  - attack(E) ok
  - move(E) FAILED: blocked by monster (x2)

What action will you take?
```

The game screen comes FIRST so the agent sees spatial context before text feedback. Position is explicitly stated to anchor the agent. Repeated messages and API calls are deduplicated with counts (e.g., `(x3)`).

### Tools Available to the LLM

| Tool | When Available | Purpose |
|------|---------------|---------|
| `execute_code` | Always | Run Python code with `nh` API access |
| `view_full_map` | `local_map_mode=True` | See full 21-row dungeon level (otherwise already shown) |
| `write_skill` | `skills_enabled=True` | Save reusable `async def skill_name(nh, **params):` |
| `invoke_skill` | `skills_enabled=True` | Call a previously saved skill |

### Sandbox Security

Code validation in `src/sandbox/validation.py`:
- AST-based validation before execution
- Forbidden imports: `os`, `subprocess`, `socket`, `sys`, etc.
- Forbidden calls: `exec`, `eval`, `compile`, `__import__`, `open`
- Forbidden attribute access: `__class__`, `__globals__`, `__code__`, frame inspection
- Limited builtins whitelist
- Pre-injected safe types: `Direction`, `Position`, `SkillResult`, `HungerState`, `PathResult`, `TargetResult`, `random`
- Allowed imports: `asyncio`, `typing`, `dataclasses`, `enum`, `collections`, `itertools`, `functools`, `math`, `random`, `re`, `json`, `time`
- Signal-based timeout (SIGALRM) for infinite loops

### Extended Thinking / Reasoning

The LLM client supports extended thinking via the `reasoning` config parameter:
- Effort levels: `none`, `minimal`, `low`, `medium`, `high`, `xhigh`
- Sent as `extra_body={"reasoning": {"effort": value}}` to OpenRouter
- `reasoning_text` and `reasoning_details` extracted from responses
- Reasoning is preserved across turns in conversation history for chain-of-thought continuity

## Web Interface

### Backend (`src/web/`)

FastAPI application with REST API and WebSocket support.

**REST Endpoints** (all under `/api` prefix):
| Endpoint | Description |
|----------|-------------|
| `GET /api/runs` | List runs (limit/offset pagination, most recent first) |
| `GET /api/runs/{run_id}` | Get single run metadata |
| `GET /api/runs/{run_id}/turns` | Get turns (after/limit pagination) |
| `GET /api/runs/{run_id}/turns/latest` | Get latest turn |
| `GET /api/runs/{run_id}/turns/{turn_number}` | Get specific turn |

**WebSocket** (`/ws/runs/{run_id}/live`):
- Streams `{"type": "turn", "data": {...}}` for each new turn
- Sends `{"type": "run_ended", "data": {...}}` when run finishes
- Polls repository every 0.3s for new turns (decoupled from agent runner)

**`WebAgentRunner`** (`src/web/runner.py`):
- Wraps `NetHackAgent` to persist turns during live gameplay
- Lifecycle: `start()` -> creates `RunRecord` -> runs agent loop -> `_finalize_run()`
- Captures full game state snapshot before each agent decision
- Builds `TurnRecord` from pre-state + decision + execution result

**Production serving**: When `frontend/dist/` exists, FastAPI serves the built frontend with SPA fallback (non-API 404s serve `index.html`).

### Frontend (`frontend/`)

React 19 + TypeScript SPA built with Vite.

**Stack**: React Router for navigation, Tailwind CSS 4 for styling, Prism React Renderer for Python syntax highlighting, JetBrains Mono font for game screen/code.

**Pages**:
- `RunListPage` - Lists all runs with status, model, score, depth, turns. Polls every 5s
- `RunViewerPage` - Two modes:
  - **Replay mode** (finished runs): Batch-fetches all turns, scrub through with slider/buttons/keyboard
  - **Live mode** (running runs): WebSocket connection, auto-follows latest turn, shows connection status

**Key Components** (`frontend/src/components/viewer/`):
- `GameScreen` - 24x80 ASCII display (monospace, fixed width)
- `ReasoningPanel` - LLM reasoning/thinking text
- `CodePanel` - Executed Python with syntax highlighting + success/fail badge
- `StatsBar` - HP (color-coded), Game Turn, Dungeon Level, XP Level, Score, Hunger
- `TurnScrubber` - Turn navigation (first/prev/next/last, slider, turn counter)
- `ExecutionDetails` - Collapsible game messages and API call lists
- `LiveBadge` - WebSocket connection status indicator

**Development**:
```bash
cd frontend
npm install
npx vite          # Dev server on :3000 (proxies /api and /ws to :8000)
npx vite build    # Production build to dist/
```

Vite dev server proxies `/api` to `http://localhost:8000` and `/ws` to `ws://localhost:8000`.

## Persistence

### Turn Repository (`src/persistence/`)

Protocol-based storage abstraction with SQLite implementation.

**Database**: `data/turns.db` (SQLite with WAL mode for concurrent read/write)

**Schema** (2 tables):
- **`runs`**: Run metadata - `run_id`, timestamps, model/provider, config snapshot, outcome stats (final_score, final_depth, etc.), status (running/stopped/error)
- **`turns`**: Turn snapshots - full game state (screen, position, HP, dungeon level), LLM interaction (reasoning, model, token usage), decision (action type, code), execution result (success, error, game_messages, api_calls as JSON)

**`TurnRepository` protocol** (`src/persistence/repository.py`): `create_run()`, `update_run()`, `get_run()`, `list_runs()`, `save_turn()`, `get_turns()`, `get_turn()`, `get_latest_turn()`, `count_turns()`

The protocol allows future implementations (e.g., PostgreSQL) without changing client code.

## Memory System (`src/memory/`)

Three-layer memory architecture for episode tracking:

- **`WorkingMemory`**: In-memory current state (HP, position, turn, monsters, combat status)
- **`DungeonMemory`**: Per-level exploration tracking (tiles explored, stairs, features, branches)
- **`EpisodeMemory`**: Coordinator that integrates working + dungeon memory. Tracks events (level changes, monster kills, skill usage, item discoveries), maintains episode statistics, and optionally persists to SQLite via `MemoryManager`

## Configuration

`config/default.yaml` - key settings:

**Agent**:
- `agent.provider`: `"openrouter"` or `"anthropic"`
- `agent.model`: Model identifier (default: `"anthropic/claude-opus-4.5"`, config currently set to `"google/gemini-3-flash-preview"`)
- `agent.temperature`: LLM sampling temperature (default: 0.1)
- `agent.reasoning`: Extended thinking effort - `"none"`, `"minimal"`, `"low"`, `"medium"`, `"high"`, `"xhigh"`
- `agent.skills_enabled`: `false` (core tools only) or `true` (adds write_skill/invoke_skill)
- `agent.local_map_mode`: `false` (full map) or `true` (cropped view + view_full_map tool)
- `agent.local_map_radius`: Tiles in each direction for local map (default: 7 = 15x15 view)
- `agent.max_turns`: Maximum agent turns per episode (default: 100000)
- `agent.max_consecutive_errors`: Error threshold before stopping (default: 5)

**Context management**:
- `agent.max_history_turns`: 0 = unlimited (compress old), N = sliding window of N turns
- `agent.maps_in_history`: How many recent turns keep full game screen (default: 0 = only current)
- `agent.tool_calls_in_history`: How many recent tool calls keep full arguments, 0 = unlimited (default: 10)
- `agent.show_inventory`: Include inventory in each turn's context (default: true)
- `agent.show_adjacent_tiles`: Include N/S/E/W/etc. tile descriptions (default: true)

**Environment**:
- `environment.name`: NLE environment (default: `"NetHackChallenge-v0"`)
- `environment.character`: `"random"` or specific like `"val-hum-law-fem"`

**Environment variables**:
- `OPENROUTER_KEY` or `OPENROUTER_API_KEY`: Required for OpenRouter provider
- `ANTHROPIC_API_KEY`: Required for Anthropic provider
- `NETHACK_AGENT_MODEL`: Override model
- `NETHACK_AGENT_PROVIDER`: Override provider
- `NETHACK_AGENT_BASE_URL`: Override LLM base URL
- `NETHACK_AGENT_LOG_LEVEL`: Override log level

## Logs & Recordings

**Logs** are stored in `data/logs/` with filenames like `run_2026-01-19_19-34-49.log`.

Logs include:
- LLM requests/responses (prompts sent, tool calls received)
- Game state each turn (HP, position, dungeon level)
- Agent decisions and reasoning
- API call results (successes and failures)
- Pathfinding debug info

**Recordings** (when using `--record`) are stored in `data/recordings/` as `.cast` files.

```bash
# Playback a recording
asciinema play data/recordings/run_2026-01-19_19-34-49.cast

# Upload to asciinema.org for sharing
asciinema upload data/recordings/run_2026-01-19_19-34-49.cast
```

**Database**: `data/turns.db` stores all runs and turns for the web interface. Created automatically on first use.

## Key Patterns

### Agent Code Execution

Code runs in sandbox with `nh` available. All API calls are synchronous (no await):
```python
# Example execute_code content
stats = nh.get_stats()
if stats.hp < stats.max_hp * 0.3:
    nh.pray()
else:
    nh.move(Direction.E)
```

### NetHackAPI Methods

**State queries** (don't consume turns):
- `get_stats()`, `get_position()`, `get_screen()`, `get_message()`
- `get_visible_monsters()`, `get_hostile_monsters()`, `get_adjacent_hostiles()`
- `get_inventory()`, `get_items_here()`, `get_food_in_inventory()`, `get_weapons_in_inventory()`
- Properties: `hp`, `max_hp`, `position`, `turn`, `dungeon_level`, `is_hungry`, `is_weak`, `is_blind`, `is_confused`, `is_stunned`, `has_adjacent_hostile`, `turns_since_last_prayer`

**Movement**: `move(direction, count)`, `run(direction)`, `go_up()`, `go_down()`, `move_to(position)`, `travel_to(char)`, `autoexplore(max_steps)`

**Combat**: `attack(direction)`, `kick(direction)`, `fire(direction)`, `throw(slot, direction)`

**Items**: `pickup()`, `drop(slot)`, `eat(slot)`, `quaff(slot)`, `read(slot)`, `wield(slot)`, `wear(slot)`, `take_off(slot)`, `zap(slot, direction)`, `apply(slot)`

**Interactions**: `open_door(direction)`, `close_door(direction)`, `cast_spell(slot, direction)`, `pay()`, `pray()`, `engrave(text)`, `look()`

**Utility**: `wait(count)`, `search(count)`, `add_reminder(turns, msg)`, `add_note(turns, msg)`, `remove_note(id)`, `confirm()`, `deny()`, `escape()`, `space()`

**Queries**: `find_stairs()`, `find_altars()`, `find_doors()`, `find_nearest_item()`, `find_items_on_map()`, `get_local_map(radius)`, `get_adjacent_tiles()`, `get_fired_reminders()`, `get_active_notes()`

### Test Markers

- Default: unit tests only (skips `integration` marker)
- `@pytest.mark.integration`: requires API key, tests real game scenarios

### Directory Structure

```
src/
  cli.py              # CLI entry point (watch, serve, verify)
  config.py           # Configuration dataclasses and loader
  agent/              # Agent orchestration, LLM client, prompts, parser
  api/                # NetHack API, pathfinding, glyphs, queries, actions
  memory/             # Episode/dungeon/working memory + schema.sql
  persistence/        # Run/turn storage (repository protocol + SQLite)
  sandbox/            # Code execution sandbox + validation
  scoring/            # BALROG progression scoring
  skills/             # Skill library, executor, models, statistics
  tui/                # Textual TUI app + widgets
  web/                # FastAPI app, REST routes, WebSocket, runner
frontend/
  src/                # React TypeScript SPA
    api/              # HTTP client + endpoint definitions
    components/       # Layout, viewer, and run list components
    hooks/            # useRuns, useTurns, useLiveStream, useTurnNavigation
    pages/            # RunListPage, RunViewerPage
    types/            # API response type definitions
config/
  default.yaml        # Default configuration
data/
  turns.db            # SQLite database (runs + turns)
  logs/               # Per-run log files
  recordings/         # Asciinema recordings
scripts/
  analyze_logs.py     # Log analysis utility
  test_llm.py         # LLM testing script
  verify_setup.py     # Setup verification
skills/               # Skill library directory (mostly disabled/empty)
```
