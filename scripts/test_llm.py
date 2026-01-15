#!/usr/bin/env python3
"""
Test the LLM integration.

Run with: uv run python scripts/test_llm.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agent.llm_client import LLMClient, create_client_from_config
from src.config import load_config


def test_basic_completion():
    """Test a basic LLM completion."""
    print("Testing LLM integration...")
    print()

    config = load_config()
    print(f"Provider: {config.agent.provider}")
    print(f"Model: {config.agent.model}")
    print()

    try:
        client = create_client_from_config(config)
    except ValueError as e:
        print(f"ERROR: {e}")
        print("\nMake sure OPENROUTER_API_KEY is set:")
        print("  export OPENROUTER_API_KEY='your-key-here'")
        return 1

    # Test a simple completion
    print("Sending test prompt...")
    print("-" * 40)

    response = client.complete(
        prompt="You are playing NetHack. You see a grid bug to your east. What action should you take? Reply in one short sentence.",
        system="You are an expert NetHack player. Be concise.",
    )

    print(f"Response: {response.content}")
    print("-" * 40)
    print(f"Model: {response.model}")
    print(f"Finish reason: {response.finish_reason}")
    if response.usage:
        print(f"Tokens: {response.usage}")
    print()
    print("LLM integration working!")
    return 0


def test_nethack_screen():
    """Test LLM with actual NetHack screen."""
    print("\nTesting with actual NetHack screen...")
    print()

    config = load_config()

    try:
        client = create_client_from_config(config)
    except ValueError as e:
        print(f"ERROR: {e}")
        return 1

    # Get a real NetHack screen
    from src.api.environment import NLEWrapper

    with NLEWrapper() as env:
        obs = env.reset()
        screen = obs.get_screen()
        message = obs.get_message()

    prompt = f"""You are playing NetHack. Here is the current screen:

```
{screen}
```

Message: {message}

Player position: ({obs.player_x}, {obs.player_y})
HP: {obs.hp}/{obs.max_hp}
Dungeon level: {obs.dungeon_level}

What do you observe and what should you do next? Be specific about what you see on screen."""

    print("Sending NetHack screen to LLM...")
    print("-" * 40)

    response = client.complete(
        prompt=prompt,
        system="You are an expert NetHack player analyzing game state. Describe what you see and suggest the next action.",
    )

    print(f"Response:\n{response.content}")
    print("-" * 40)
    if response.usage:
        print(f"Tokens used: {response.usage['total_tokens']}")

    return 0


if __name__ == "__main__":
    result = test_basic_completion()
    if result == 0:
        result = test_nethack_screen()
    sys.exit(result)
