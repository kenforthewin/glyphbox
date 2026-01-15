"""Controls widget with Start/Pause/Stop buttons."""

from textual.widgets import Button, Static
from textual.containers import Horizontal
from textual.app import ComposeResult

from ..events import AgentStatusChanged


class ControlsWidget(Horizontal):
    """
    Control buttons: Start, Pause/Resume, Stop.
    Plus status indicator.
    """

    DEFAULT_CSS = """
    ControlsWidget {
        height: 3;
        dock: bottom;
        background: $surface;
        padding: 0 1;
        border-top: solid $primary;
    }

    ControlsWidget Button {
        margin: 0 1;
        min-width: 16;
    }

    #status-label {
        width: auto;
        padding: 0 2;
        content-align: center middle;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._status = "ready"

    def compose(self) -> ComposeResult:
        """Compose the controls layout."""
        yield Button("Start [S]", id="btn-start", variant="success")
        yield Button("Pause [Space]", id="btn-pause", variant="warning", disabled=True)
        yield Button("Stop [Q]", id="btn-stop", variant="error", disabled=True)
        yield Static("Status: Ready", id="status-label")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-start":
            self.app.action_start()
        elif event.button.id == "btn-pause":
            self.app.action_toggle_pause()
        elif event.button.id == "btn-stop":
            self.app.action_stop()

    def on_agent_status_changed(self, event: AgentStatusChanged) -> None:
        """Update status display and button states."""
        self._status = event.status

        status_label = self.query_one("#status-label", Static)
        btn_start = self.query_one("#btn-start", Button)
        btn_pause = self.query_one("#btn-pause", Button)
        btn_stop = self.query_one("#btn-stop", Button)

        # Update status text with color
        status_colors = {
            "ready": "white",
            "running": "green",
            "paused": "yellow",
            "stopped": "red",
            "error": "red bold",
        }
        color = status_colors.get(event.status, "white")

        status_text = f"Status: {event.status.title()}"
        if event.error_message:
            status_text += f" - {event.error_message[:30]}"

        status_label.update(f"[{color}]{status_text}[/{color}]")

        # Update button states
        if event.status == "running":
            btn_start.disabled = True
            btn_pause.disabled = False
            btn_pause.label = "Pause [Space]"
            btn_stop.disabled = False
        elif event.status == "paused":
            btn_start.disabled = True
            btn_pause.disabled = False
            btn_pause.label = "Resume [Space]"
            btn_stop.disabled = False
        elif event.status in ("stopped", "error"):
            btn_start.disabled = False
            btn_pause.disabled = True
            btn_pause.label = "Pause [Space]"
            btn_stop.disabled = True
        else:  # ready
            btn_start.disabled = False
            btn_pause.disabled = True
            btn_stop.disabled = True
