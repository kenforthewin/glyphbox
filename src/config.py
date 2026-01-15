"""Configuration management for the NetHack agent."""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """LLM agent configuration."""

    provider: str = "openrouter"
    model: str = "anthropic/claude-opus-4.5"
    base_url: str = "https://openrouter.ai/api/v1"
    temperature: float = 0.2
    max_turns: int = 100000
    skills_enabled: bool = False  # Enable write_skill/invoke_skill tools
    max_recent_messages: int = 10  # Number of recent messages to keep in full


@dataclass
class EnvironmentConfig:
    """NLE environment configuration."""

    name: str = "NetHackChallenge-v0"
    max_episode_steps: int = 1000000
    render_mode: Optional[str] = None
    character: str = "random"


@dataclass
class SandboxConfig:
    """Skill sandbox configuration."""

    type: str = "docker"
    image: str = "nethack-skill-sandbox:latest"
    memory_limit: str = "256m"
    cpu_limit: float = 0.5
    timeout_seconds: int = 30
    use_gvisor: bool = False


@dataclass
class SkillsConfig:
    """Skill system configuration."""

    library_path: str = "./skills"
    auto_save: bool = True
    min_success_rate_to_save: float = 0.3
    max_actions_per_skill: int = 500


@dataclass
class MemoryConfig:
    """Memory system configuration."""

    database_path: str = "./data/memory.db"
    max_short_term_items: int = 100
    enable_dungeon_memory: bool = True


@dataclass
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file: Optional[str] = "./data/agent.log"
    log_llm: bool = True
    log_actions: bool = True


@dataclass
class Config:
    """Main configuration container."""

    agent: AgentConfig = field(default_factory=AgentConfig)
    environment: EnvironmentConfig = field(default_factory=EnvironmentConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    skills: SkillsConfig = field(default_factory=SkillsConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def load_config(config_path: Optional[str] = None) -> Config:
    """
    Load configuration from YAML file with environment variable overrides.

    Args:
        config_path: Path to config file. Defaults to config/default.yaml

    Returns:
        Populated Config dataclass
    """
    if config_path is None:
        # Look for config in standard locations
        candidates = [
            Path("config/default.yaml"),
            Path(__file__).parent.parent / "config" / "default.yaml",
        ]
        for candidate in candidates:
            if candidate.exists():
                config_path = str(candidate)
                break

    config = Config()

    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            data = yaml.safe_load(f)

        if data:
            # Load each section
            if "agent" in data:
                config.agent = AgentConfig(**data["agent"])
            if "environment" in data:
                config.environment = EnvironmentConfig(**data["environment"])
            if "sandbox" in data:
                config.sandbox = SandboxConfig(**data["sandbox"])
            if "skills" in data:
                config.skills = SkillsConfig(**data["skills"])
            if "memory" in data:
                config.memory = MemoryConfig(**data["memory"])
            if "logging" in data:
                config.logging = LoggingConfig(**data["logging"])

    # Environment variable overrides
    if os.environ.get("NETHACK_AGENT_PROVIDER"):
        config.agent.provider = os.environ["NETHACK_AGENT_PROVIDER"]
    if os.environ.get("NETHACK_AGENT_MODEL"):
        config.agent.model = os.environ["NETHACK_AGENT_MODEL"]
    if os.environ.get("NETHACK_AGENT_BASE_URL"):
        config.agent.base_url = os.environ["NETHACK_AGENT_BASE_URL"]
    if os.environ.get("NETHACK_AGENT_LOG_LEVEL"):
        config.logging.level = os.environ["NETHACK_AGENT_LOG_LEVEL"]
    if os.environ.get("NETHACK_SANDBOX_TYPE"):
        config.sandbox.type = os.environ["NETHACK_SANDBOX_TYPE"]

    # Note: API key should be set via OPENROUTER_API_KEY env var
    # (read by the LLM client, not stored in config for security)

    return config


def setup_logging(config: LoggingConfig) -> None:
    """
    Configure logging based on configuration.

    Args:
        config: Logging configuration
    """
    level = getattr(logging, config.level.upper(), logging.INFO)

    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if config.file:
        # Ensure log directory exists
        log_path = Path(config.file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(config.file))

    logging.basicConfig(
        level=level,
        format=config.format,
        handlers=handlers,
    )

    # Reduce noise from third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("docker").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)

    logger.info(f"Logging configured at level {config.level}")
