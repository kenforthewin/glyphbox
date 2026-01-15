"""Decision log widget showing scrolling history of agent decisions."""

from textual.widgets import RichLog
from rich.text import Text

from ..events import DecisionMade, SkillExecuted


class DecisionLogWidget(RichLog):
    """
    Scrolling log of agent decisions.

    Shows:
    - Turn number
    - Action type (INVOKE_SKILL, CREATE_SKILL, ANALYZE)
    - Skill name (if applicable)
    - Brief reasoning excerpt
    - Success/failure status after execution
    """

    DEFAULT_CSS = """
    DecisionLogWidget {
        border: solid $success;
        background: $surface;
        scrollbar-gutter: stable;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(highlight=True, markup=True, wrap=True, **kwargs)
        self._decision_count = 0

    def on_mount(self) -> None:
        """Initialize when mounted."""
        self.write(Text("Decision Log", style="bold underline"))
        self.write(Text("Waiting for agent to start...", style="dim italic"))

    def on_decision_made(self, event: DecisionMade) -> None:
        """Handle new decision event."""
        self._decision_count += 1
        decision = event.decision

        # Color code by action type
        action_colors = {
            "invoke_skill": "green",
            "create_skill": "yellow",
            "analyze": "cyan",
            "direct_action": "magenta",
            "unknown": "red",
        }
        color = action_colors.get(decision.action.value, "white")

        # Format the log entry
        text = Text()
        text.append(f"[{event.turn:05d}] ", style="dim")
        text.append(f"{decision.action.value.upper()}", style=f"bold {color}")

        if decision.skill_name:
            text.append(f" {decision.skill_name}", style="italic")

        # Validation status
        if not decision.is_valid:
            text.append(" [INVALID]", style="red bold")
            if decision.parse_error:
                text.append(f" ({decision.parse_error})", style="red dim")

        # Truncated reasoning
        if decision.reasoning:
            reason_preview = decision.reasoning[:80].replace("\n", " ")
            if len(decision.reasoning) > 80:
                reason_preview += "..."
            text.append(f"\n    {reason_preview}", style="dim italic")

        self.write(text)

    def on_skill_executed(self, event: SkillExecuted) -> None:
        """Show skill execution result."""
        text = Text()
        text.append("    -> ", style="dim")

        if event.success:
            text.append("OK", style="green bold")
        else:
            text.append("FAIL", style="red bold")

        text.append(f" ({event.stopped_reason})", style="dim")
        text.append(f" {event.actions} actions, {event.turns} turns", style="dim")

        self.write(text)
