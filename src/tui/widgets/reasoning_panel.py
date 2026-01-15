"""Reasoning panel showing full LLM reasoning for current decision."""

from textual.containers import VerticalScroll
from textual.widgets import Static
from textual.app import ComposeResult
from rich.text import Text

from ..events import DecisionMade


class ReasoningPanel(VerticalScroll):
    """
    Shows the full LLM reasoning for the current/selected decision.

    Scrollable panel with the complete reasoning text and
    optionally the raw LLM response.
    """

    DEFAULT_CSS = """
    ReasoningPanel {
        border: solid $primary;
        background: $surface;
        padding: 1;
    }

    ReasoningPanel > Static {
        width: 100%;
    }

    #reasoning-label {
        text-style: bold underline;
        margin-bottom: 1;
    }

    #reasoning-content {
        width: 100%;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        """Compose the panel layout."""
        yield Static("Reasoning", id="reasoning-label")
        yield Static("Waiting for first decision...", id="reasoning-content")

    def on_decision_made(self, event: DecisionMade) -> None:
        """Update with new decision's reasoning."""
        decision = event.decision

        content = Text()

        # Header
        content.append(f"Turn {event.turn}", style="bold")
        content.append(" - ", style="dim")
        content.append(f"{decision.action.value.upper()}", style="bold cyan")
        content.append("\n")

        if decision.skill_name:
            content.append(f"Skill: {decision.skill_name}\n", style="green")

        if decision.params:
            params_str = ", ".join(f"{k}={v}" for k, v in decision.params.items())
            content.append(f"Params: {params_str}\n", style="dim")

        content.append("\n")

        # Main reasoning
        if decision.reasoning:
            content.append(decision.reasoning, style="white")
        else:
            content.append("(no reasoning provided)", style="dim italic")

        # Show validation error if present
        if decision.parse_error:
            content.append("\n\n")
            content.append("Parse Error: ", style="red bold")
            content.append(decision.parse_error, style="red")

        # Show code for create_skill actions
        if decision.code:
            content.append("\n\n")
            content.append("Generated Code:\n", style="yellow bold")
            # Truncate very long code
            code_preview = decision.code[:1000]
            if len(decision.code) > 1000:
                code_preview += "\n... (truncated)"
            content.append(code_preview, style="dim")

        # Update the content widget
        content_widget = self.query_one("#reasoning-content", Static)
        content_widget.update(content)

        # Scroll to top to see new content
        self.scroll_home()
