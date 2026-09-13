from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.status import Status

from . import git, prompt
from .clipboard import copy_to_clipboard
from .config import (
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="cm", description="AI-powered git commit message generator"
    )
    parser.add_argument(
        "-s",
        "--staged",
        action="store_true",
        help="generate commit message for staged changes only",
    )
    parser.add_argument(
        "--provider",
        choices=PROVIDER_CHOICES,
        default=None,
        help="AI provider to use (default: auto-detect)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="override the provider's model id",
    )
    args = parser.parse_args(argv)

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
        settings = Settings.from_env(provider=args.provider, model=args.model)
    except ConfigError as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        sys.exit(1)

    provider = build_provider(settings)

    diff = git.get_diff(staged=args.staged)
    stat = git.get_stat(staged=args.staged)
    user_prompt = prompt.build_prompt(diff, stat, git.get_recent_commits())

    try:
        with Status("Generating commit message...", console=console):
            message = provider.generate(user_prompt)
    except ProviderError as exc:
        console.print(f"[bold red]Error:[/] {exc}")
        sys.exit(1)

    console.print(message)
    if not copy_to_clipboard(message + "\n"):
        console.print(
            "[yellow]Note:[/] could not copy to the clipboard; the message is "
            "printed above. On Linux install wl-clipboard, xclip, or xsel."
        )
