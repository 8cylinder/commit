from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

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


@dataclass(frozen=True)
class GenerateOptions:
    staged: bool
    provider: str | None
    model: str | None


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


def _load_settings(options: GenerateOptions, console: Console) -> Settings:
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
        return Settings.from_env(
            provider=options.provider,
            model=options.model,
        )
    except ConfigError as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        sys.exit(1)


def _generate_message(
    settings: Settings,
    *,
    staged: bool,
    console: Console,
) -> str:
    selected_provider = build_provider(settings)

    diff = git.get_diff(staged=staged)
    stat = git.get_stat(staged=staged)
    user_prompt = prompt.build_prompt(diff, stat, git.get_recent_commits())

    try:
        with Status("Generating commit message...", console=console):
            return selected_provider.generate(user_prompt)
    except ProviderError as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        sys.exit(1)


def _run_commit_app(message: str, commit: Callable[[str], object]) -> bool:
    from .tui import CommitApp

    return bool(CommitApp(message, commit=commit).run())


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


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    no_args_is_help=False,
)
@click.option(
    "-s",
    "--staged",
    is_flag=True,
    help="use staged changes only (no auto-staging for commit)",
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
@click.pass_context
def main(
    ctx: click.Context,
    staged: bool,
    provider: str | None,
    model: str | None,
) -> None:
    """AI-powered git commit message generator.

    Options are set on this base command and must come before a subcommand,
    for example `cm --staged generate` or `cm --staged commit`.
    """
    ctx.obj = GenerateOptions(staged=staged, provider=provider, model=model)


@main.command()
@click.pass_context
def generate(ctx: click.Context) -> None:
    """Generate a commit message, print it, and copy it to the clipboard."""
    options = cast(GenerateOptions, ctx.obj)
    console = Console(stderr=True)

    settings = _load_settings(options, console)
    message = _generate_message(
        settings,
        staged=options.staged,
        console=console,
    )

    # The message is model output, so never interpret square brackets in it as
    # Rich markup.
    console.print(message, markup=False, highlight=False)
    if not copy_to_clipboard(message + "\n"):
        console.print(
            "[yellow]Note:[/] could not copy to the clipboard; the message is "
            "printed above. On Linux install wl-clipboard, xclip, or xsel."
        )


@main.command()
@click.pass_context
def commit(ctx: click.Context) -> None:
    """Generate a commit message in a TUI and commit the changes."""
    options = cast(GenerateOptions, ctx.obj)
    console = Console(stderr=True)

    try:
        have_staged = git.has_staged_changes()
    except git.GitError as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        sys.exit(1)

    if options.staged and not have_staged:
        console.print(
            "[bold red]Error:[/] no staged changes. Stage changes first or "
            "run `cm commit` without --staged."
        )
        sys.exit(1)

    settings = _load_settings(options, console)

    if have_staged:
        commit_func = git.commit
        staged = True
    else:
        commit_func = git.commit_all
        staged = False

    message = _generate_message(settings, staged=staged, console=console)
    if _run_commit_app(message, commit_func):
        console.print("[green]Committed.[/]")
    else:
        console.print("[yellow]Commit cancelled.[/]")
