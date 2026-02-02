"""Tests for RunConfig dataclass."""

from src.web.run_config import RunConfig


class TestRunConfig:
    def test_defaults(self):
        config = RunConfig()
        assert config.run_id == ""
        assert config.user_id is None
        assert config.model == ""
        assert config.character == "random"
        assert config.temperature == 0.1
        assert config.reasoning == "none"
        assert config.max_turns == 10000

    def test_construction(self):
        config = RunConfig(
            run_id="run-abc",
            user_id=42,
            model="anthropic/claude-sonnet-4",
            character="val-hum-law-fem",
            temperature=0.5,
            reasoning="high",
            max_turns=5000,
        )
        assert config.run_id == "run-abc"
        assert config.user_id == 42
        assert config.model == "anthropic/claude-sonnet-4"
        assert config.character == "val-hum-law-fem"
        assert config.temperature == 0.5
        assert config.reasoning == "high"
        assert config.max_turns == 5000

    def test_mutation(self):
        config = RunConfig(model="test-model")
        config.run_id = "new-id"
        config.user_id = 10
        assert config.run_id == "new-id"
        assert config.user_id == 10
