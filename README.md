# cm

`cm` is a small command-line tool that reads your uncommitted git changes, asks an AI
provider to write a commit message that matches your repo's recent style, prints it,
and copies it to your clipboard.

It supports two providers and can switch between them automatically:

- **Claude on AWS Bedrock** — uses your existing AWS SSO profile (good for a work
  machine with a `bedrock` profile).
- **DeepSeek** — uses a DeepSeek API key (good for a personal machine).

The message is generated from the diff, a file summary, and your last 20 commit
messages so the tone and format stay consistent.

## Requirements

- Python 3.13+
- [`uv`](https://docs.astral.sh/uv/)
- One of:
  - AWS credentials with Bedrock access (profile `bedrock`), or
  - a DeepSeek API key

## Install

Build a wheel/sdist:

```bash
uv build
```

Install the `cm` command globally as a tool:

```bash
uv tool install .
```

Install in editable mode so source changes take effect without reinstalling:

```bash
uv tool install --editable .
```

Run from a checkout without installing (uses the local project environment):

```bash
uv run cm
```

## Usage

```bash
cm              # generate from all uncommitted changes (including untracked files)
cm --staged     # generate from staged changes only
cm --provider deepseek
cm --provider bedrock --model us.anthropic.claude-opus-4-6-v1
```

The generated message is printed to stderr and copied to the clipboard.

Clipboard support:

- macOS: `pbcopy`
- Linux (Wayland): `wl-copy`
- Linux (X11): `xclip` or `xsel`

If none of these are installed, `cm` prints the message and tells you to copy it
manually.

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
uv sync                     # create the environment and install dev tools
uv run pytest               # run the test suite
uv run ruff check .         # lint
uv run ruff format .        # format
uv run ty check             # type check (strict)
```
