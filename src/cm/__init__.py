import json
import os
import subprocess
import sys
import tempfile

import boto3


def get_staged_diff():
    result = subprocess.run(
        ["git", "diff", "--cached"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("Error: not a git repository or git not available", file=sys.stderr)
        sys.exit(1)
    if not result.stdout.strip():
        print("Error: no staged changes. Stage files with 'git add' first.", file=sys.stderr)
        sys.exit(1)
    return result.stdout


def get_staged_stat():
    result = subprocess.run(
        ["git", "diff", "--cached", "--stat"],
        capture_output=True, text=True
    )
    return result.stdout


def generate_commit_message(diff, stat):
    client = boto3.client("bedrock-runtime", region_name="us-west-2")

    prompt = f"""Write a concise git commit message for the following changes.

Rules:
- First line: short summary (max 72 chars), imperative mood
- Then a blank line
- Then bullet points explaining what changed and why (if non-obvious)
- No markdown formatting, no backticks
- Just the commit message, nothing else

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
    return response_body["content"][0]["text"].strip()


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
    diff = get_staged_diff()
    stat = get_staged_stat()

    print("Generating commit message...", file=sys.stderr)
    message = generate_commit_message(diff, stat)

    edited = open_editor(message)

    if not edited:
        print("Aborting commit: empty message.", file=sys.stderr)
        sys.exit(1)

    result = subprocess.run(["git", "commit", "-m", edited])
    sys.exit(result.returncode)
