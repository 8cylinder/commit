from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv

PROVIDER_AUTO = "auto"
PROVIDER_BEDROCK = "bedrock"
PROVIDER_DEEPSEEK = "deepseek"
PROVIDERS = (PROVIDER_BEDROCK, PROVIDER_DEEPSEEK)

DEFAULT_AWS_PROFILE = "bedrock"
DEFAULT_AWS_REGION = "us-west-2"
DEFAULT_BEDROCK_MODEL = "us.anthropic.claude-opus-4-6-v1"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-flash"

DEFAULT_ENV_FILE = Path.home() / ".config" / "cm" / ".env"


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Settings:
    provider: str
    model: str
    aws_profile: str
    aws_region: str
    deepseek_api_key: str | None
    deepseek_base_url: str

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        provider: str | None = None,
        model: str | None = None,
    ) -> "Settings":
        env = os.environ if environ is None else environ

        requested = (provider or env.get("CM_PROVIDER") or PROVIDER_AUTO).strip().lower()
        if requested not in (*PROVIDERS, PROVIDER_AUTO):
            raise ConfigError(
                f"Unknown CM_PROVIDER {requested!r}; expected one of "
                f"{', '.join((*PROVIDERS, PROVIDER_AUTO))}."
            )

        deepseek_api_key = env.get("DEEPSEEK_API_KEY") or None

        if requested == PROVIDER_AUTO:
            provider = PROVIDER_DEEPSEEK if deepseek_api_key else PROVIDER_BEDROCK
        else:
            provider = requested

        if provider == PROVIDER_DEEPSEEK and not deepseek_api_key:
            raise ConfigError(
                "DEEPSEEK_API_KEY is not set. Export it or add it to "
                f"{DEFAULT_ENV_FILE}."
            )

        if provider == PROVIDER_DEEPSEEK:
            model = (
                model
                or env.get("CM_MODEL")
                or env.get("CM_DEEPSEEK_MODEL")
                or DEFAULT_DEEPSEEK_MODEL
            )
        else:
            model = (
                model
                or env.get("CM_MODEL")
                or env.get("CM_BEDROCK_MODEL")
                or DEFAULT_BEDROCK_MODEL
            )

        return cls(
            provider=provider,
            model=model,
            aws_profile=env.get("CM_AWS_PROFILE") or DEFAULT_AWS_PROFILE,
            aws_region=env.get("CM_AWS_REGION") or DEFAULT_AWS_REGION,
            deepseek_api_key=deepseek_api_key,
            deepseek_base_url=env.get("DEEPSEEK_BASE_URL") or DEFAULT_DEEPSEEK_BASE_URL,
        )


SAMPLE_ENV = """\
# cm configuration. Copy this file to .env and edit as needed.
#
# Provider selection: auto | bedrock | deepseek. When unset, cm uses
# DeepSeek if DEEPSEEK_API_KEY is set, otherwise AWS Bedrock.
# CM_PROVIDER=auto

# DeepSeek (e.g. personal machines)
# DEEPSEEK_API_KEY=
# DEEPSEEK_BASE_URL=https://api.deepseek.com
# CM_DEEPSEEK_MODEL=deepseek-flash

# AWS Bedrock (e.g. work machines; uses the `bedrock` SSO profile)
# CM_AWS_PROFILE=bedrock
# CM_AWS_REGION=us-west-2
# CM_BEDROCK_MODEL=us.anthropic.claude-opus-4-6-v1

# Universal model override (wins over the provider-specific variables above)
# CM_MODEL=
"""


def ensure_config_dir(path: Path = DEFAULT_ENV_FILE) -> Path | None:
    """Create the config directory and a sample .env if the directory is missing.

    Does nothing when the directory already exists, so a deliberately removed
    sample is not recreated. Returns the sample path when the directory was
    created, otherwise None.
    """
    path = Path(path)
    directory = path.parent
    if directory.exists():
        return None
    directory.mkdir(parents=True, exist_ok=True)
    sample = directory / ".env.sample"
    sample.write_text(SAMPLE_ENV, encoding="utf-8")
    return sample


def load_env_file(path: Path = DEFAULT_ENV_FILE) -> None:
    path = Path(path)
    if path.is_file():
        load_dotenv(path, override=False)

