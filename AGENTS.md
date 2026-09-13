# AGENTS.md

`cm` is a small CLI that generates a git commit message from the working-tree diff
using a pluggable AI provider (AWS Bedrock or DeepSeek), prints it, and copies it to
the clipboard.

## Commands

- Run: `uv run cm` (or `uv run cm --staged`). `uv` manages the env and installs the
  `cm` entry point from `[project.scripts]`.
- Override selection: `uv run cm --provider {auto,bedrock,deepseek} --model <id>`.
- Tests: `uv run pytest`.
- Lint / format: `uv run ruff check .` and `uv run ruff format .`.
- Types: `uv run ty check` (strict: `[tool.ty.rules] all = "error"`).
- Do NOT use `python -m cm` — there is no `if __name__ == "__main__"` guard, so it
  exits silently. The installed `cm` script is the only working entrypoint.

## Layout

- `src/cm/cli.py` — argparse, orchestration, `build_provider()` factory.
- `src/cm/config.py` — `Settings.from_env()` resolution + `~/.config/cm/.env` loading.
- `src/cm/providers.py` — `BedrockClaudeProvider`, `DeepSeekProvider`, `AuthError`.
- `src/cm/git.py` — diff/stat/recent-commit helpers.
- `src/cm/prompt.py` — prompt template + `wrap_message`.
- `src/cm/clipboard.py` — platform/session-aware clipboard copy.

## Provider / model resolution

- Provider: `--provider` > `CM_PROVIDER` > auto (`DEEPSEEK_API_KEY` set → deepseek,
  else bedrock). Selecting deepseek without a key is a `ConfigError`.
- Model: `--model` > `CM_MODEL` > `CM_DEEPSEEK_MODEL`/`CM_BEDROCK_MODEL` > built-in
  default (`deepseek-flash` / `us.anthropic.claude-opus-4-6-v1`).
- Bedrock uses AWS profile `bedrock`, region `us-west-2`; auth failures tell the user
  to run `aws sso login --profile bedrock`.
- First run: if `~/.config/cm` is missing it is created with a `.env.sample`. If the
  directory already exists, nothing is written (a deliberately deleted sample stays
  deleted).

## Behavior / gotchas

- Default mode reads ALL uncommitted changes, including untracked files, not just
  staged ones. `--staged` restricts to `git diff --cached`.
- Rich output goes to stderr.
- Clipboard: macOS uses `pbcopy`; Linux chooses by session (`WAYLAND_DISPLAY` →
  `wl-copy`, else `xclip`/`xsel`). When editing `copy_to_clipboard`, do NOT use
  `capture_output`/pipes — `wl-copy` and `xclip` fork a daemon that holds inherited
  pipes open and `subprocess.run` hangs. Output goes to `DEVNULL`.
- Build backend is `uv_build`; `pyproject.toml` pins `uv-build<0.12.0`, which warns
  against newer `uv` (harmless but noisy).
