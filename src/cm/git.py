from __future__ import annotations

import subprocess
import sys


class GitError(Exception):
    """A git operation failed."""


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
    )


def _run_git(*args: str) -> subprocess.CompletedProcess[str]:
    try:
        return _git(*args)
    except OSError as exc:
        raise GitError(f"could not run git: {exc}") from exc


def _git_error(result: subprocess.CompletedProcess[str], fallback: str) -> GitError:
    detail = result.stderr.strip() or result.stdout.strip() or fallback
    return GitError(detail)


def get_diff(staged: bool = False) -> str:
    if staged:
        diff = _git("diff", "--cached")
        if diff.returncode != 0:
            print("Error: not a git repository or git not available", file=sys.stderr)
            sys.exit(1)
        if not diff.stdout.strip():
            print("Error: no staged changes.", file=sys.stderr)
            sys.exit(1)
        return diff.stdout

    diff = _git("diff")
    if diff.returncode != 0:
        print("Error: not a git repository or git not available", file=sys.stderr)
        sys.exit(1)

    untracked = _git("ls-files", "--others", "--exclude-standard")
    untracked_files = untracked.stdout.strip().splitlines()

    untracked_content = ""
    for filepath in untracked_files:
        content = _git("diff", "--no-index", "/dev/null", filepath)
        untracked_content += content.stdout

    combined = diff.stdout + untracked_content
    if not combined.strip():
        print("Error: no uncommitted changes.", file=sys.stderr)
        sys.exit(1)
    return combined


def get_stat(staged: bool = False) -> str:
    if staged:
        return _git("diff", "--cached", "--stat").stdout

    stat = _git("diff", "--stat")
    untracked = _git("ls-files", "--others", "--exclude-standard")
    untracked_files = untracked.stdout.strip().splitlines()

    result = stat.stdout
    if untracked_files:
        result += "\nNew untracked files:\n"
        for f in untracked_files:
            result += f"  {f}\n"
    return result


def has_staged_changes() -> bool:
    """Return True when the index differs from HEAD."""
    result = _run_git("diff", "--cached", "--quiet")
    if result.returncode == 0:
        return False
    if result.returncode == 1:
        return True
    raise _git_error(result, "not a git repository or git not available")


def commit(message: str) -> str:
    """Commit the staged changes with the given message."""
    try:
        result = subprocess.run(
            ["git", "commit", "-F", "-"],
            input=message.rstrip() + "\n",
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise GitError(f"could not run git: {exc}") from exc

    if result.returncode != 0:
        raise _git_error(result, "git commit failed")
    return result.stdout.strip()


def commit_all(message: str) -> str:
    """Stage all changes, then commit them with the given message."""
    result = _run_git("add", "--all")
    if result.returncode != 0:
        raise _git_error(result, "git add failed")
    return commit(message)


def get_recent_commits() -> str:
    return _git("log", "--oneline", "-20").stdout.strip()
