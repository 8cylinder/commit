from __future__ import annotations

import subprocess

import pytest

from cm import git

RunArgs = list[str]
RunKwargs = dict[str, object]


def _result(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout, "")


def test_get_diff_staged(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(
        command: RunArgs, **kwargs: RunKwargs
    ) -> subprocess.CompletedProcess[str]:
        return _result("staged diff\n")

    monkeypatch.setattr(git.subprocess, "run", fake_run)
    assert git.get_diff(staged=True) == "staged diff\n"


def test_get_diff_staged_requires_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(git.subprocess, "run", lambda *a, **k: _result(""))
    with pytest.raises(SystemExit):
        git.get_diff(staged=True)


def test_get_diff_staged_requires_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        git.subprocess, "run", lambda *a, **k: _result("", returncode=1)
    )
    with pytest.raises(SystemExit):
        git.get_diff(staged=True)


def test_get_diff_unstaged_includes_untracked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(
        command: RunArgs, **kwargs: RunKwargs
    ) -> subprocess.CompletedProcess[str]:
        if command[1] == "ls-files":
            return _result("new.txt\n")
        if "--no-index" in command:
            return _result(f"content of {command[-1]}\n")
        return _result("tracked change\n")

    monkeypatch.setattr(git.subprocess, "run", fake_run)
    assert git.get_diff() == "tracked change\ncontent of new.txt\n"


def test_get_diff_unstaged_requires_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(
        command: RunArgs, **kwargs: RunKwargs
    ) -> subprocess.CompletedProcess[str]:
        return _result("")

    monkeypatch.setattr(git.subprocess, "run", fake_run)
    with pytest.raises(SystemExit):
        git.get_diff()


def test_get_stat_unstaged_lists_untracked(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(
        command: RunArgs, **kwargs: RunKwargs
    ) -> subprocess.CompletedProcess[str]:
        if command[1] == "ls-files":
            return _result("a.txt\nb.txt\n")
        return _result(" a.txt | 1 +\n")

    monkeypatch.setattr(git.subprocess, "run", fake_run)
    assert git.get_stat() == " a.txt | 1 +\n\nNew untracked files:\n  a.txt\n  b.txt\n"


def test_get_stat_staged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(git.subprocess, "run", lambda *a, **k: _result("cached stat\n"))
    assert git.get_stat(staged=True) == "cached stat\n"


def test_get_recent_commits_strips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(git.subprocess, "run", lambda *a, **k: _result("abc\ndef\n"))
    assert git.get_recent_commits() == "abc\ndef"
