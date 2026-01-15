"""
Pytest configuration and fixtures for nethack-agent tests.
"""

import os
import pytest


@pytest.fixture
def nle_env():
    """Create a fresh NLE environment for testing."""
    from src.api.environment import NLEWrapper

    env = NLEWrapper(max_episode_steps=1000)
    yield env
    env.close()


@pytest.fixture
def nethack_api():
    """Create a NetHackAPI instance for testing."""
    from src.api.nethack_api import NetHackAPI

    api = NetHackAPI(max_episode_steps=1000)
    yield api
    api.close()


@pytest.fixture
def observation(nle_env):
    """Get an initial observation from a fresh environment."""
    return nle_env.reset()


# ============================================================================
# Integration test fixtures (require OPENROUTER_API_KEY)
# ============================================================================


def has_api_key() -> bool:
    """Check if OpenRouter API key is available."""
    return bool(os.environ.get("OPENROUTER_API_KEY"))


@pytest.fixture
def skip_without_api_key():
    """Skip test if OPENROUTER_API_KEY is not set."""
    if not has_api_key():
        pytest.skip("OPENROUTER_API_KEY not set - skipping integration test")


@pytest.fixture
def llm_client(skip_without_api_key):
    """Create a real LLM client for integration tests."""
    from src.agent.llm_client import LLMClient

    # Use claude-opus-4.5 which supports structured outputs
    client = LLMClient(
        provider="openrouter",
        model="anthropic/claude-opus-4.5",
        base_url="https://openrouter.ai/api/v1",
        temperature=0.7,
    )
    return client


@pytest.fixture
def skill_library():
    """Create a skill library with loaded skills."""
    from src.skills import SkillLibrary

    library = SkillLibrary("skills")
    library.load_all()
    return library


@pytest.fixture
def integration_api():
    """Create a NetHackAPI instance for integration tests."""
    from src.api.nethack_api import NetHackAPI

    api = NetHackAPI(max_episode_steps=10000)
    api.reset()  # Must reset to start a fresh game
    yield api
    api.close()


@pytest.fixture
def skill_executor(integration_api, skill_library):
    """Create a skill executor for integration tests."""
    from src.skills import SkillExecutor

    return SkillExecutor(api=integration_api, library=skill_library)


@pytest.fixture
def integration_agent(llm_client, skill_library, skill_executor):
    """Create a fully configured agent for integration tests."""
    from src.agent import NetHackAgent, AgentConfig

    config = AgentConfig(
        max_turns=100,  # Limit turns for testing
        max_consecutive_errors=3,
        decision_timeout=60.0,
        skill_timeout=30.0,
    )

    agent = NetHackAgent(
        llm_client=llm_client,
        skill_library=skill_library,
        skill_executor=skill_executor,
        config=config,
    )
    return agent


@pytest.fixture
def tui_app(integration_agent, integration_api):
    """Create a TUI app for integration tests."""
    from src.tui import NetHackTUI

    return NetHackTUI(integration_agent, integration_api)
