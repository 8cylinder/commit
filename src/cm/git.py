from __future__ import annotations

import subprocess
import sys


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
    )


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


def get_recent_commits() -> str:
    return _git("log", "--oneline", "-20").stdout.strip()
