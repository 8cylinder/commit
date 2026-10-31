from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from cm import completions


def test_completion_path_uses_xdg_data_home(tmp_path: Path) -> None:
    path = completions.completion_path({"XDG_DATA_HOME": str(tmp_path)})

    assert path == tmp_path / "bash-completion" / "completions" / "cm"


def test_completion_path_falls_back_to_local_share(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    path = completions.completion_path({})

    assert path == (
        tmp_path / ".local" / "share" / "bash-completion" / "completions" / "cm"
    )


def test_install_completion_writes_script(tmp_path: Path) -> None:
    environ = {"XDG_DATA_HOME": str(tmp_path)}

    path = completions.install_completion(environ)

    assert path == tmp_path / "bash-completion" / "completions" / "cm"
    assert path.read_text(encoding="utf-8") == (completions.generate_bash_completion())


def test_generated_script_is_static_bash_completion() -> None:
    script = completions.generate_bash_completion()

    assert "complete -o nosort -F _cm_completion cm" in script
    assert "compopt -o nosort" in script
    assert "auto bedrock deepseek" in script
    for option in (
        "-h",
        "--help",
        "-s",
        "--staged",
        "--provider",
        "--model",
        "--config",
        "--completions",
        "--version",
    ):
        assert option in script


def test_installed_bash_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(completions.shutil, "which", lambda name: "/bin/bash")
    monkeypatch.setattr(
        completions.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout="GNU bash, version 5.2.15(1)-release (x86_64-pc-linux-gnu)\n"
        ),
    )

    assert completions.installed_bash_version() == (5, 2)


def test_installed_bash_version_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(completions.shutil, "which", lambda name: None)

    assert completions.installed_bash_version() is None


def test_installed_bash_version_subprocess_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(completions.shutil, "which", lambda name: "/bin/bash")

    def fail(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError("boom")

    monkeypatch.setattr(completions.subprocess, "run", fail)

    assert completions.installed_bash_version() is None
