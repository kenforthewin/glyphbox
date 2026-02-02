"""Configuration management for the NetHack agent."""

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


class ReasoningEffort(Enum):
    """OpenRouter reasoning/thinking effort levels.

    Controls how much "thinking" the model does before responding.
    Maps to OpenRouter's reasoning.effort parameter.
    """

    NONE = "none"  # Disabled - no thinking tokens
    MINIMAL = "minimal"  # ~10% of max_tokens for thinking
    LOW = "low"  # ~20% of max_tokens for thinking
    MEDIUM = "medium"  # ~50% of max_tokens for thinking
    HIGH = "high"  # ~80% of max_tokens for thinking (recommended)
    XHIGH = "xhigh"  # ~95% of max_tokens for thinking


@dataclass
class AgentConfig:
    """Agent configuration (LLM + runtime settings)."""

    # LLM settings
    provider: str = "openrouter"
    model: str = "anthropic/claude-opus-4.5"
    base_url: str = "https://openrouter.ai/api/v1"
    temperature: float = 0.2
    # Reasoning/thinking effort level (for models that support extended thinking)
    # Options: "none", "minimal", "low", "medium", "high", "xhigh"
    reasoning: str = "none"

    # Runtime settings
    max_turns: int = 100000
    max_consecutive_errors: int = 5
    decision_timeout: float = 60.0
    skill_timeout: float = 30.0
    hp_flee_threshold: float = 0.3
    auto_save_skills: bool = True
    log_decisions: bool = True
    skills_enabled: bool = False  # Enable write_skill/invoke_skill tools

    # Message history settings
    # 0 = unlimited (keep all, compress old), N = sliding window of N turns
    max_history_turns: int = 0
    # How many recent turns keep their full map (0 = only current turn has map)
    # Higher values give more spatial context but use more tokens
    maps_in_history: int = 1
    # How many recent turns keep full tool call arguments (0 = unlimited)
    # Older tool calls show just the tool name with "[compacted]" arguments
    tool_calls_in_history: int = 0
    # Show inventory in context each turn (helps agent track items without querying)
    show_inventory: bool = True
    # Show adjacent tiles (N, S, E, W, etc.) with descriptions
    show_adjacent_tiles: bool = True
    # Show items visible on the map with their coordinates (food, weapons, etc.)
    show_items_on_map: bool = True
    # Show dungeon overview (#overview) with visited levels, branches, and features
    show_dungeon_overview: bool = True
    # Local map mode: show only tiles around player with coordinate guides (LLM-optimized)
    local_map_mode: bool = False
    # Tiles in each direction from player (7 = 15x15 total view)
    local_map_radius: int = 7

    def get_reasoning_effort(self) -> Optional[ReasoningEffort]:
        """Get reasoning effort as enum, or None if disabled."""
        try:
            effort = ReasoningEffort(self.reasoning.lower())
            return None if effort == ReasoningEffort.NONE else effort
        except ValueError:
            logger.warning(f"Invalid reasoning value '{self.reasoning}', defaulting to none")
            return None


@dataclass
class AuthConfig:
    """Authentication configuration (OpenRouter OAuth + JWT sessions).

    Auth is entirely optional. If session_secret is empty, all auth
    middleware becomes a no-op and the app works as a single-user instance.
    """

    # Required for auth to be enabled
    session_secret: str = ""  # HS256 signing key for JWT cookies
    encryption_key: str = ""  # Fernet key for encrypting stored API keys

    # OAuth endpoints
    openrouter_auth_url: str = "https://openrouter.ai/auth"
    openrouter_keys_url: str = "https://openrouter.ai/api/v1/auth/keys"
    callback_url: str = ""  # e.g. https://yoursite.com/api/auth/callback

    # Cookie settings
    cookie_domain: str = ""  # empty = use request host
    cookie_secure: bool = True  # set False for local HTTP dev
    jwt_expiry_days: int = 7

    @property
    def enabled(self) -> bool:
        return bool(self.session_secret)


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
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file: Optional[str] = "./data/agent.log"
    log_llm: bool = True
    log_actions: bool = True


@dataclass
class DatabaseConfig:
    """PostgreSQL database configuration."""

    host: str = "localhost"
    port: int = 5432
    database: str = "nethack_agent"
    user: str = "nethack"
    password: str = "nethack"
    pool_min_size: int = 2
    pool_max_size: int = 10

    @property
    def url(self) -> str:
        """Async SQLAlchemy connection URL."""
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )

    @property
    def conninfo(self) -> str:
        """Standard PostgreSQL connection string (libpq / psycopg format)."""
        return (
            f"postgresql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )


@dataclass
class WorkerConfig:
    """Procrastinate worker configuration.

    When enabled, agent runs are dispatched to separate worker processes
    via Procrastinate (PostgreSQL-backed task queue) instead of running
    in the web server process.
    """

    enabled: bool = True  # True = Procrastinate workers, False = in-process
    concurrency: int = 1  # max concurrent jobs per worker process
    queue: str = "agent_runs"
    monitor_interval: float = 10.0  # seconds between background status checks


@dataclass
class Config:
    """Main configuration container."""

    agent: AgentConfig = field(default_factory=AgentConfig)
    environment: EnvironmentConfig = field(default_factory=EnvironmentConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    skills: SkillsConfig = field(default_factory=SkillsConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    worker: WorkerConfig = field(default_factory=WorkerConfig)


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
            if "logging" in data:
                config.logging = LoggingConfig(**data["logging"])
            if "database" in data:
                config.database = DatabaseConfig(**data["database"])
            if "auth" in data:
                config.auth = AuthConfig(**data["auth"])
            if "worker" in data:
                config.worker = WorkerConfig(**data["worker"])

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
    if os.environ.get("NETHACK_AGENT_DB_HOST"):
        config.database.host = os.environ["NETHACK_AGENT_DB_HOST"]
    if os.environ.get("NETHACK_AGENT_DB_PORT"):
        config.database.port = int(os.environ["NETHACK_AGENT_DB_PORT"])
    if os.environ.get("NETHACK_AGENT_DB_NAME"):
        config.database.database = os.environ["NETHACK_AGENT_DB_NAME"]
    if os.environ.get("NETHACK_AGENT_DB_USER"):
        config.database.user = os.environ["NETHACK_AGENT_DB_USER"]
    if os.environ.get("NETHACK_AGENT_DB_PASSWORD"):
        config.database.password = os.environ["NETHACK_AGENT_DB_PASSWORD"]

    # Auth overrides
    if os.environ.get("AUTH_SESSION_SECRET"):
        config.auth.session_secret = os.environ["AUTH_SESSION_SECRET"]
    if os.environ.get("AUTH_ENCRYPTION_KEY"):
        config.auth.encryption_key = os.environ["AUTH_ENCRYPTION_KEY"]
    if os.environ.get("AUTH_CALLBACK_URL"):
        config.auth.callback_url = os.environ["AUTH_CALLBACK_URL"]
    if os.environ.get("AUTH_COOKIE_SECURE"):
        config.auth.cookie_secure = os.environ["AUTH_COOKIE_SECURE"].lower() == "true"

    # Worker overrides
    if os.environ.get("NETHACK_WORKER_ENABLED"):
        config.worker.enabled = os.environ["NETHACK_WORKER_ENABLED"].lower() == "true"
    if os.environ.get("NETHACK_WORKER_CONCURRENCY"):
        config.worker.concurrency = int(os.environ["NETHACK_WORKER_CONCURRENCY"])
    if os.environ.get("NETHACK_WORKER_QUEUE"):
        config.worker.queue = os.environ["NETHACK_WORKER_QUEUE"]

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
