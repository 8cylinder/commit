from __future__ import annotations

import sys

import click
from rich.console import Console
from rich.status import Status

from . import git, prompt
from .clipboard import copy_to_clipboard
from .completions import (
    MIN_BASH_VERSION,
    install_completion,
    installed_bash_version,
)
from .config import (
    DEFAULT_ENV_FILE,
    PROVIDER_AUTO,
    PROVIDERS,
    ConfigError,
    Settings,
    ensure_config_dir,
    load_env_file,
)
from .providers import (
    BedrockClaudeProvider,
    DeepSeekProvider,
    Provider,
    ProviderError,
)

PROVIDER_CHOICES = (PROVIDER_AUTO, *PROVIDERS)


def build_provider(settings: Settings) -> Provider:
    if settings.provider == "deepseek":
        return DeepSeekProvider(
            model=settings.model,
            api_key=settings.deepseek_api_key or "",
            base_url=settings.deepseek_base_url,
        )
    return BedrockClaudeProvider(
        model=settings.model,
        profile=settings.aws_profile,
        region=settings.aws_region,
    )


def _print_config(ctx: click.Context, _param: click.Parameter, value: bool) -> None:
    """Print the config file path and exit, without loading any config."""
    if not value or ctx.resilient_parsing:
        return
    click.echo(DEFAULT_ENV_FILE)
    ctx.exit()


def _write_completions(
    ctx: click.Context, _param: click.Parameter, value: bool
) -> None:
    """Write the static bash completion script and exit."""
    if not value or ctx.resilient_parsing:
        return

    path = install_completion()
    click.echo(f"Wrote bash completion for cm to {path}")
    click.echo(f"Run this to enable it in the current terminal:\n  source {path}")

    version = installed_bash_version()
    if version is not None and version < MIN_BASH_VERSION:
        required = ".".join(str(part) for part in MIN_BASH_VERSION)
        click.echo(
            f"Warning: bash {version[0]}.{version[1]} on PATH is older than "
            f"{required}; the completion script needs bash {required} or newer.",
            err=True,
        )
        if sys.platform == "darwin":
            click.echo(
                "On macOS /bin/bash is 3.2; install a newer bash (for example "
                "with Homebrew). Zsh completions are not generated.",
                err=True,
            )
    ctx.exit()


@click.command(
    context_settings={"help_option_names": ["-h", "--help"]},
    help="AI-powered git commit message generator.",
)
@click.option(
    "-s",
    "--staged",
    is_flag=True,
    help="generate commit message for staged changes only",
)
@click.option(
    "--provider",
    type=click.Choice(PROVIDER_CHOICES, case_sensitive=False),
    default=None,
    help="AI provider to use (default: auto-detect)",
)
@click.option(
    "--model",
    default=None,
    help="override the provider's model id",
)
@click.option(
    "--config",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_print_config,
    help="print the config file path and exit",
)
@click.option(
    "--completions",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_write_completions,
    help="write static bash completions and exit",
)
@click.version_option(package_name="cm", prog_name="cm")
def main(staged: bool, provider: str | None, model: str | None) -> None:
    console = Console(stderr=True)

    sample = ensure_config_dir()
    if sample is not None:
        console.print(
            f"[dim]Created config directory [bold]{sample.parent}[/] and wrote a "
            f"sample config to [bold]{sample}[/].[/]\n"
            f"[dim]Copy it to [bold]{sample.with_name('.env')}[/] and fill in "
            "DEEPSEEK_API_KEY to use DeepSeek; AWS SSO credentials work with no "
            "config at all.[/]"
        )

    load_env_file()
    try:
        settings = Settings.from_env(provider=provider, model=model)
    except ConfigError as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        sys.exit(1)

    selected_provider = build_provider(settings)

    diff = git.get_diff(staged=staged)
    stat = git.get_stat(staged=staged)
    user_prompt = prompt.build_prompt(diff, stat, git.get_recent_commits())

    try:
        with Status("Generating commit message...", console=console):
            message = selected_provider.generate(user_prompt)
    except ProviderError as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        sys.exit(1)

    # The message is model output, so never interpret square brackets in it as
    # Rich markup.
    console.print(message, markup=False, highlight=False)
    if not copy_to_clipboard(message + "\n"):
        console.print(
            "[yellow]Note:[/] could not copy to the clipboard; the message is "
            "printed above. On Linux install wl-clipboard, xclip, or xsel."
        )
