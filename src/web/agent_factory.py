"""Factory for creating per-user agent instances.

Creates a fully configured (agent, api) tuple from user-provided
run configuration and API key. Mirrors create_watched_agent() from
src/tui/runner.py but parameterized for multi-user runs.
"""

import logging

from src.agent import NetHackAgent
from src.agent.llm_client import LLMClient
from src.api import NetHackAPI
from src.config import AgentConfig, load_config
from src.skills import SkillExecutor, SkillLibrary

logger = logging.getLogger(__name__)


def create_agent_for_run(
    api_key: str,
    model: str,
    character: str = "random",
    temperature: float = 0.1,
    reasoning: str = "none",
    max_turns: int = 10000,
) -> tuple[NetHackAgent, NetHackAPI]:
    """Create a fresh agent + API for a user-initiated run.

    Args:
        api_key: User's OpenRouter API key (decrypted).
        model: OpenRouter model ID (e.g. "anthropic/claude-sonnet-4").
        character: NetHack character spec (e.g. "random", "val-hum-fem-law").
        temperature: LLM sampling temperature.
        reasoning: Reasoning effort level ("none", "low", "medium", "high").
        max_turns: Maximum agent turns before auto-stop.

    Returns:
        Tuple of (NetHackAgent, NetHackAPI) ready to run.
    """
    config = load_config()

    # Create game environment
    api = NetHackAPI(
        env_name=config.environment.name,
        max_episode_steps=config.environment.max_episode_steps,
    )
    api.reset()

    # Create LLM client with user's API key
    llm = LLMClient(
        provider="openrouter",
        model=model,
        base_url=config.agent.base_url,
        temperature=temperature,
        api_key=api_key,
        reasoning=reasoning if reasoning != "none" else None,
    )

    # Create skill system (fresh per run)
    library = SkillLibrary(config.skills.library_path)
    library.load_all()
    executor = SkillExecutor(api=api, library=library)

    # Build agent config with user overrides
    agent_config = AgentConfig(
        provider="openrouter",
        model=model,
        base_url=config.agent.base_url,
        temperature=temperature,
        reasoning=reasoning,
        max_turns=max_turns,
        # Inherit defaults from base config
        max_consecutive_errors=config.agent.max_consecutive_errors,
        decision_timeout=config.agent.decision_timeout,
        skill_timeout=config.agent.skill_timeout,
        hp_flee_threshold=config.agent.hp_flee_threshold,
        skills_enabled=config.agent.skills_enabled,
        max_history_turns=config.agent.max_history_turns,
        maps_in_history=config.agent.maps_in_history,
        tool_calls_in_history=config.agent.tool_calls_in_history,
        show_inventory=config.agent.show_inventory,
        show_adjacent_tiles=config.agent.show_adjacent_tiles,
        show_items_on_map=config.agent.show_items_on_map,
        show_dungeon_overview=config.agent.show_dungeon_overview,
        local_map_mode=config.agent.local_map_mode,
        local_map_radius=config.agent.local_map_radius,
    )

    agent = NetHackAgent(
        llm_client=llm,
        skill_library=library,
        skill_executor=executor,
        config=agent_config,
    )

    logger.info(f"Created agent for run: model={model}, character={character}")
    return agent, api
