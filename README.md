# Self-Programming NetHack Agent

A novel architecture for a NetHack-playing agent that dynamically generates its own behavioral skills through code synthesis.

## Overview

Unlike traditional hardcoded skill systems, this agent allows the LLM to write, execute, and persist Python functions that implement complex behaviors. The agent becomes a *programmer of its own behavior*, with the LLM serving as a strategic planner that delegates tactical execution to generated code.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         STRATEGIC LAYER (LLM)                           │
│  Claude reasons about game state, decides what to do, writes            │
│  Python skills to accomplish goals                                      │
└─────────────────────────────────────┬───────────────────────────────────┘
                                      │ writes/invokes skills
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      SKILL EXECUTION LAYER                              │
│  Sandboxed Python environment executes agent-written code               │
│  Skills call the NetHack API and return structured results              │
└─────────────────────────────────────┬───────────────────────────────────┘
                                      │ API calls
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        NETHACK API LAYER                                │
│  High-level Python interface wrapping NLE observations and actions      │
│  Provides state queries, action execution, knowledge base access        │
└─────────────────────────────────────┬───────────────────────────────────┘
                                      │ gymnasium interface
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    NETHACK LEARNING ENVIRONMENT                         │
│  NLE v1.2+ wrapping NetHack 3.6.7                                       │
└─────────────────────────────────────────────────────────────────────────┘
```

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/nethack_agent.git
cd nethack_agent

# Install dependencies with uv
uv sync

# Verify setup
uv run python scripts/verify_setup.py
```

## Usage

```bash
# Run the agent
uv run python -m src.cli run

# Human play mode (for debugging)
uv run python -m src.cli play

# Test a specific skill
uv run python -m src.cli test-skill cautious_explore

# List available skills
uv run python -m src.cli list-skills

# Show performance statistics
uv run python -m src.cli stats
```

## Configuration

Configuration is stored in `config/default.yaml`. Key settings include:

- **agent.provider**: LLM provider (default: "openrouter")
- **agent.model**: LLM model to use (default: "anthropic/claude-sonnet-4")
- **agent.base_url**: API base URL (default: OpenRouter)
- **sandbox.type**: Sandbox type for skill execution (docker or local)
- **skills.library_path**: Path to skill library

### API Key Setup

Set your OpenRouter API key as an environment variable:

```bash
export OPENROUTER_KEY="your-api-key-here"
# or: export OPENROUTER_API_KEY="your-api-key-here"
```

### Environment Variable Overrides

- `OPENROUTER_KEY` or `OPENROUTER_API_KEY`: OpenRouter API key (required)
- `NETHACK_AGENT_PROVIDER`: Override LLM provider
- `NETHACK_AGENT_MODEL`: Override LLM model
- `NETHACK_AGENT_BASE_URL`: Override API base URL
- `NETHACK_AGENT_LOG_LEVEL`: Override log level

## Development

```bash
# Install dev dependencies
uv sync --dev

# Run tests
uv run pytest

# Run with debug logging
uv run python -m src.cli run --log-level DEBUG
```

## Documentation

See [SPEC.md](SPEC.md) for the full implementation specification.

## License

MIT
