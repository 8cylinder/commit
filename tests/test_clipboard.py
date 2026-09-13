from __future__ import annotations

import subprocess

import pytest

from cm import clipboard


class _Completed:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode


def _patch_platform(
    monkeypatch: pytest.MonkeyPatch, platform: str, available: set[str]
) -> None:
    monkeypatch.setattr(clipboard.sys, "platform", platform)
    monkeypatch.setattr(
        clipboard.shutil,
        "which",
        lambda name: f"/usr/bin/{name}" if name in available else None,
    )


def test_darwin_uses_pbcopy(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_platform(monkeypatch, "darwin", {"pbcopy"})
    assert clipboard.clipboard_commands() == [["pbcopy"]]


def test_darwin_without_pbcopy(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_platform(monkeypatch, "darwin", set())
    assert clipboard.clipboard_commands() == []


def test_wayland_prefers_wl_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_platform(monkeypatch, "linux", {"wl-copy", "xclip"})
    commands = clipboard.clipboard_commands(
        {"XDG_SESSION_TYPE": "wayland", "WAYLAND_DISPLAY": "wayland-0", "DISPLAY": ":0"}
    )
    assert commands[0] == ["wl-copy"]
    assert ["xclip", "-selection", "clipboard"] in commands


def test_x11_prefers_xclip(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_platform(monkeypatch, "linux", {"wl-copy", "xclip"})
    commands = clipboard.clipboard_commands(
        {"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"}
    )
    assert commands[0] == ["xclip", "-selection", "clipboard"]
    assert commands[1] == ["wl-copy"]


def test_linux_x11_only_display(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_platform(monkeypatch, "linux", {"wl-copy", "xclip"})
    commands = clipboard.clipboard_commands({"DISPLAY": ":0"})
    assert commands[0] == ["xclip", "-selection", "clipboard"]


def test_linux_no_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_platform(monkeypatch, "linux", set())
    assert clipboard.clipboard_commands({"WAYLAND_DISPLAY": "wayland-0"}) == []


def test_unknown_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_platform(monkeypatch, "freebsd", {"pbcopy", "xclip"})
    assert clipboard.clipboard_commands() == []


def test_copy_uses_devnull_and_no_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(command: list[str], **kwargs: object) -> _Completed:
        calls.append({"command": command, **kwargs})
        return _Completed(0)

    monkeypatch.setattr(
        clipboard, "clipboard_commands", lambda environ=None: [["wl-copy"]]
    )
    monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

    assert clipboard.copy_to_clipboard("hello\n") is True

    call = calls[0]
    assert call["command"] == ["wl-copy"]
    assert call["input"] == "hello\n"
    assert call["stdout"] == subprocess.DEVNULL
    assert call["stderr"] == subprocess.DEVNULL
    assert "capture_output" not in call


def test_copy_falls_through_to_next_command(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def fake_run(command: list[str], **kwargs: object) -> _Completed:
        seen.append(command[0])
        return _Completed(0 if command[0] == "xclip" else 1)

    monkeypatch.setattr(
        clipboard,
        "clipboard_commands",
        lambda environ=None: [["wl-copy"], ["xclip", "-selection", "clipboard"]],
    )
    monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

    assert clipboard.copy_to_clipboard("x") is True
    assert seen == ["wl-copy", "xclip"]


def test_copy_returns_false_without_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clipboard, "clipboard_commands", lambda environ=None: [])
    assert clipboard.copy_to_clipboard("x") is False


def test_copy_handles_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: object) -> _Completed:
        raise FileNotFoundError

    monkeypatch.setattr(
        clipboard, "clipboard_commands", lambda environ=None: [["gone"]]
    )
    monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

    assert clipboard.copy_to_clipboard("x") is False


def test_copy_handles_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **kwargs: object) -> _Completed:
        raise subprocess.TimeoutExpired(command, 10)

    monkeypatch.setattr(
        clipboard, "clipboard_commands", lambda environ=None: [["slow"]]
    )
    monkeypatch.setattr(clipboard.subprocess, "run", fake_run)

    assert clipboard.copy_to_clipboard("x") is False
