from __future__ import annotations

import importlib.metadata
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, NoReturn, cast

import click
from rich.console import Console
from rich.markup import escape
from rich.status import Status

from . import git, prompt
from .clipboard import copy_to_clipboard
from .completions import (
    APP_NAME,
    MIN_BASH_VERSION,
    install_bash_completion,
    installed_bash_version,
)
from .config import (
    PROVIDER_AUTO,
    PROVIDERS,
    ConfigError,
    Settings,
    config_path,
    load_config,
)
from .providers import (
    BedrockClaudeProvider,
    DeepSeekProvider,
    Provider,
    ProviderError,
)

PROVIDER_CHOICES = (PROVIDER_AUTO, *PROVIDERS)
COLOR_CHOICES = ("auto", "always", "never")


class AppCommand(click.Command):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        context_settings = dict(kwargs.pop("context_settings", {}) or {})
        context_settings.setdefault("help_option_names", ["-h", "--help"])
        super().__init__(*args, context_settings=context_settings, **kwargs)


class AppGroup(click.Group):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        context_settings = dict(kwargs.pop("context_settings", {}) or {})
        context_settings.setdefault("help_option_names", ["-h", "--help"])
        super().__init__(*args, context_settings=context_settings, **kwargs)


@dataclass(frozen=True)
class CliOptions:
    staged: bool
    provider: str | None
    model: str | None


@dataclass
class CliContext:
    options: CliOptions
    console: Console
    error_console: Console
    config: dict[str, str] | None = None


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


def _consoles(color: str) -> tuple[Console, Console]:
    if color == "always":
        return (
            Console(force_terminal=True, no_color=False),
            Console(stderr=True, force_terminal=True, no_color=False),
        )
    if color == "never":
        return (
            Console(force_terminal=False, no_color=True),
            Console(stderr=True, force_terminal=False, no_color=True),
        )

    force_color = os.environ.get("FORCE_COLOR")
    no_color = False if force_color is not None and force_color != "0" else None
    return (
        Console(no_color=no_color),
        Console(stderr=True, no_color=no_color),
    )


def _ctx_color(color: str) -> bool | None:
    if color == "always":
        return True
    if color == "never":
        return False
    return None


def _fail(console: Console, exc: Exception) -> NoReturn:
    console.print(f"[bold red]error:[/] {escape(str(exc))}")
    raise click.exceptions.Exit(1)


def _load_config(obj: CliContext) -> dict[str, str]:
    if obj.config is not None:
        return obj.config

    try:
        loaded = load_config()
    except ConfigError as exc:
        _fail(obj.error_console, exc)

    for key in loaded.unknown_keys:
        obj.error_console.print(
            f"[yellow]warning:[/] ignoring unknown config key "
            f"{escape(key)!r} in {escape(str(loaded.path))}"
        )

    obj.config = dict(loaded.values)
    return obj.config


def _settings(obj: CliContext) -> Settings:
    return Settings.from_sources(
        _load_config(obj),
        provider=obj.options.provider,
        model=obj.options.model,
    )


def _generate_message(
    settings: Settings,
    *,
    staged: bool,
    error_console: Console,
) -> str:
    selected_provider = build_provider(settings)

    diff = git.get_diff(staged=staged)
    stat = git.get_stat(staged=staged)
    user_prompt = prompt.build_prompt(diff, stat, git.get_recent_commits())

    with Status("Generating commit message...", console=error_console):
        return selected_provider.generate(user_prompt)


def _run_commit_app(message: str, commit: Callable[[str], object]) -> bool:
    from .tui import CommitApp

    return bool(CommitApp(message, commit=commit).run())


def _print_config(
    ctx: click.Context, _param: click.Parameter, value: bool
) -> None:
    """Print the config file path and exit, without loading any config."""
    if not value or ctx.resilient_parsing:
        return
    click.echo(config_path())
    ctx.exit()


def _write_completions(
    ctx: click.Context, _param: click.Parameter, value: bool
) -> None:
    """Write the static bash completion script and exit."""
    if not value or ctx.resilient_parsing:
        return

    group = cast(click.Group, ctx.command)
    path = install_bash_completion(
        group,
        ctx.info_name or APP_NAME,
        importlib.metadata.version("cm"),
    )
    click.echo(path)
    click.echo(f"To use it in this shell:\n  source {path}", err=True)

    version = installed_bash_version()
    required = ".".join(str(part) for part in MIN_BASH_VERSION)
    if version is None:
        click.echo(
            "Warning: could not determine the bash version on PATH; the "
            f"completion script needs bash {required} or newer.",
            err=True,
        )
        if sys.platform == "darwin":
            click.echo(
                "On macOS /bin/bash is 3.2; install a newer bash (for example "
                "with Homebrew). Zsh completions are not generated.",
                err=True,
            )
    elif version < MIN_BASH_VERSION:
        click.echo(
            f"Warning: bash {version[0]}.{version[1]} on PATH is older than "
            f"{required}; the completion script needs bash {required} "
            "or newer.",
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
    cls=AppGroup,
    invoke_without_command=True,
    no_args_is_help=False,
    epilog=(
        "\b\nExamples:\n  cm generate\n  cm --staged generate\n  cm commit"
    ),
)
@click.option(
    "--color",
    type=click.Choice(COLOR_CHOICES, case_sensitive=False),
    default="auto",
    show_default=True,
    help="Control colored output (auto, always, never).",
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
    color: str,
    staged: bool,
    provider: str | None,
    model: str | None,
) -> None:
    """AI-powered git commit message generator.

    Options are set on this base command and must come before a subcommand,
    for example `cm --staged generate` or `cm --staged commit`.
    """
    console, error_console = _consoles(color)
    ctx.color = _ctx_color(color)

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help(), color=ctx.color)
        ctx.exit(0)

    ctx.obj = CliContext(
        options=CliOptions(staged=staged, provider=provider, model=model),
        console=console,
        error_console=error_console,
    )


@main.command(cls=AppCommand)
@click.pass_context
def generate(ctx: click.Context) -> None:
    """Generate a commit message and copy it to the clipboard."""
    obj = cast(CliContext, ctx.obj)

    try:
        settings = _settings(obj)
        message = _generate_message(
            settings,
            staged=obj.options.staged,
            error_console=obj.error_console,
        )
    except (ConfigError, ProviderError, git.GitError) as exc:
        _fail(obj.error_console, exc)

    # The message is model output, so never interpret square brackets in it as
    # Rich markup.
    obj.console.print(message, markup=False, highlight=False)
    if not copy_to_clipboard(message + "\n"):
        obj.error_console.print(
            "[yellow]warning:[/] could not copy to the clipboard; the message "
            "is printed above. On Linux install wl-clipboard, xclip, or xsel."
        )


@main.command(cls=AppCommand)
@click.pass_context
def commit(ctx: click.Context) -> None:
    """Generate a commit message in a TUI and commit the changes."""
    obj = cast(CliContext, ctx.obj)

    try:
        have_staged = git.has_staged_changes()
        if obj.options.staged and not have_staged:
            raise git.GitError(
                "no staged changes. Stage changes first or run `cm commit` "
                "without --staged."
            )

        settings = _settings(obj)
        if have_staged:
            commit_func = git.commit
            staged = True
        else:
            commit_func = git.commit_all
            staged = False

        message = _generate_message(
            settings,
            staged=staged,
            error_console=obj.error_console,
        )
    except (ConfigError, ProviderError, git.GitError) as exc:
        _fail(obj.error_console, exc)

    if _run_commit_app(message, commit_func):
        obj.error_console.print("[green]committed[/]")
    else:
        obj.error_console.print("[yellow]commit cancelled[/]")
