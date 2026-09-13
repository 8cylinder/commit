from __future__ import annotations

from pathlib import Path

import pytest

from cm.config import (
    DEFAULT_BEDROCK_MODEL,
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_DEEPSEEK_MODEL,
    ConfigError,
    Settings,
    ensure_config_dir,
    load_env_file,
)


def test_auto_without_key_selects_bedrock() -> None:
    settings = Settings.from_env({})
    assert settings.provider == "bedrock"
    assert settings.model == DEFAULT_BEDROCK_MODEL


def test_auto_with_key_selects_deepseek() -> None:
    settings = Settings.from_env({"DEEPSEEK_API_KEY": "secret"})
    assert settings.provider == "deepseek"
    assert settings.model == DEFAULT_DEEPSEEK_MODEL
    assert settings.deepseek_base_url == DEFAULT_DEEPSEEK_BASE_URL
    assert settings.deepseek_api_key == "secret"


def test_cli_provider_overrides_auto() -> None:
    settings = Settings.from_env({"DEEPSEEK_API_KEY": "secret"}, provider="bedrock")
    assert settings.provider == "bedrock"
    assert settings.model == DEFAULT_BEDROCK_MODEL


def test_env_provider_overrides_auto() -> None:
    settings = Settings.from_env(
        {"DEEPSEEK_API_KEY": "secret", "CM_PROVIDER": "bedrock"}
    )
    assert settings.provider == "bedrock"


def test_unknown_provider_raises() -> None:
    with pytest.raises(ConfigError, match="Unknown CM_PROVIDER"):
        Settings.from_env({"CM_PROVIDER": "gemini"})


def test_deepseek_without_key_raises() -> None:
    with pytest.raises(ConfigError, match="DEEPSEEK_API_KEY is not set"):
        Settings.from_env({}, provider="deepseek")


def test_provider_specific_model_override() -> None:
    settings = Settings.from_env(
        {"DEEPSEEK_API_KEY": "secret", "CM_DEEPSEEK_MODEL": "deepseek-v4-pro"}
    )
    assert settings.model == "deepseek-v4-pro"


def test_generic_model_env_beats_provider_specific() -> None:
    settings = Settings.from_env(
        {
            "DEEPSEEK_API_KEY": "secret",
            "CM_MODEL": "generic",
            "CM_DEEPSEEK_MODEL": "specific",
        }
    )
    assert settings.model == "generic"


def test_cli_model_arg_beats_everything() -> None:
    settings = Settings.from_env(
        {"DEEPSEEK_API_KEY": "secret", "CM_MODEL": "generic"},
        model="from-flag",
    )
    assert settings.model == "from-flag"


def test_aws_and_base_url_overrides() -> None:
    settings = Settings.from_env(
        {
            "CM_AWS_PROFILE": "work",
            "CM_AWS_REGION": "eu-west-1",
            "DEEPSEEK_API_KEY": "secret",
            "DEEPSEEK_BASE_URL": "http://localhost:8000/",
        }
    )
    assert settings.aws_profile == "work"
    assert settings.aws_region == "eu-west-1"
    assert settings.deepseek_base_url == "http://localhost:8000/"


def test_ensure_config_dir_creates_dir_and_sample(tmp_path: Path) -> None:
    env_file = tmp_path / "cm" / ".env"

    sample = ensure_config_dir(env_file)

    assert sample == env_file.parent / ".env.sample"
    assert env_file.parent.is_dir()
    assert sample is not None
    assert "DEEPSEEK_API_KEY" in sample.read_text()


def test_ensure_config_dir_noop_when_dir_exists(tmp_path: Path) -> None:
    env_file = tmp_path / "cm" / ".env"
    env_file.parent.mkdir(parents=True)
    sample = env_file.parent / ".env.sample"
    sample.write_text("leftover")

    assert ensure_config_dir(env_file) is None
    assert sample.read_text() == "leftover"


def test_ensure_config_dir_does_not_recreate_deleted_sample(tmp_path: Path) -> None:
    env_file = tmp_path / "cm" / ".env"
    ensure_config_dir(env_file)
    sample = env_file.parent / ".env.sample"
    sample.unlink()

    assert ensure_config_dir(env_file) is None
    assert not sample.exists()


def test_load_env_file_reads_file_and_env_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=from-file\n")

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    load_env_file(env_file)
    assert Settings.from_env().provider == "deepseek"

    monkeypatch.setenv("DEEPSEEK_API_KEY", "from-env")
    load_env_file(env_file)
    assert Settings.from_env().deepseek_api_key == "from-env"


def test_load_env_file_missing_is_noop(tmp_path: Path) -> None:
    load_env_file(tmp_path / "does-not-exist")
