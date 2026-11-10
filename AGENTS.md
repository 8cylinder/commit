# AGENTS.md

`cm` is a small CLI that generates a git commit message from the working-tree diff
using a pluggable AI provider (AWS Bedrock or DeepSeek), prints it, and copies it to
the clipboard. The CLI is built with click.

## Commands

- Run: `uv run cm generate` (or `uv run cm --staged generate`). `uv` manages the env
  and installs the `cm` entry point from `[project.scripts]`.
- Override selection:
  `uv run cm --provider {auto,bedrock,deepseek} --model <id> generate`.
- Print the config path: `uv run cm --config`.
- Write bash completions: `uv run cm --completions`.
- Bare `cm` is an error; a subcommand is required (currently only `generate`).
  Options belong to the base command and must come before the subcommand.
- Tests: `make test` (or `uv run pytest`).
- Lint / format: `make lint` / `make fmt` (or `uv run ruff check --fix .`,
  `uv run ruff format .`).
- Types: `make type` (or `uv run ty check`; strict: `[tool.ty.rules] all = "error"`).
- Everything: `make check`.
- Do NOT use `python -m cm` — there is no `if __name__ == "__main__"` guard, so it
  exits silently. The installed `cm` script is the only working entrypoint.

## Layout

- `src/cm/cli.py` — click group, `generate` subcommand, orchestration,
  `build_provider()` factory.
- `src/cm/config.py` — `Settings.from_env()` resolution + `~/.config/cm/.env` loading.
- `src/cm/completions.py` — static bash completion generation/installation.
- `src/cm/providers.py` — `BedrockClaudeProvider`, `DeepSeekProvider`, `AuthError`.
- `src/cm/git.py` — diff/stat/recent-commit helpers.
- `src/cm/prompt.py` — prompt template + `wrap_message`.
- `src/cm/clipboard.py` — platform/session-aware clipboard copy.
- `Makefile` — sync/fmt/lint/type/test/check/install/upgrade targets.

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

## CLI behavior

- `cm` is a click group. `cm generate` does the work; bare `cm` fails with
  `Missing command.` and exit code 2. Options live on the group and must precede the
  subcommand (for example `cm --staged generate`).
- `-h` and `--help` both show help.
- `--version` reads the version from package metadata (`pyproject.toml`); never
  hardcode a version in Python.
- `--config` prints `~/.config/cm/.env` and exits without loading config or git.
- `--completions` writes a **static** bash script to
  `$XDG_DATA_HOME/bash-completion/completions/cm` (fallback
  `~/.local/share/bash-completion/completions/cm`), prints the path and a `source`
  hint, and exits. It warns when bash on `PATH` is older than 4.4. Only bash is
  supported; macOS `/bin/bash` 3.2 is too old and zsh is not covered.
- `--version`, `--config`, `--completions`, and `-h`/`--help` are eager and work
  without a subcommand.
- Rich output goes to stderr. Color is disabled automatically when stderr is not a
  terminal. The generated commit message is printed with markup disabled so brackets
  in model output are not interpreted.
- `cm generate` reads ALL uncommitted changes, including untracked files, not just
  staged ones. `--staged` restricts to `git diff --cached`.

## Behavior / gotchas

- Clipboard: macOS uses `pbcopy`; Linux chooses by session (`WAYLAND_DISPLAY` →
  `wl-copy`, else `xclip`/`xsel`). When editing `copy_to_clipboard`, do NOT use
  `capture_output`/pipes — `wl-copy` and `xclip` fork a daemon that holds inherited
  pipes open and `subprocess.run` hangs. Output goes to `DEVNULL`.
- Build backend is `uv_build`; `pyproject.toml` pins `uv-build<0.12.0`, which warns
  against newer `uv` (harmless but noisy).
