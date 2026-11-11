# cm

`cm` is a small command-line tool that reads your uncommitted git changes, asks an
AI provider to write a commit message that matches your repo's recent style,
prints it, and copies it to your clipboard.

Source: <https://github.com/8cylinder/commit>

It supports two providers and can switch between them automatically:

- **Claude on AWS Bedrock** — uses your existing AWS SSO profile.
- **DeepSeek** — uses a DeepSeek API key.

The message is generated from the diff, a file summary, and your last 20 commit
messages so the tone and format stay consistent.


## Requirements

- Python 3.13+
- [`uv`](https://docs.astral.sh/uv/)
- One of:
  - AWS credentials with Bedrock access (profile `bedrock`), or
  - a DeepSeek API key
- For bash completions only:
  - bash 4.4 or newer
  - bash-completion 2.18 or newer for automatic loading

`cm` targets Linux and macOS. Clipboard integration uses `pbcopy` on macOS,
`wl-copy` on Wayland, and `xclip` or `xsel` on X11.


## Installation

Clone the repository and install the command:

```bash
git clone https://github.com/8cylinder/commit.git
cd commit
make sync
make install
```

`make install` installs `cm` as an editable tool and writes bash completions. To
install only the command:

```bash
uv tool install .
```

Or install in editable mode so source changes take effect without reinstalling:

```bash
uv tool install --editable .
```

Run from a checkout without installing:

```bash
uv run cm generate
```


## Quick start

Generate a message from all uncommitted changes, including untracked files:

```bash
cm generate
```

Generate a message from staged changes only:

```bash
cm --staged generate
```

Edit the generated message in a terminal editor and commit:

```bash
cm commit
```


## Command reference

```text
cm [OPTIONS] [COMMAND] [ARGS]...
```

Options belong to the base `cm` command and must come before the subcommand.
Running `cm` without a subcommand prints help.

### Commands

| Command | Description |
| --- | --- |
| `generate` | Generate a commit message from the selected changes, print it to stdout, and copy it to the clipboard. |
| `commit` | Generate a message in an editable TUI, then commit with git. |

### Options

| Option | Description |
| --- | --- |
| `-h`, `--help` | Show help and exit. `-h` works on every command. |
| `--version` | Show the version (read from package metadata) and exit. |
| `--config` | Print the config file path and exit. |
| `--completions` | Write the static bash completion script and exit. |
| `--color {auto,always,never}` | Control colored output. Defaults to `auto`. |
| `-s`, `--staged` | Generate from staged changes only. For `cm commit`, also require staged changes instead of auto-staging. |
| `--provider {auto,bedrock,deepseek}` | Choose the provider; defaults to auto-detection. |
| `--model <id>` | Override the provider's model id. |

`cm generate` prints the generated message to stdout. Progress, warnings, and
errors go to stderr, so the message can be redirected or piped cleanly.

### Commit TUI

`cm commit` generates a message and opens a Textual editor. The editor shows line
numbers and is 80 text columns wide, plus the line-number gutter. It has **Commit**
and **Cancel** buttons, and a shortcut bar at the bottom; `Ctrl+S` commits and
closes, while `Ctrl+Q` (or `Esc`) quits without committing.

- If staged changes exist, the message is generated from the staged diff and only
  staged changes are committed.
- If nothing is staged, the message is generated from all changes and **Commit**
  stages everything first.
- `--staged` disables auto-staging, so nothing staged is an error.
- If `git commit` fails, the editor stays open with the error so you can fix the
  message and retry. Cancelling does not stage or commit anything.


## Configuration

`cm` resolves settings from four sources, in order of precedence:

1. Command-line flags (`--provider`, `--model`)
2. Environment variables
3. `config.toml`
4. Built-in defaults

### Config file location

The config file is `config.toml` in the platform's per-user config directory.
On Linux that is:

```text
~/.config/cm/config.toml
```

Run `cm --config` to print the effective path. A missing file is not an error;
`cm` uses built-in defaults. `cm` never creates or modifies the file.

An example:

```toml
# ~/.config/cm/config.toml
provider = "deepseek"
model = "deepseek-flash"

# aws_profile = "bedrock"
# aws_region = "us-west-2"
# deepseek_base_url = "https://api.deepseek.com"
```

The DeepSeek API key can be set as `deepseek_api_key` in the file, but exporting
`DEEPSEEK_API_KEY` is recommended so the secret stays out of the config file.
Unknown keys produce a warning on stderr and are ignored. Invalid TOML is an
error that names the file.

### Environment variables

| Variable | Provider | Description |
| --- | --- | --- |
| `CM_PROVIDER` | both | Which provider to use: `auto`, `bedrock`, or `deepseek`. |
| `CM_MODEL` | both | Universal model override. |
| `CM_BEDROCK_MODEL` | bedrock | Bedrock model id. |
| `CM_AWS_PROFILE` | bedrock | AWS profile to use. |
| `CM_AWS_REGION` | bedrock | AWS region for Bedrock. |
| `DEEPSEEK_API_KEY` | deepseek | Required when using DeepSeek. |
| `DEEPSEEK_BASE_URL` | deepseek | API base URL. |
| `CM_DEEPSEEK_MODEL` | deepseek | DeepSeek model name. |

For the model, the precedence is `--model` > `CM_MODEL` >
`CM_DEEPSEEK_MODEL` or `CM_BEDROCK_MODEL` > `model` in `config.toml` >
built-in default.

### Automatic provider selection

When the provider is unset (or `auto`):

- If `DEEPSEEK_API_KEY` is set (or `deepseek_api_key` is in the config) →
  **DeepSeek**
- Otherwise → **Bedrock**

Selecting `deepseek` explicitly without a key is an error. AWS authentication
failures tell you to run:

```bash
aws sso login --profile bedrock
```

### Example: DeepSeek

```bash
export DEEPSEEK_API_KEY=sk-your-key-here
cm generate
```

Or in `config.toml`:

```toml
provider = "deepseek"
model = "deepseek-flash"
```

### Example: Claude on Bedrock

```toml
# ~/.config/cm/config.toml
provider = "bedrock"
aws_profile = "bedrock"
aws_region = "us-west-2"
model = "us.anthropic.claude-opus-4-6-v1"
```

Then authenticate and run:

```bash
aws sso login --profile bedrock
cm generate
```


## Bash completions

`cm --completions` writes a static completion script and exits. The destination is
resolved in this order:

1. `BASH_COMPLETION_USER_DIR` (first non-empty colon-separated entry)
2. `XDG_DATA_HOME`
3. `~/.local/share`

The script is written to
`<base>/bash-completion/completions/cm.bash`. Only the absolute path is printed
to stdout; the `source` hint and warnings go to stderr:

```bash
$ cm --completions
/home/user/.local/share/bash-completion/completions/cm.bash
To use it in this shell:
  source /home/user/.local/share/bash-completion/completions/cm.bash
```

The script requires **bash 4.4 or newer** (it uses `compopt`, `mapfile`, and
`complete -o nosort`) and bash-completion 2.18 or newer for automatic loading. If
the `bash` on your `PATH` is older, `cm` prints a warning. Rerun
`cm --completions` after changing commands or options.

On macOS `/bin/bash` is still 3.2 and the default shell is zsh, so:

- install a newer bash (for example `brew install bash`) to use these completions;
- zsh completions are **not** generated.


## Development

```bash
make sync       # create the environment and install dev tools
make fmt        # format with ruff
make fmt-check  # check formatting without changing files
make lint       # lint and auto-fix with ruff
make lint-check # lint without changing files
make type       # strict type check with ty
make test       # run the test suite
make check      # format check, lint, types, and tests
make ci         # install locked dependencies and run check
make build      # build the wheel and sdist into dist/
make install    # install cm and bash completions
make upgrade    # upgrade dependencies
make clean      # remove build and test artifacts
```

The same commands work directly with `uv`, for example `uv run pytest` or
`uv run ty check`. Run a single test with:

```bash
uv run pytest tests/test_cli.py::test_version_comes_from_package_metadata
```


## License

GPL-2.0-only. See [LICENSE](LICENSE).

Copyright (C) 2026 Sheldon McGrandle


## Contributing

Issues and pull requests are welcome at
<https://github.com/8cylinder/commit>.
