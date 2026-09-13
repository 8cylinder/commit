# AGENTS.md

`cm` is a small CLI that generates a git commit message from the working-tree diff
using AWS Bedrock, prints it, and copies it to the clipboard. All logic lives in
`src/cm/__init__.py`; there are no tests, lint config, or CI.

## Commands

- Run: `uv run cm` (or `uv run cm --staged`). `uv` manages the env and installs the
  `cm` entry point from `[project.scripts]`.
- Do NOT use `python -m cm` — there is no `if __name__ == "__main__"` guard, so it
  exits silently. The installed `cm` script is the only working entrypoint.

## Behavior / gotchas

- Default mode reads ALL uncommitted changes, including untracked files, not just
  staged ones. `--staged` restricts to `git diff --cached`.
- `generate_commit_message` hardcodes AWS profile `bedrock`, region `us-west-2`, and
  model `us.anthropic.claude-opus-4-6-v1`. Auth failures tell the user to run
  `aws sso login --profile bedrock`.
- Rich output goes to stderr; the final step pipes the message to `pbcopy` with no
  error handling. `pbcopy` is macOS-only, so running on Linux raises unless `pbcopy`
  exists.
- Build backend is `uv_build`; `pyproject.toml` pins `uv-build<0.12.0`, which warns
  against newer `uv` (harmless but noisy).
