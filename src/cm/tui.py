from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar, override

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static, TextArea

from .git import GitError

TEXT_COLUMNS = 80
# Round border (2), horizontal padding (2), and the vertical scrollbar (1).
EDITOR_CHROME_WIDTH = 5

CommitFunc = Callable[[str], object]


class CommitApp(App[bool]):
    """Edit an AI-generated commit message and commit it."""

    CSS = """
    Screen {
        align: center middle;
    }

    #dialog {
        width: auto;
        height: 1fr;
        padding: 1;
    }

    #message {
        width: 84;
        height: 1fr;
        border: round $primary;
        padding: 0 1;
        overflow-y: scroll;
        scrollbar-size-vertical: 1;
    }

    #message:focus {
        border: round $primary;
    }

    #error {
        color: $error;
        width: auto;
        height: auto;
    }

    #actions {
        width: auto;
        height: auto;
        align: center middle;
        padding-top: 1;
    }

    #actions Button {
        margin: 0 1;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("ctrl+s", "commit", "Commit"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, message: str, commit: CommitFunc) -> None:
        super().__init__()
        self._message = message
        self._commit = commit

    @override
    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield TextArea(
                self._message,
                show_line_numbers=True,
                soft_wrap=False,
                tab_behavior="focus",
                id="message",
            )
            yield Static("", id="error")
            with Horizontal(id="actions"):
                yield Button("Commit", variant="primary", id="commit")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        editor = self.query_one("#message", TextArea)
        editor.focus()
        editor.move_cursor(editor.document.end)
        self._resize_editor()

    @on(TextArea.Changed)
    def _on_message_changed(self, _event: TextArea.Changed) -> None:
        self.query_one("#error", Static).update("")
        self._resize_editor()

    def _resize_editor(self) -> None:
        editor = self.query_one("#message", TextArea)
        editor.styles.width = TEXT_COLUMNS + editor.gutter_width + EDITOR_CHROME_WIDTH

    def _show_error(self, message: str) -> None:
        self.query_one("#error", Static).update(message)

    def action_commit(self) -> None:
        editor = self.query_one("#message", TextArea)
        message = editor.text.strip()
        if not message:
            self._show_error("Commit message is empty.")
            return

        try:
            self._commit(message)
        except GitError as exc:
            self._show_error(str(exc))
            return

        self.exit(True)

    def action_cancel(self) -> None:
        self.exit(False)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "commit":
            self.action_commit()
        elif event.button.id == "cancel":
            self.action_cancel()
