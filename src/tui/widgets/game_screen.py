"""Game screen widget displaying the 24x80 NetHack ASCII view."""

from textual.widgets import Static

from ..events import GameStateUpdated


class GameScreenWidget(Static):
    """
    Displays the 24x80 NetHack ASCII screen.

    Uses monospace rendering and preserves exact spacing.
    The widget should be sized to fit 24 lines x 80 columns.
    """

    DEFAULT_CSS = """
    GameScreenWidget {
        background: black;
        color: white;
        padding: 0;
        border: solid $secondary;
        overflow: hidden;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        # Initialize with empty screen
        self._screen = self._empty_screen()

    def _empty_screen(self) -> str:
        """Generate an empty 24x80 screen."""
        lines = []
        for _ in range(24):
            lines.append(" " * 80)
        return "\n".join(lines)

    def on_mount(self) -> None:
        """Initialize display when mounted."""
        self.update(self._screen)

    def on_game_state_updated(self, event: GameStateUpdated) -> None:
        """Update the game screen display."""
        self._screen = event.screen
        self.update(self._screen)
