"""
Command-line interface for the NetHack agent.

Usage:
    uv run python -m src.cli watch        Watch agent in TUI mode
    uv run python -m src.cli verify       Verify setup is correct
"""

import argparse
import logging
import sys

from src.config import load_config, setup_logging

logger = logging.getLogger(__name__)


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
