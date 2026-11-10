from __future__ import annotations

import asyncio

from textual.widgets import Footer, Static, TextArea

from cm.git import GitError
from cm.tui import TEXT_COLUMNS, CommitApp


def test_loads_message_with_line_numbers_and_80_columns() -> None:
    message = "\n".join(f"line {index}" for index in range(10))
    app = CommitApp(message, commit=lambda _text: None)

    async def run() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            editor = app.query_one("#message", TextArea)

            assert editor.text == message
            assert editor.show_line_numbers is True
            assert editor.soft_wrap is False
            assert (
                editor.scrollable_content_region.width - editor.gutter_width
                == TEXT_COLUMNS
            )
            assert app.query_one("#commit").size.height == 1
            assert app.query_one("#cancel").size.height == 1
            assert app.query_one(Footer).size.height == 1

            await pilot.press("escape")

    asyncio.run(run())


def test_commit_button_sends_edited_message() -> None:
    committed: list[str] = []
    app = CommitApp("initial", commit=committed.append)

    async def run() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            editor = app.query_one("#message", TextArea)
            editor.text = "edited subject\n\nedited body"

            await pilot.click("#commit")
            await pilot.pause()

    asyncio.run(run())

    assert committed == ["edited subject\n\nedited body"]
    assert app.return_value is True


def test_cancel_button_does_not_commit() -> None:
    committed: list[str] = []
    app = CommitApp("initial", commit=committed.append)

    async def run() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.click("#cancel")
            await pilot.pause()

    asyncio.run(run())

    assert committed == []
    assert app.return_value is False


def test_ctrl_s_commits_and_exits() -> None:
    committed: list[str] = []
    app = CommitApp("initial", commit=committed.append)

    async def run() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            editor = app.query_one("#message", TextArea)
            editor.text = "keyboard commit"

            await pilot.press("ctrl+s")
            await pilot.pause()

    asyncio.run(run())

    assert committed == ["keyboard commit"]
    assert app.return_value is True


def test_ctrl_q_quits_without_committing() -> None:
    committed: list[str] = []
    app = CommitApp("initial", commit=committed.append)

    async def run() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("ctrl+q")
            await pilot.pause()

    asyncio.run(run())

    assert committed == []
    assert app.return_value is False


def test_commit_failure_keeps_editor_open() -> None:
    def fail(_message: str) -> None:
        raise GitError("hook failed")

    app = CommitApp("initial", commit=fail)

    async def run() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.click("#commit")
            await pilot.pause()

            assert app.is_running
            error = app.query_one("#error", Static)
            assert str(error.content) == "hook failed"

            await pilot.click("#cancel")

    asyncio.run(run())

    assert app.return_value is False


def test_empty_message_is_not_committed() -> None:
    committed: list[str] = []
    app = CommitApp("  \n", commit=committed.append)

    async def run() -> None:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.click("#commit")
            await pilot.pause()

            assert app.is_running
            error = app.query_one("#error", Static)
            assert str(error.content) == "Commit message is empty."

            await pilot.click("#cancel")

    asyncio.run(run())

    assert committed == []
