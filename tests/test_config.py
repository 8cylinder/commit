from __future__ import annotations

from pathlib import Path

import pytest

from cm.config import (
    DEFAULT_AWS_PROFILE,
    DEFAULT_AWS_REGION,
    DEFAULT_BEDROCK_MODEL,
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_DEEPSEEK_MODEL,
    ConfigError,
    Settings,
    config_path,
    load_config,
)


def test_config_path_uses_xdg_config_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))

    assert config_path() == tmp_path / "cm" / "config.toml"


def test_config_path_falls_back_to_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    assert config_path() == tmp_path / ".config" / "cm" / "config.toml"


def test_load_config_missing_returns_empty(tmp_path: Path) -> None:
    loaded = load_config(tmp_path / "config.toml")

    assert loaded.values == {}
    assert loaded.unknown_keys == ()
    assert loaded.path == tmp_path / "config.toml"


def test_load_config_reads_values(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        'provider = "deepseek"\nmodel = "custom"\naws_region = "eu-west-1"\n',
        encoding="utf-8",
    )

    loaded = load_config(path)

    assert loaded.values == {
        "provider": "deepseek",
        "model": "custom",
        "aws_region": "eu-west-1",
    }
    assert loaded.unknown_keys == ()


def test_load_config_invalid_toml_names_path(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("not = [\n", encoding="utf-8")

    with pytest.raises(ConfigError, match=str(path)):
        load_config(path)


def test_load_config_non_string_value_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("provider = 1\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="must be a string"):
        load_config(path)


def test_load_config_reports_unknown_keys(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('provider = "bedrock"\ntypo = "x"\n', encoding="utf-8")

    loaded = load_config(path)

    assert loaded.values == {"provider": "bedrock"}
    assert loaded.unknown_keys == ("typo",)


def test_auto_without_key_selects_bedrock() -> None:
    settings = Settings.from_sources({}, {})

    assert settings.provider == "bedrock"
    assert settings.model == DEFAULT_BEDROCK_MODEL
    assert settings.aws_profile == DEFAULT_AWS_PROFILE
    assert settings.aws_region == DEFAULT_AWS_REGION


def test_auto_with_env_key_selects_deepseek() -> None:
    settings = Settings.from_sources({}, {"DEEPSEEK_API_KEY": "secret"})

    assert settings.provider == "deepseek"
    assert settings.model == DEFAULT_DEEPSEEK_MODEL
    assert settings.deepseek_base_url == DEFAULT_DEEPSEEK_BASE_URL
    assert settings.deepseek_api_key == "secret"


def test_auto_with_config_key_selects_deepseek() -> None:
    settings = Settings.from_sources({"deepseek_api_key": "secret"}, {})

    assert settings.provider == "deepseek"
    assert settings.deepseek_api_key == "secret"


def test_cli_provider_overrides_everything() -> None:
    settings = Settings.from_sources(
        {"provider": "bedrock"},
        {"CM_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "secret"},
        provider="bedrock",
    )

    assert settings.provider == "bedrock"
    assert settings.model == DEFAULT_BEDROCK_MODEL


def test_env_provider_overrides_config() -> None:
    settings = Settings.from_sources(
        {"provider": "bedrock"},
        {"CM_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "secret"},
    )

    assert settings.provider == "deepseek"


def test_config_provider_is_used() -> None:
    settings = Settings.from_sources(
        {"provider": "deepseek"}, {"DEEPSEEK_API_KEY": "secret"}
    )

    assert settings.provider == "deepseek"


def test_unknown_provider_raises() -> None:
    with pytest.raises(ConfigError, match="Unknown provider"):
        Settings.from_sources({"provider": "gemini"}, {})


def test_deepseek_without_key_raises() -> None:
    with pytest.raises(ConfigError, match="DEEPSEEK_API_KEY is not set"):
        Settings.from_sources({"provider": "deepseek"}, {})


def test_model_precedence() -> None:
    config = {"model": "config-model"}
    env = {
        "DEEPSEEK_API_KEY": "secret",
        "CM_MODEL": "env-model",
        "CM_DEEPSEEK_MODEL": "specific-model",
    }

    assert Settings.from_sources(config, env).model == "env-model"
    assert (
        Settings.from_sources(config, env, model="flag-model").model
        == "flag-model"
    )
    assert (
        Settings.from_sources(
            config,
            {"DEEPSEEK_API_KEY": "secret", "CM_DEEPSEEK_MODEL": "specific"},
        ).model
        == "specific"
    )
    assert (
        Settings.from_sources(config, {"DEEPSEEK_API_KEY": "secret"}).model
        == "config-model"
    )
    assert (
        Settings.from_sources({}, {"DEEPSEEK_API_KEY": "secret"}).model
        == DEFAULT_DEEPSEEK_MODEL
    )


def test_other_settings_precedence() -> None:
    config = {
        "aws_profile": "config-profile",
        "aws_region": "config-region",
        "deepseek_base_url": "https://config.example",
    }
    env = {
        "CM_AWS_PROFILE": "env-profile",
        "CM_AWS_REGION": "env-region",
        "DEEPSEEK_BASE_URL": "https://env.example",
        "DEEPSEEK_API_KEY": "secret",
    }

    settings = Settings.from_sources(config, env)

    assert settings.aws_profile == "env-profile"
    assert settings.aws_region == "env-region"
    assert settings.deepseek_base_url == "https://env.example"


def test_config_settings_used_without_env() -> None:
    settings = Settings.from_sources(
        {
            "aws_profile": "config-profile",
            "aws_region": "config-region",
            "deepseek_base_url": "https://config.example",
            "deepseek_api_key": "secret",
        },
        {},
    )

    assert settings.aws_profile == "config-profile"
    assert settings.aws_region == "config-region"
    assert settings.deepseek_base_url == "https://config.example"
