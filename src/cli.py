"""
Command-line interface for the NetHack agent.

Usage:
    uv run python -m src.cli run          Run the agent
    uv run python -m src.cli watch        Watch agent in TUI mode
    uv run python -m src.cli play         Human play mode (for debugging)
    uv run python -m src.cli test-skill   Test a specific skill
    uv run python -m src.cli list-skills  List available skills
    uv run python -m src.cli stats        Show performance statistics
"""

import argparse
import logging
import sys

from src.config import load_config, setup_logging

logger = logging.getLogger(__name__)


def cmd_run(args: argparse.Namespace) -> int:
    """Run the agent."""
    logger.info("Starting agent...")
    # TODO: Implement agent loop
    print("Agent run not yet implemented. Complete Phase 6 first.")
    return 0


def cmd_play(args: argparse.Namespace) -> int:
    """Human play mode for debugging."""
    from src.api.environment import NLEWrapper

    logger.info("Starting human play mode...")

    with NLEWrapper(render_mode="human") as env:
        obs = env.reset()
        print("\nNetHack Human Play Mode")
        print("Press Ctrl+C to exit\n")
        print(obs.get_screen())

        try:
            while not env.is_done:
                # For now, just take random actions as a demo
                # In a real implementation, this would capture keyboard input
                action = env.action_space.sample()
                obs, reward, terminated, truncated, info = env.step(action)

                if terminated or truncated:
                    print("\n--- Game Over ---")
                    print(f"Score: {obs.score}")
                    print(f"Turns: {obs.turn}")
                    break
        except KeyboardInterrupt:
            print("\n\nExiting...")

    return 0


def cmd_test_skill(args: argparse.Namespace) -> int:
    """Test a specific skill."""
    skill_name = args.skill_name
    logger.info(f"Testing skill: {skill_name}")
    # TODO: Implement skill testing
    print(f"Skill testing not yet implemented. Skill: {skill_name}")
    return 0


def cmd_list_skills(args: argparse.Namespace) -> int:
    """List available skills."""
    logger.info("Listing skills...")
    # TODO: Implement skill listing
    print("Skill listing not yet implemented. Complete Phase 4 first.")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    """Show performance statistics."""
    logger.info("Showing statistics...")
    # TODO: Implement statistics display
    print("Statistics not yet implemented. Complete Phase 5 first.")
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    """Watch the agent play in TUI mode."""
    import asyncio
    import os

    # Override model via CLI if specified
    if args.model:
        os.environ["NETHACK_AGENT_MODEL"] = args.model
        logger.info(f"Using model: {args.model}")

    logger.info("Starting TUI watch mode...")

    async def run_tui():
        from src.tui import NetHackTUI
        from src.tui.runner import create_watched_agent

        try:
            agent, api = await create_watched_agent()
            app = NetHackTUI(agent, api)
            await app.run_async()
        except Exception as e:
            logger.exception(f"TUI error: {e}")
            print(f"Error starting TUI: {e}")
            return 1
        return 0

    return asyncio.run(run_tui())


def cmd_verify(args: argparse.Namespace) -> int:
    """Run setup verification."""
    import subprocess

    result = subprocess.run(
        [sys.executable, "scripts/verify_setup.py"],
        cwd=args.project_root,
    )
    return result.returncode


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="NetHack Agent - A self-programming agent for NetHack",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        default=None,
        help="Path to configuration file",
    )
    parser.add_argument(
        "--log-level",
        "-l",
        type=str,
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level override",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # run command
    run_parser = subparsers.add_parser("run", help="Run the agent")
    run_parser.add_argument(
        "--episodes",
        "-n",
        type=int,
        default=1,
        help="Number of episodes to run",
    )
    run_parser.set_defaults(func=cmd_run)

    # play command
    play_parser = subparsers.add_parser("play", help="Human play mode")
    play_parser.set_defaults(func=cmd_play)

    # test-skill command
    test_parser = subparsers.add_parser("test-skill", help="Test a specific skill")
    test_parser.add_argument("skill_name", type=str, help="Name of skill to test")
    test_parser.set_defaults(func=cmd_test_skill)

    # list-skills command
    list_parser = subparsers.add_parser("list-skills", help="List available skills")
    list_parser.set_defaults(func=cmd_list_skills)

    # stats command
    stats_parser = subparsers.add_parser("stats", help="Show performance statistics")
    stats_parser.set_defaults(func=cmd_stats)

    # watch command
    watch_parser = subparsers.add_parser("watch", help="Watch agent in TUI mode")
    watch_parser.add_argument(
        "--model",
        "-m",
        type=str,
        default=None,
        help="Model to use (e.g., anthropic/claude-3-haiku-20240307 for cheap testing)",
    )
    watch_parser.set_defaults(func=cmd_watch)

    # verify command
    verify_parser = subparsers.add_parser("verify", help="Verify setup")
    verify_parser.set_defaults(func=cmd_verify, project_root=".")

    args = parser.parse_args()

    # Load config and set up logging
    config = load_config(args.config)
    if args.log_level:
        config.logging.level = args.log_level
    setup_logging(config.logging)

    if args.command is None:
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
