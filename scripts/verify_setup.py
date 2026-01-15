#!/usr/bin/env python3
"""
Verification script to test that the NetHack agent environment is correctly set up.

This script tests:
1. NLE installation and basic functionality
2. MiniHack installation (for testing)
3. Environment wrapper functionality
4. Basic action execution

Run with: uv run python scripts/verify_setup.py
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_nle_import() -> bool:
    """Test that NLE can be imported."""
    print("Testing NLE import...", end=" ")
    try:
        import nle  # noqa: F401

        print("OK")
        return True
    except ImportError as e:
        print(f"FAILED: {e}")
        print("  Install with: uv add nle")
        return False


def test_minihack_import() -> bool:
    """Test that MiniHack can be imported."""
    print("Testing MiniHack import...", end=" ")
    try:
        import minihack  # noqa: F401

        print("OK")
        return True
    except ImportError as e:
        print(f"FAILED: {e}")
        print("  Install with: uv add minihack")
        return False


def test_gymnasium_import() -> bool:
    """Test that gymnasium can be imported."""
    print("Testing gymnasium import...", end=" ")
    try:
        import gymnasium as gym  # noqa: F401

        print("OK")
        return True
    except ImportError as e:
        print(f"FAILED: {e}")
        print("  Install with: uv add gymnasium")
        return False


def test_nle_environment() -> bool:
    """Test creating and running a basic NLE environment."""
    print("Testing NLE environment creation...", end=" ")
    try:
        import gymnasium as gym
        import nle  # noqa: F401

        env = gym.make(
            "NetHackChallenge-v0",
            observation_keys=("glyphs", "blstats", "message", "tty_chars"),
            max_episode_steps=100,
        )
        print("OK")

        print("Testing environment reset...", end=" ")
        obs, info = env.reset()
        print("OK")

        print("Testing observation structure...", end=" ")
        assert "glyphs" in obs, "Missing glyphs"
        assert "blstats" in obs, "Missing blstats"
        assert obs["glyphs"].shape == (21, 79), f"Wrong glyphs shape: {obs['glyphs'].shape}"
        assert len(obs["blstats"]) >= 25, f"Wrong blstats length: {len(obs['blstats'])}"
        print("OK")

        print("Testing basic actions (10 steps)...", end=" ")
        for i in range(10):
            action = env.action_space.sample()
            obs, reward, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                break
        print("OK")

        env.close()
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_minihack_environment() -> bool:
    """Test creating a MiniHack environment."""
    print("Testing MiniHack environment...", end=" ")
    try:
        import gymnasium as gym
        import minihack  # noqa: F401

        env = gym.make("MiniHack-Room-5x5-v0", max_episode_steps=50)
        obs, info = env.reset()
        # Take a few random actions
        for _ in range(5):
            action = env.action_space.sample()
            obs, reward, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                break
        env.close()
        print("OK")
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False


def test_environment_wrapper() -> bool:
    """Test our NLEWrapper class."""
    print("Testing NLEWrapper...", end=" ")
    try:
        from src.api.environment import NLEWrapper

        with NLEWrapper(max_episode_steps=100) as wrapper:
            obs = wrapper.reset()

            # Test observation properties
            assert obs.player_x >= 0
            assert obs.player_y >= 0
            assert obs.hp > 0
            assert obs.dungeon_level >= 1

            # Test screen rendering
            screen = obs.get_screen()
            assert len(screen) > 0
            assert "@" in screen  # Player character should be visible

            # Test a few steps
            for _ in range(5):
                action = wrapper.action_space.sample()
                obs, reward, terminated, truncated, info = wrapper.step(action)
                if wrapper.is_done:
                    break

        print("OK")
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_config_loading() -> bool:
    """Test configuration loading."""
    print("Testing config loading...", end=" ")
    try:
        from src.config import load_config

        config = load_config()
        assert config.agent.model is not None
        assert config.environment.name is not None
        print("OK")
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False


def main() -> int:
    """Run all verification tests."""
    print("=" * 60)
    print("NetHack Agent Setup Verification")
    print("=" * 60)
    print()

    tests = [
        ("NLE Import", test_nle_import),
        ("MiniHack Import", test_minihack_import),
        ("Gymnasium Import", test_gymnasium_import),
        ("Config Loading", test_config_loading),
        ("NLE Environment", test_nle_environment),
        ("MiniHack Environment", test_minihack_environment),
        ("NLEWrapper", test_environment_wrapper),
    ]

    results = []
    for name, test_fn in tests:
        try:
            result = test_fn()
        except Exception as e:
            print(f"  Unexpected error: {e}")
            result = False
        results.append((name, result))
        print()

    print("=" * 60)
    print("Summary")
    print("=" * 60)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  {name}: {status}")

    print()
    print(f"Passed: {passed}/{total}")

    if passed == total:
        print("\nAll tests passed! The environment is ready.")
        return 0
    else:
        print("\nSome tests failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
