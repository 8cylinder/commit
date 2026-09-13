from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping

_WAYLAND = (("wl-copy",),)
_X11 = (
    ("xclip", "-selection", "clipboard"),
    ("xsel", "--clipboard", "--input"),
)


def _available(command: tuple[str, ...]) -> bool:
    return shutil.which(command[0]) is not None


def clipboard_commands(
    environ: Mapping[str, str] | None = None,
) -> list[list[str]]:
    """Return the clipboard-copy commands to try, in preference order.

    macOS uses pbcopy. Linux picks the order from the session type:
    WAYLAND_DISPLAY / XDG_SESSION_TYPE=wayland prefers wl-copy, X11 prefers
    xclip then xsel. Only tools present on PATH are returned.
    """
    env = os.environ if environ is None else environ

    if sys.platform == "darwin":
        return [["pbcopy"]] if shutil.which("pbcopy") else []

    if sys.platform.startswith(("win", "cygwin", "msys")):
        return [["clip"]] if shutil.which("clip") else []

    if not sys.platform.startswith("linux"):
        return []

    session = (env.get("XDG_SESSION_TYPE") or "").lower()
    is_wayland = session == "wayland" or bool(env.get("WAYLAND_DISPLAY"))
    is_x11 = session == "x11" or bool(env.get("DISPLAY"))

    if is_wayland:
        order = (*_WAYLAND, *_X11)
    elif is_x11:
        order = (*_X11, *_WAYLAND)
    else:
        order = (*_WAYLAND, *_X11)

    return [list(command) for command in order if _available(command)]


def clipboard_command(environ: Mapping[str, str] | None = None) -> list[str] | None:
    """Return the preferred clipboard command, or None if none are available."""
    commands = clipboard_commands(environ)
    return commands[0] if commands else None


def copy_to_clipboard(text: str, environ: Mapping[str, str] | None = None) -> bool:
    """Copy text to the clipboard, trying each candidate until one succeeds.

    Clipboard tools such as wl-copy and xclip fork a daemon that can keep
    inherited pipes open, so output is sent to DEVNULL rather than captured.
    """
    for command in clipboard_commands(environ):
        try:
            result = subprocess.run(
                command,
                input=text,
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0:
            return True
    return False
