import json
import os
import subprocess
import sys
import tempfile
import textwrap

import boto3
from botocore.exceptions import (
    CredentialRetrievalError,
    NoCredentialsError,
    SSOError,
    TokenRetrievalError,
)
from rich.console import Console
from rich.status import Status


def get_diff():
    diff = subprocess.run(
        ["git", "diff"],
        capture_output=True, text=True
    )
    if diff.returncode != 0:
        print("Error: not a git repository or git not available", file=sys.stderr)
        sys.exit(1)

    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        capture_output=True, text=True
    )
    untracked_files = untracked.stdout.strip().splitlines()

    untracked_content = ""
    for filepath in untracked_files:
        content = subprocess.run(
            ["git", "diff", "--no-index", "/dev/null", filepath],
            capture_output=True, text=True
        )
        untracked_content += content.stdout

    combined = diff.stdout + untracked_content
    if not combined.strip():
        print("Error: no uncommitted changes.", file=sys.stderr)
        sys.exit(1)
    return combined


def get_stat():
    stat = subprocess.run(
        ["git", "diff", "--stat"],
        capture_output=True, text=True
    )

    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        capture_output=True, text=True
    )
    untracked_files = untracked.stdout.strip().splitlines()

    result = stat.stdout
    if untracked_files:
        result += "\nNew untracked files:\n"
        for f in untracked_files:
            result += f"  {f}\n"
    return result


def generate_commit_message(diff, stat):
    session = boto3.Session(profile_name="bedrock")
    client = session.client("bedrock-runtime", region_name="us-west-2")

    prompt = f"""Write a concise git commit message for the following changes.

Rules:
- First line: short summary (max 72 chars), imperative mood
- Then a blank line
- Then provide a brief bulleted body explaining *why* the changes were made, not just *what* changed (skip body if the change is trivial).
- use asterisks for the bullets
- wrap the bullet points at 72 chars
- No markdown formatting, no backticks
- Just the commit message, nothing else
- Do NOT include any AI attribution, co-authorship tags, or "Generated with Claude" disclaimers.

File summary:
{stat}

Diff:
{diff}"""

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    })

    response = client.invoke_model(
        modelId="us.anthropic.claude-sonnet-4-20250514-v1:0",
        contentType="application/json",
        accept="application/json",
        body=body,
    )

    response_body = json.loads(response["body"].read())
    raw = response_body["content"][0]["text"].strip()
    return wrap_message(raw)


def wrap_message(message):
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


def open_editor(message):
    editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "vi"))

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".COMMIT_EDITMSG", prefix="cm-", delete=False
    ) as f:
        f.write(message)
        f.write("\n")
        tmpfile = f.name

    try:
        subprocess.run([editor, tmpfile], check=True)
        with open(tmpfile) as f:
            edited = f.read().strip()
        return edited
    finally:
        os.unlink(tmpfile)


def main():
    diff = get_diff()
    stat = get_stat()

    console = Console(stderr=True)
    try:
        with Status("Generating commit message...", console=console):
            message = generate_commit_message(diff, stat)
    except (NoCredentialsError, TokenRetrievalError, SSOError, CredentialRetrievalError):
        console.print(
            "[bold red]Error:[/] AWS session has expired or credentials are missing.\n"
            "Run [bold]aws sso login --profile bedrock[/] to authenticate."
        )
        sys.exit(1)

    console.print(message)
    subprocess.run(["pbcopy"], input=message, text=True)
