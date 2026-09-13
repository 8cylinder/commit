from __future__ import annotations

import textwrap


def build_prompt(diff: str, stat: str, recent_commits: str) -> str:
    return f"""Write a concise git commit message for the following changes.

Rules:
- First line: short summary (max 72 chars), imperative mood
- Then a blank line
- Then provide a brief bulleted body explaining *why* the changes were made, not just *what* changed (skip body if the change is trivial).
- use asterisks for the bullets
- wrap the bullet points at 72 chars
- No markdown formatting, no backticks
- Just the commit message, nothing else
- Do NOT include any AI attribution, co-authorship tags, or "Generated with Claude" disclaimers.

Recent commit messages (match this style and tone):
{recent_commits}

File summary:
{stat}

Diff:
{diff}"""


def wrap_message(message: str) -> str:
    lines = message.splitlines()
    result = []
    for line in lines:
        if line.startswith("* "):
            wrapped = textwrap.fill(
                line[2:], width=72, initial_indent="* ", subsequent_indent="  "
            )
            result.append(wrapped)
        else:
            result.append(line)
    return "\n".join(result)
