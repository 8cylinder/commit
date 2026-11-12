# AGENTS.md

`cm` is a small CLI that generates a git commit message from the working-tree diff
using a pluggable AI provider (AWS Bedrock or DeepSeek). `cm generate` prints the
message to stdout and copies it to the clipboard; `cm commit` opens a Textual editor
and commits. The CLI is built with click.

## Commands

- Run: `uv run cm generate` (or `uv run cm --staged generate`). `uv` manages the env
  and installs the `cm` entry point from `[project.scripts]`.
- Commit via TUI: `uv run cm commit` (or `uv run cm --staged commit`).
- Override selection:
  `uv run cm --provider {auto,bedrock,deepseek} --model <id> <command>`.
- Control color: `uv run cm --color {auto,always,never} <command>`.
- Print the config path: `uv run cm --config`.
- Write bash completions: `uv run cm --completions`.
- Bare `cm` shows help and exits 0. A subcommand is required for real work
  (`generate` or `commit`). Options belong to the base command and must come before
  the subcommand.
- Tests: `make test` (or `uv run pytest`).
- Lint / format: `make lint` / `make fmt` (or `uv run ruff check --fix .`,
  `uv run ruff format .`).
- Check without changing files: `make fmt-check` / `make lint-check`.
- Types: `make type` (or `uv run ty check`; strict: `[tool.ty.rules] all = "error"`).
- Everything: `make check` (format check, lint check, types, tests).
- Locked install plus checks: `make ci`.
- Build: `make build` (wheel and sdist in `dist/`).
- Install the tool and completions: `make install`.
- Do NOT use `python -m cm` — there is no `if __name__ == "__main__"` guard, so it
  exits silently. The installed `cm` script is the only working entrypoint.

## Layout

- `src/cm/cli.py` — click group, `AppGroup`/`AppCommand`, `generate`/`commit`
  subcommands, orchestration, `build_provider()` factory, color handling.
- `src/cm/tui.py` — Textual `CommitApp`: editable message, Commit/Cancel buttons.
- `src/cm/config.py` — `config.toml` loading, `platformdirs` path resolution, and
  `Settings.from_sources()`.
- `src/cm/completions.py` — static bash completion generation/installation.
- `src/cm/providers.py` — `BedrockClaudeProvider`, `DeepSeekProvider`, `AuthError`.
- `src/cm/git.py` — diff/stat/recent-commit helpers plus commit/staging helpers.
  These raise `GitError`; the CLI prints it and exits.
- `src/cm/prompt.py` — prompt template + `wrap_message`.
- `src/cm/clipboard.py` — platform/session-aware clipboard copy.
- `Makefile` — sync/fmt/fmt-check/lint/lint-check/type/test/check/ci/build/install/
  install-completions/uninstall/upgrade/clean targets.

## Provider / model / config resolution

- Provider: `--provider` > `CM_PROVIDER` > `provider` in `config.toml` > auto
  (`DEEPSEEK_API_KEY` or `deepseek_api_key` set → deepseek, else bedrock). Selecting
  deepseek without a key is a `ConfigError`.
- Model: `--model` > `CM_MODEL` > `CM_DEEPSEEK_MODEL`/`CM_BEDROCK_MODEL` >
  `model` in `config.toml` > built-in default (`deepseek-flash` /
  `us.anthropic.claude-opus-4-6-v1`).
- Other settings: `CM_AWS_PROFILE`/`aws_profile`, `CM_AWS_REGION`/`aws_region`,
  `DEEPSEEK_BASE_URL`/`deepseek_base_url`.
- Config lives at `platformdirs.user_config_dir("cm") / "config.toml"`
  (`~/.config/cm/config.toml` on Linux). Use `tomllib`; do not add `tomli`. A
  missing file uses defaults. Invalid TOML names the path and exits nonzero.
  Unknown keys warn on stderr and are ignored. Never create or modify the file from
  `--config`, and never print config values.
- `python-dotenv` and the old `~/.config/cm/.env` file are gone. Environment
  variables in the shell still override config values.
- Bedrock uses AWS profile `bedrock`, region `us-west-2`; auth failures tell the user
  to run `aws sso login --profile bedrock`.

## CLI behavior

- `cm` is a click group using the reusable `AppGroup`/`AppCommand` classes, so
  `-h` and `--help` work on the root and every subcommand. Bare `cm` prints help
  and exits 0; the root uses `invoke_without_command=True` for that.
- `--version` reads the version from package metadata (`pyproject.toml`); never
  hardcode a version in Python.
- `--config`, `--completions`, `--version`, and help are eager and work without a
  subcommand. `--config` prints only the absolute config path and does not load the
  config. `--completions` prints only the completion path to stdout.
- `--color auto` lets Rich detect the terminal and respect `NO_COLOR`,
  `FORCE_COLOR`, and `TERM=dumb`; `always` forces color; `never` disables ANSI.
  Create consoles after parsing `--color` and set `ctx.color` so Click errors agree.
- Human status, warnings, and errors go to stderr. Normal data goes to stdout.
  `cm generate` prints the commit message to stdout with markup disabled so brackets
  in model output are not interpreted.
- Escape dynamic values with `rich.markup.escape()` before passing them to Rich.
- `cm generate` reads ALL uncommitted changes, including untracked files, not just
  staged ones. `--staged` restricts to `git diff --cached`.
- `cm commit` scope: if staged changes exist, it generates from the staged diff and
  commits only staged files. If nothing is staged and `--staged` is not given, it
  generates from all changes and **Commit** runs `git add --all` before committing.
  With `--staged`, nothing staged is an error. Cancelling never stages or commits.
- `cm commit` opens a Textual `TextArea` with line numbers and 80 text columns plus
  the gutter. It has Commit/Cancel buttons, a footer with the key bindings (`Ctrl+S`
  commits, `Ctrl+Q`/`Esc` quits without committing). A failed `git commit` keeps the
  editor open with the error. Textual is imported lazily so `cm generate` stays
  light.

## Bash completions

- `cm --completions` generates a static script from the click command tree. Do not
  use Click's dynamic completion API and do not run Python at tab-press time.
- Destination precedence: first non-empty `BASH_COMPLETION_USER_DIR` entry +
  `completions`, then `XDG_DATA_HOME` + `bash-completion/completions`, then
  `~/.local/share` + `bash-completion/completions`. Use the `.bash` suffix, not
  unsuffixed `cm`. `BASH_COMPLETION_USER_DIR` already points at the
  bash-completion base directory. Installation removes the alternate unsuffixed
  name so an older file cannot shadow the new one.
- Write atomically with mode 0644. Print only the path to stdout; the `source` hint
  and warnings go to stderr.
- The script needs bash >= 4.4 and bash-completion >= 2.18 for auto-loading. Warn on
  stderr when the bash on `PATH` is missing or older, but still write the file.
- macOS `/bin/bash` is 3.2 and zsh is not covered. Document `brew install bash` and
  the lack of zsh support.
- The generator lives in `src/cm/completions.py` and takes the click group object;
  do not import the CLI module from `completions.py`.
- Bash calls the registered completion function with the command name as `$1`,
  the current word as `$2`, and the previous word as `$3`. Only child functions
  generated for subcommands may treat `$1` as the internal start index.

## Tests

- pytest + pytest-cov, branch coverage, `fail_under = 90`.
- Use `click.testing.CliRunner` for CLI tests; do not spawn subprocesses unless the
  test needs a real process (for example running the generated completion script).
- Tests must not touch the real home directory, network, or system config. Use
  `tmp_path` and `monkeypatch` to set `XDG_CONFIG_HOME`, `XDG_DATA_HOME`,
  `BASH_COMPLETION_USER_DIR`, and `HOME` per test.
- Cover `-h`/`--help` on the root and every subcommand, `--version`, `--config`,
  `--completions`, color modes, stdout/stderr separation, and error exit codes.

## Behavior / gotchas

- Clipboard: macOS uses `pbcopy`; Linux chooses by session (`WAYLAND_DISPLAY` →
  `wl-copy`, else `xclip`/`xsel`). When editing `copy_to_clipboard`, do NOT use
  `capture_output`/pipes — `wl-copy` and `xclip` fork a daemon that holds inherited
  pipes open and `subprocess.run` hangs. Output goes to `DEVNULL`.
- Build backend is `uv_build`; `pyproject.toml` pins `uv-build<0.12.0`, which warns
  against newer `uv` (harmless but noisy).
- No Sphinx docs site and no man page. Do not add `docs/`, `sphinx-build`,
  `sphinx-click`, `furo`, or man-page targets.
- License is GPL-2.0-only; keep `LICENSE` and the `pyproject.toml` license metadata
  in sync.
