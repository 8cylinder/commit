from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import platformdirs

APP_NAME = "cm"

PROVIDER_AUTO = "auto"
PROVIDER_BEDROCK = "bedrock"
PROVIDER_DEEPSEEK = "deepseek"
PROVIDERS = (PROVIDER_BEDROCK, PROVIDER_DEEPSEEK)

DEFAULT_AWS_PROFILE = "bedrock"
DEFAULT_AWS_REGION = "us-west-2"
DEFAULT_BEDROCK_MODEL = "us.anthropic.claude-opus-4-6-v1"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-flash"

CONFIG_KEYS = frozenset(
    {
        "provider",
        "model",
        "aws_profile",
        "aws_region",
        "deepseek_api_key",
        "deepseek_base_url",
    }
)


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class ConfigFile:
    path: Path
    values: Mapping[str, str]
    unknown_keys: tuple[str, ...] = ()


def config_path() -> Path:
    """Return the platform-specific path to config.toml."""
    return Path(platformdirs.user_config_dir(APP_NAME)) / "config.toml"


def load_config(path: Path | None = None) -> ConfigFile:
    """Read config.toml and validate its top-level keys.

    A missing file is not an error and yields empty values. Invalid TOML or a
    value with the wrong type raises ConfigError naming the path.
    """
    path = config_path() if path is None else Path(path)
    if not path.is_file():
        return ConfigFile(path=path, values={})

    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: invalid TOML: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"{path}: could not read config: {exc}") from exc

    values: dict[str, str] = {}
    unknown: list[str] = []
    for key, value in data.items():
        if key not in CONFIG_KEYS:
            unknown.append(key)
            continue
        if not isinstance(value, str):
            raise ConfigError(f"{path}: {key!r} must be a string")
        values[key] = value

    return ConfigFile(
        path=path,
        values=values,
        unknown_keys=tuple(sorted(unknown)),
    )


@dataclass(frozen=True)
class Settings:
    provider: str
    model: str
    aws_profile: str
    aws_region: str
    deepseek_api_key: str | None
    deepseek_base_url: str

    @classmethod
    def from_sources(
        cls,
        config: Mapping[str, str] | None = None,
        environ: Mapping[str, str] | None = None,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> Settings:
        """Resolve settings from CLI flags, environment, config, and defaults.

        Precedence is command-line option > environment variable > config.toml
        > built-in default.
        """
        values: Mapping[str, str] = (
            config if config is not None else dict[str, str]()
        )
        env = os.environ if environ is None else environ

        requested: str = (
            (
                provider
                or env.get("CM_PROVIDER")
                or values.get("provider")
                or PROVIDER_AUTO
            )
            .strip()
            .lower()
        )
        if requested not in (*PROVIDERS, PROVIDER_AUTO):
            raise ConfigError(
                f"Unknown provider {requested!r}; expected one of "
                f"{', '.join((*PROVIDERS, PROVIDER_AUTO))}."
            )

        deepseek_api_key = (
            env.get("DEEPSEEK_API_KEY")
            or values.get("deepseek_api_key")
            or None
        )

        selected: str
        if requested == PROVIDER_AUTO:
            selected = (
                PROVIDER_DEEPSEEK if deepseek_api_key else PROVIDER_BEDROCK
            )
        else:
            selected = requested

        if selected == PROVIDER_DEEPSEEK and not deepseek_api_key:
            raise ConfigError(
                "DEEPSEEK_API_KEY is not set. Export it or add it to "
                f"{config_path()}."
            )

        selected_model: str
        if selected == PROVIDER_DEEPSEEK:
            selected_model = (
                model
                or env.get("CM_MODEL")
                or env.get("CM_DEEPSEEK_MODEL")
                or values.get("model")
                or DEFAULT_DEEPSEEK_MODEL
            )
        else:
            selected_model = (
                model
                or env.get("CM_MODEL")
                or env.get("CM_BEDROCK_MODEL")
                or values.get("model")
                or DEFAULT_BEDROCK_MODEL
            )

        return cls(
            provider=selected,
            model=selected_model,
            aws_profile=(
                env.get("CM_AWS_PROFILE")
                or values.get("aws_profile")
                or DEFAULT_AWS_PROFILE
            ),
            aws_region=(
                env.get("CM_AWS_REGION")
                or values.get("aws_region")
                or DEFAULT_AWS_REGION
            ),
            deepseek_api_key=deepseek_api_key,
            deepseek_base_url=(
                env.get("DEEPSEEK_BASE_URL")
                or values.get("deepseek_base_url")
                or DEFAULT_DEEPSEEK_BASE_URL
            ),
        )
