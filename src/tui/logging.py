"""
Logging configuration for TUI runs.

Creates timestamped log files with comprehensive logging of all
agent activity including LLM calls, decisions, and skill executions.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


# Custom log level for LLM interactions
LLM_LEVEL = 25  # Between INFO (20) and WARNING (30)
logging.addLevelName(LLM_LEVEL, "LLM")


class TUIRunLogger:
    """
    Manages logging for a single TUI run.

    Creates a timestamped log file and configures logging to capture
    all relevant information for debugging and analysis.
    """

    LOG_DIR = Path("./data/logs")

    def __init__(self, log_dir: Optional[Path] = None):
        """
        Initialize the run logger.

        Args:
            log_dir: Directory for log files (defaults to ./data/logs)
        """
        self.log_dir = log_dir or self.LOG_DIR
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.run_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.log_file = self.log_dir / f"run_{self.run_id}.log"

        self._file_handler: Optional[logging.FileHandler] = None
        self._original_handlers: list[logging.Handler] = []

    def setup(self) -> Path:
        """
        Set up logging for this run.

        Returns:
            Path to the log file
        """
        # Create file handler with detailed formatting
        self._file_handler = logging.FileHandler(self.log_file, encoding="utf-8")
        self._file_handler.setLevel(logging.DEBUG)

        # Detailed format for file logging
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        self._file_handler.setFormatter(formatter)

        # Get root logger
        root_logger = logging.getLogger()

        # Save original handlers (we'll suppress console output but keep file)
        self._original_handlers = root_logger.handlers.copy()

        # Clear existing handlers and add our file handler
        root_logger.handlers = [self._file_handler]
        root_logger.setLevel(logging.DEBUG)

        # Reduce noise from third-party libraries
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("openai").setLevel(logging.WARNING)
        logging.getLogger("docker").setLevel(logging.WARNING)

        # Log session start
        logger = logging.getLogger("tui.session")
        logger.info("=" * 80)
        logger.info(f"TUI SESSION STARTED: {self.run_id}")
        logger.info(f"Log file: {self.log_file}")
        logger.info("=" * 80)

        return self.log_file

    def teardown(self) -> None:
        """Clean up logging handlers."""
        logger = logging.getLogger("tui.session")
        logger.info("=" * 80)
        logger.info(f"TUI SESSION ENDED: {self.run_id}")
        logger.info("=" * 80)

        if self._file_handler:
            self._file_handler.close()

        # Restore original handlers
        root_logger = logging.getLogger()
        root_logger.handlers = self._original_handlers


class LLMLogger:
    """
    Logger specifically for LLM interactions.

    Logs full request/response content for debugging.
    """

    def __init__(self, name: str = "llm"):
        self.logger = logging.getLogger(f"agent.{name}")
        self._system_prompt_logged = False
        self._last_message_count = 0

    def log_request(
        self,
        model: str,
        messages: list[dict],
        temperature: float,
        max_tokens: Optional[int] = None,
    ) -> None:
        """Log an LLM request."""
        self.logger.info("-" * 60)
        self.logger.info(f"LLM REQUEST: {model} (temp={temperature}, {len(messages)} msgs)")

        # Only log the newest messages to avoid repetition
        # Skip system (logged once) and already-seen messages
        new_start = self._last_message_count
        self._last_message_count = len(messages)

        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            # Skip logging system prompt after first time (it's always the same)
            if role == "system":
                if self._system_prompt_logged:
                    continue  # Don't even mention it
                else:
                    self._system_prompt_logged = True
                    self.logger.info(f"  [system] {len(content)} chars (logged once)")
                    self.logger.debug(f"  [system] {content[:1000]}...")
                    continue

            # Skip already-logged messages (show count instead)
            if i < new_start:
                continue

            # Log full content with proper formatting
            self.logger.info(f"  [{i}] {role}:")
            for line in content.split('\n'):
                self.logger.info(f"      {line}")

    def log_response(
        self,
        content: str,
        model: str,
        usage: Optional[dict] = None,
        finish_reason: Optional[str] = None,
    ) -> None:
        """Log an LLM response."""
        tokens_str = ""
        if usage:
            tokens_str = f" [{usage.get('total_tokens', '?')} tokens]"

        self.logger.info(f"LLM RESPONSE: {finish_reason}{tokens_str}")

        # Log full content
        for line in content.split('\n'):
            self.logger.info(f"  {line}")
        self.logger.info("-" * 60)

    def log_error(self, error: str, context: Optional[dict] = None) -> None:
        """Log an LLM error."""
        self.logger.error(f"LLM ERROR: {error}")
        if context:
            self.logger.error(f"Context: {json.dumps(context, indent=2)}")


class DecisionLogger:
    """Logger for agent decisions."""

    def __init__(self):
        self.logger = logging.getLogger("agent.decision")

    def log_decision(
        self,
        decision_type: str,
        skill_name: Optional[str] = None,
        params: Optional[dict] = None,
        reasoning: Optional[str] = None,
        raw_response: Optional[str] = None,
    ) -> None:
        """Log an agent decision."""
        parts = [f"DECISION: {decision_type}"]
        if skill_name:
            parts.append(f"skill={skill_name}")
        if params:
            parts.append(f"params={json.dumps(params)}")
        self.logger.info(" | ".join(parts))

        if reasoning:
            self.logger.info(f"  Reasoning: {reasoning}")


class SkillLogger:
    """Logger for skill executions."""

    def __init__(self):
        self.logger = logging.getLogger("agent.skill")

    def log_execution_start(
        self,
        skill_name: str,
        params: dict,
    ) -> None:
        """Log skill execution start."""
        if params:
            self.logger.info(f"SKILL: {skill_name} {json.dumps(params)}")
        else:
            self.logger.info(f"SKILL: {skill_name}")

    def log_execution_end(
        self,
        skill_name: str,
        success: bool,
        stopped_reason: Optional[str] = None,
        actions_taken: int = 0,
        turns_elapsed: int = 0,
        result: Optional[dict] = None,
    ) -> None:
        """Log skill execution end."""
        status = "OK" if success else "FAIL"
        reason = f" ({stopped_reason})" if stopped_reason else ""
        self.logger.info(f"  -> {status}{reason} [{actions_taken} actions, {turns_elapsed} turns]")

        # Log the hint if present (contains map/screen for look_around, summaries for others)
        if result and result.get("hint"):
            hint = result["hint"]
            self.logger.info(f"  Output:\n{hint}")


class GameStateLogger:
    """Logger for game state changes."""

    def __init__(self):
        self.logger = logging.getLogger("game.state")

    def log_state(
        self,
        turn: int,
        hp: int,
        max_hp: int,
        position: tuple[int, int],
        dlvl: int,
        message: Optional[str] = None,
    ) -> None:
        """Log current game state."""
        self.logger.debug(
            f"Turn {turn}: HP {hp}/{max_hp}, Pos {position}, DLvl {dlvl}"
        )
        if message:
            self.logger.debug(f"  Message: {message}")

    def log_screen(self, screen: str) -> None:
        """Log the game screen."""
        self.logger.debug("Game screen:")
        for line in screen.split('\n'):
            self.logger.debug(f"  {line}")


# Global instance for the current run
_current_run: Optional[TUIRunLogger] = None


def setup_run_logging(log_dir: Optional[Path] = None) -> Path:
    """
    Set up logging for a new TUI run.

    Args:
        log_dir: Optional custom log directory

    Returns:
        Path to the log file
    """
    global _current_run

    if _current_run:
        _current_run.teardown()

    _current_run = TUIRunLogger(log_dir)
    return _current_run.setup()


def teardown_run_logging() -> None:
    """Clean up logging for the current run."""
    global _current_run

    if _current_run:
        _current_run.teardown()
        _current_run = None


def get_log_file() -> Optional[Path]:
    """Get the path to the current log file."""
    if _current_run:
        return _current_run.log_file
    return None
