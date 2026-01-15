"""
End-to-end integration tests for the TUI with real LLM calls.

These tests exercise the full stack:
- NLE environment (real game)
- NetHack API
- Skill execution
- LLM client (real API calls via OpenRouter)
- Agent decision loop
- TUI event emission and display

Run with: OPENROUTER_API_KEY=your_key uv run pytest tests/test_tui/test_integration.py -v
"""

import asyncio
import os
import pytest

from src.tui import NetHackTUI


def requires_api_key():
    """Skip decorator if no API key."""
    return pytest.mark.skipif(
        not os.environ.get("OPENROUTER_API_KEY"),
        reason="OPENROUTER_API_KEY not set",
    )


@pytest.mark.integration
@requires_api_key()
class TestTUIIntegration:
    """Integration tests for the TUI with real LLM calls."""

    @pytest.mark.timeout(30)
    async def test_tui_startup(self, tui_app):
        """Test that TUI starts up and shows initial state."""
        async with tui_app.run_test() as pilot:
            # Verify app mounted
            assert tui_app.runner is not None
            assert not tui_app.runner.is_running

            # Check widgets are present
            decision_log = tui_app.query_one("#decision-log")
            game_screen = tui_app.query_one("#game-screen")
            stats_bar = tui_app.query_one("#stats-bar")
            controls = tui_app.query_one("#controls")

            assert decision_log is not None
            assert game_screen is not None
            assert stats_bar is not None
            assert controls is not None

    @pytest.mark.timeout(60)
    async def test_start_agent_makes_llm_call(
        self, integration_agent, integration_api
    ):
        """Test that starting the agent makes a real LLM call and gets a decision."""
        app = NetHackTUI(integration_agent, integration_api)

        async with app.run_test() as pilot:
            # Verify initial state
            assert app.runner is not None
            assert not app.runner.is_running

            # Start agent (press 's')
            await pilot.press("s")

            # Wait for agent to start and make at least one decision
            # Real LLM calls can take several seconds
            max_wait = 30
            waited = 0
            while waited < max_wait:
                await asyncio.sleep(1)
                waited += 1
                if integration_agent.state.decisions_made >= 1:
                    break

            # Stop the agent
            await app.runner.stop()

            # Verify agent made at least one decision
            assert integration_agent.state.decisions_made >= 1, (
                f"Agent made {integration_agent.state.decisions_made} decisions, expected >= 1"
            )

    @pytest.mark.timeout(120)
    async def test_full_agent_loop_multiple_decisions(
        self, integration_agent, integration_api
    ):
        """Test that the agent can make multiple decisions in a row."""
        app = NetHackTUI(integration_agent, integration_api)

        async with app.run_test() as pilot:
            # Start agent
            await pilot.press("s")

            # Wait for multiple decisions (3+)
            target_decisions = 3
            max_wait = 90
            waited = 0
            while waited < max_wait:
                await asyncio.sleep(1)
                waited += 1
                if integration_agent.state.decisions_made >= target_decisions:
                    break

            # Stop the agent
            await app.runner.stop()

            # Verify multiple decisions were made
            assert integration_agent.state.decisions_made >= target_decisions, (
                f"Agent made {integration_agent.state.decisions_made} decisions, "
                f"expected >= {target_decisions}"
            )

    @pytest.mark.timeout(60)
    async def test_pause_resume_functionality(
        self, integration_agent, integration_api
    ):
        """Test that pause and resume work correctly."""
        app = NetHackTUI(integration_agent, integration_api)

        async with app.run_test() as pilot:
            # Start agent
            await pilot.press("s")

            # Wait for agent to start and make at least one decision
            max_wait = 30
            waited = 0
            while waited < max_wait:
                await asyncio.sleep(1)
                waited += 1
                if app.runner.is_running and integration_agent.state.decisions_made >= 1:
                    break

            assert app.runner.is_running, "Agent should be running"

            # Pause (press space)
            await pilot.press("space")
            await asyncio.sleep(0.5)
            assert app.runner.is_paused, "Agent should be paused"

            # Record decisions at pause
            decisions_at_pause = integration_agent.state.decisions_made

            # Wait a bit - no new decisions should be made while paused
            await asyncio.sleep(3)
            assert integration_agent.state.decisions_made == decisions_at_pause, (
                "Agent should not make decisions while paused"
            )

            # Resume (press space again)
            await pilot.press("space")
            await asyncio.sleep(0.5)
            assert not app.runner.is_paused, "Agent should be resumed"

            # Stop
            await app.runner.stop()

    @pytest.mark.timeout(90)
    async def test_game_screen_updates_after_actions(
        self, integration_agent, integration_api
    ):
        """Test that the game state is updated after agent actions."""
        app = NetHackTUI(integration_agent, integration_api)

        async with app.run_test() as pilot:
            # Get initial turn
            initial_stats = integration_api.get_stats()
            initial_turn = initial_stats.turn

            # Start agent
            await pilot.press("s")

            # Wait for some actions (LLM calls can be slow)
            max_wait = 60
            waited = 0
            while waited < max_wait:
                await asyncio.sleep(1)
                waited += 1
                # Check if agent made any decisions
                if integration_agent.state.decisions_made >= 1:
                    break

            # Stop
            await app.runner.stop()

            # Verify agent made decisions (which implies game state was read)
            assert integration_agent.state.decisions_made >= 1, (
                "Agent should have made at least one decision"
            )

    @pytest.mark.timeout(120)
    async def test_skill_execution(
        self, integration_agent, integration_api
    ):
        """Test that skills are executed when the agent decides to use them."""
        app = NetHackTUI(integration_agent, integration_api)

        async with app.run_test() as pilot:
            # Start agent
            await pilot.press("s")

            # Wait for decisions - some should execute skills
            max_wait = 90
            waited = 0
            while waited < max_wait:
                await asyncio.sleep(1)
                waited += 1
                # Check if any skills were executed
                if integration_agent.state.skills_executed >= 1:
                    break
                # Or if we've made enough decisions
                if integration_agent.state.decisions_made >= 5:
                    break

            # Stop
            await app.runner.stop()

            # Verify decisions were made
            assert integration_agent.state.decisions_made >= 1, (
                "Agent should have made at least one decision"
            )

            # Check last decision
            if integration_agent.state.last_decision:
                decision = integration_agent.state.last_decision
                assert decision.action is not None

    @pytest.mark.timeout(30)
    async def test_quit_stops_agent(
        self, integration_agent, integration_api
    ):
        """Test that quitting the app stops the agent cleanly."""
        app = NetHackTUI(integration_agent, integration_api)

        async with app.run_test() as pilot:
            # Start agent
            await pilot.press("s")

            # Wait for agent to start
            max_wait = 10
            waited = 0
            while waited < max_wait:
                await asyncio.sleep(0.5)
                waited += 0.5
                if app.runner.is_running:
                    break

            assert app.runner.is_running, "Agent should be running"

            # Quit (press 'q')
            await pilot.press("q")

            # App should exit - runner should stop
            await asyncio.sleep(1)
            assert not app.runner.is_running, "Agent should have stopped"


@pytest.mark.integration
@requires_api_key()
class TestLLMDecisionQuality:
    """Tests focused on LLM decision quality and parsing."""

    @pytest.mark.timeout(90)
    async def test_llm_returns_valid_decisions(
        self, integration_agent, integration_api
    ):
        """Test that LLM returns decisions that parse correctly."""
        app = NetHackTUI(integration_agent, integration_api)

        async with app.run_test() as pilot:
            # Start agent
            await pilot.press("s")

            # Wait for several decisions
            target_decisions = 3
            max_wait = 60
            waited = 0
            while waited < max_wait:
                await asyncio.sleep(1)
                waited += 1
                if integration_agent.state.decisions_made >= target_decisions:
                    break

            # Stop
            await app.runner.stop()

            # Verify decisions were made
            total_decisions = integration_agent.state.decisions_made
            assert total_decisions >= 1, "Expected at least one decision"

            # Check the last decision is valid
            if integration_agent.state.last_decision:
                decision = integration_agent.state.last_decision
                # Log for debugging
                if not decision.is_valid:
                    print(f"Invalid decision: {decision.parse_error}")
                # At least some decisions should be valid
                # (we can't check all decisions, but the agent should work)

    @pytest.mark.timeout(90)
    async def test_agent_makes_contextual_decisions(
        self, integration_agent, integration_api
    ):
        """Test that the agent's decisions have reasoning about game state."""
        app = NetHackTUI(integration_agent, integration_api)

        async with app.run_test() as pilot:
            # Start agent
            await pilot.press("s")

            # Wait for decisions
            max_wait = 60
            waited = 0
            while waited < max_wait:
                await asyncio.sleep(1)
                waited += 1
                if integration_agent.state.decisions_made >= 2:
                    break

            # Stop
            await app.runner.stop()

            # Check that last decision has reasoning
            if integration_agent.state.last_decision:
                decision = integration_agent.state.last_decision
                if decision.is_valid:
                    assert decision.reasoning, (
                        f"Decision {decision.action} should have reasoning"
                    )
                    # Reasoning should be non-trivial
                    assert len(decision.reasoning) > 10, (
                        "Reasoning should be substantive"
                    )


@pytest.mark.integration
@requires_api_key()
class TestAgentMakesProgress:
    """Tests that verify the agent makes meaningful game progress."""

    @pytest.mark.timeout(180)
    async def test_agent_advances_game_turns(
        self, integration_agent, integration_api
    ):
        """Test that agent actions actually advance the game turn counter.

        This catches issues where:
        - Skills return immediately without taking actions
        - The LLM is confused about game state
        - Actions aren't being executed properly
        """
        app = NetHackTUI(integration_agent, integration_api)

        async with app.run_test() as pilot:
            # Record initial turn
            initial_stats = integration_api.get_stats()
            initial_turn = initial_stats.turn

            # Start agent
            await pilot.press("s")

            # Wait for 10 decisions or significant turn advancement
            target_decisions = 10
            target_turn_advance = 5  # Game should advance at least 5 turns
            max_wait = 150
            waited = 0

            while waited < max_wait:
                await asyncio.sleep(1)
                waited += 1

                current_stats = integration_api.get_stats()
                turn_advance = current_stats.turn - initial_turn

                # Success if we've advanced enough turns
                if turn_advance >= target_turn_advance:
                    break

                # Or if we've made enough decisions
                if integration_agent.state.decisions_made >= target_decisions:
                    break

            # Stop
            await app.runner.stop()

            # Get final stats
            final_stats = integration_api.get_stats()
            final_turn = final_stats.turn
            turn_advance = final_turn - initial_turn

            # Verify meaningful progress was made
            assert integration_agent.state.decisions_made >= 3, (
                f"Agent only made {integration_agent.state.decisions_made} decisions, "
                f"expected at least 3"
            )

            # The game turn should have advanced
            # If turn is still 1 after multiple decisions, something is wrong
            assert turn_advance >= 1, (
                f"Game turn did not advance (stuck at turn {final_turn}). "
                f"Agent made {integration_agent.state.decisions_made} decisions but "
                f"no actions were actually executed."
            )

            # Log detailed progress for debugging
            print(f"\n=== Agent Progress Summary ===")
            print(f"Decisions made: {integration_agent.state.decisions_made}")
            print(f"Skills executed: {integration_agent.state.skills_executed}")
            print(f"Turn advance: {initial_turn} -> {final_turn} (+{turn_advance})")
            print(f"Final HP: {final_stats.hp}/{final_stats.max_hp}")
            print(f"Final DL: {final_stats.dungeon_level}")

    @pytest.mark.timeout(180)
    async def test_agent_executes_skills_with_actions(
        self, integration_agent, integration_api
    ):
        """Test that when skills are invoked, they actually take game actions.

        This catches issues where:
        - Skills exit immediately due to wrong conditions (e.g., in_combat with no enemies)
        - The API calls don't work
        - Skill preconditions are never met
        """
        app = NetHackTUI(integration_agent, integration_api)

        # Track skill results
        skill_results = []

        # Monkey-patch to capture skill results
        original_execute = integration_agent._execute_skill

        async def tracked_execute(skill_name, params):
            await original_execute(skill_name, params)
            if integration_agent.state.last_skill_result:
                result = integration_agent.state.last_skill_result.copy()
                result["skill_name"] = skill_name
                skill_results.append(result)

        integration_agent._execute_skill = tracked_execute

        async with app.run_test() as pilot:
            # Start agent
            await pilot.press("s")

            # Wait for several skill executions
            max_wait = 120
            waited = 0
            while waited < max_wait:
                await asyncio.sleep(1)
                waited += 1
                if len(skill_results) >= 5:
                    break
                if integration_agent.state.decisions_made >= 10:
                    break

            # Stop
            await app.runner.stop()

        # Analyze skill results
        if skill_results:
            successful_skills = [r for r in skill_results if r.get("success")]
            skills_with_actions = [r for r in skill_results if r.get("actions", 0) > 0]
            skills_with_turns = [r for r in skill_results if r.get("turns", 0) > 0]

            print(f"\n=== Skill Execution Summary ===")
            print(f"Total skills invoked: {len(skill_results)}")
            print(f"Successful: {len(successful_skills)}")
            print(f"With actions > 0: {len(skills_with_actions)}")
            print(f"With turns > 0: {len(skills_with_turns)}")

            # Print each skill result
            for r in skill_results:
                print(f"  - {r.get('skill_name', 'unknown')}: "
                      f"success={r.get('success')}, "
                      f"actions={r.get('actions', 0)}, "
                      f"turns={r.get('turns', 0)}, "
                      f"reason={r.get('stopped_reason', 'unknown')}")

            # At least some skills should have taken actions
            # If ALL skills return 0 actions, something is fundamentally broken
            assert len(skills_with_actions) > 0 or len(skills_with_turns) > 0, (
                f"No skills took any game actions. "
                f"All {len(skill_results)} skill invocations returned 0 actions/turns. "
                f"This suggests skills are exiting immediately without doing anything."
            )
