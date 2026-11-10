# cm

`cm` is a small command-line tool that reads your uncommitted git changes, asks an AI
provider to write a commit message that matches your repo's recent style, prints it,
and copies it to your clipboard.

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


## Install

Clone the repository and install the `cm` command globally as a tool:

```bash
git clone https://github.com/8cylinder/commit.git
cd commit
uv tool install .
```

Or build a wheel/sdist first:

```bash
uv build
uv tool install dist/cm-*.whl
```

Install in editable mode so source changes take effect without reinstalling:

```bash
uv tool install --editable .
```

Run from a checkout without installing (uses the local project environment):

```bash
uv run cm generate
```


## Usage

```bash
cm generate                     # all uncommitted changes (including untracked files)
cm --staged generate            # staged changes only
cm --provider deepseek generate # force DeepSeek
cm --provider bedrock --model us.anthropic.claude-opus-4-6-v1 generate
cm commit                       # edit the generated message and commit
cm --staged commit              # commit staged changes only
cm --config                     # print the config file path
cm --completions                # write bash completions
cm --version                    # print the version from pyproject.toml
```

Options belong to the base `cm` command, so they must come before the
subcommand. Running `cm` without a subcommand prints an error.

### Commands

| Command | Description |
| --- | --- |
| `generate` | Generate a commit message from the selected changes, print it, and copy it to the clipboard. |
| `commit` | Generate a message in an editable TUI, then commit with git. |

### Options

| Option | Description |
| --- | --- |
| `-h`, `--help` | Show help and exit. |
| `--version` | Show the version (read from package metadata) and exit. |
| `--config` | Print the config file path and exit. |
| `--completions` | Write a static bash completion script and exit. |
| `-s`, `--staged` | Generate from staged changes only. For `cm commit`, also require staged changes instead of auto-staging. |
| `--provider {auto,bedrock,deepseek}` | Choose the provider; defaults to auto-detection. |
| `--model <id>` | Override the provider's model id. |

`cm generate` prints the generated message to stderr and copies it to the clipboard.

### Commit TUI

`cm commit` generates a message and opens a Textual editor. The editor shows line
numbers and is 80 text columns wide, plus the line-number gutter. It has **Commit** and
**Cancel** buttons; `Ctrl+S` commits and `Esc` cancels.

- If staged changes exist, the message is generated from the staged diff and only
  staged changes are committed.
- If nothing is staged, the message is generated from all changes and **Commit**
  stages everything first.
- `--staged` disables auto-staging, so nothing staged is an error.
- If `git commit` fails, the editor stays open with the error so you can fix the
  message and retry. Cancelling does not stage or commit anything.

Clipboard support:

- macOS: `pbcopy`
- Linux (Wayland): `wl-copy`
- Linux (X11): `xclip` or `xsel`


## Bash completions

`cm --completions` writes a static completion script to
`$XDG_DATA_HOME/bash-completion/completions/cm`, falling back to
`~/.local/share/bash-completion/completions/cm` when `XDG_DATA_HOME` is unset. It
prints the path and a `source` command for the current terminal.

The script requires **bash 4.4 or newer** (it uses `compopt` and
`complete -o nosort`) and bash-completion 2.x to auto-load it. If the `bash` on your
`PATH` is older, `cm` prints a warning.

On macOS `/bin/bash` is still 3.2 and the default shell is zsh, so:

- install a newer bash (for example `brew install bash`) to use these completions;
- zsh completions are **not** generated.

The unsuffixed `cm` filename works with bash-completion; versions 2.18 and newer also
accept `cm.bash`.


## Configuration

`cm` resolves settings from four sources, in order of precedence:

1. Command-line flags (`--provider`, `--model`)
2. Environment variables
3. The config file
4. Built-in defaults

### Config file location

`cm` loads environment variables from:

```
~/.config/cm/.env
```

Run `cm --config` to print that path.

The first time you run `cm`, if `~/.config/cm` does not exist, it is created with a
sample file at `~/.config/cm/.env.sample`. Copy that to `.env` and edit it:

```bash
cp ~/.config/cm/.env.sample ~/.config/cm/.env
```

The `.env` file is optional — environment variables and AWS SSO credentials work with
no config file at all. Variables already set in your shell take precedence over the
file.

### Options

| Variable | Provider | Default | Description |
| --- | --- | --- | --- |
| `CM_PROVIDER` | both | `auto` | Which provider to use: `auto`, `bedrock`, or `deepseek`. |
| `CM_MODEL` | both | — | Universal model override; wins over the provider-specific variables below. |
| `CM_BEDROCK_MODEL` | bedrock | `us.anthropic.claude-opus-4-6-v1` | Bedrock model id. |
| `CM_AWS_PROFILE` | bedrock | `bedrock` | AWS profile to use. |
| `CM_AWS_REGION` | bedrock | `us-west-2` | AWS region for Bedrock. |
| `DEEPSEEK_API_KEY` | deepseek | — | Required when using DeepSeek. |
| `DEEPSEEK_BASE_URL` | deepseek | `https://api.deepseek.com` | API base URL (point at a local or compatible server if needed). |
| `CM_DEEPSEEK_MODEL` | deepseek | `deepseek-flash` | DeepSeek model name. |

### Automatic provider selection

When `CM_PROVIDER` is unset (or `auto`):

- If `DEEPSEEK_API_KEY` is set → **DeepSeek**
- Otherwise → **Bedrock**

This means a machine with only AWS SSO credentials picks Bedrock, and a machine with a
DeepSeek key picks DeepSeek, with no per-machine flags.

Selecting `deepseek` (explicitly) without a key is an error. AWS authentication
failures tell you to run:

```bash
aws sso login --profile bedrock
```

### Example: DeepSeek

`~/.config/cm/.env`:

```bash
CM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-your-key-here
# Optional:
# DEEPSEEK_BASE_URL=https://api.deepseek.com
# CM_DEEPSEEK_MODEL=deepseek-flash
```

Or, without a config file:

```bash
export DEEPSEEK_API_KEY=sk-your-key-here
cm
```

### Example: Claude on Bedrock

`~/.config/cm/.env`:

```bash
CM_PROVIDER=bedrock
CM_AWS_PROFILE=bedrock
CM_AWS_REGION=us-west-2
# Optional:
# CM_BEDROCK_MODEL=us.anthropic.claude-opus-4-6-v1
```

Then authenticate and run:

```bash
aws sso login --profile bedrock
cm
```


## Development

```bash
make sync       # create the environment and install dev tools
make fmt        # format with ruff
make lint       # lint and auto-fix with ruff
make type       # strict type check with ty
make test       # run the test suite
make check      # format check, lint, types, and tests
make install    # install cm as an editable tool
make upgrade    # upgrade dependencies
```

The same commands work directly with `uv`, for example `uv run pytest` or
`uv run ty check`.
