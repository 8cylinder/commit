from __future__ import annotations

from pathlib import Path

import pytest

from cm import cli
from cm.config import Settings
from cm.providers import AuthError, BedrockClaudeProvider, DeepSeekProvider


class FakeProvider:
    def __init__(self, error: Exception | None = None) -> None:
        self.prompts: list[str] = []
        self._error = error

    def generate(self, prompt: str) -> str:
        if self._error is not None:
            raise self._error
        self.prompts.append(prompt)
        return "Generated message"


@pytest.fixture
def no_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "ensure_config_dir", lambda: None)
    monkeypatch.setattr(cli, "load_env_file", lambda: None)
    monkeypatch.setattr(cli.git, "get_diff", lambda staged=False: "DIFF")
    monkeypatch.setattr(cli.git, "get_stat", lambda staged=False: "STAT")
    monkeypatch.setattr(cli.git, "get_recent_commits", lambda: "RECENT")


def _capture(
    monkeypatch: pytest.MonkeyPatch, provider: FakeProvider
) -> dict[str, object]:
    captured: dict[str, object] = {"copied": None, "settings": None}

    def build_provider(settings: Settings) -> FakeProvider:
        captured["settings"] = settings
        return provider

    def copy_to_clipboard(text: str) -> bool:
        captured["copied"] = text
        return True

    monkeypatch.setattr(cli, "build_provider", build_provider)
    monkeypatch.setattr(cli, "copy_to_clipboard", copy_to_clipboard)
    return captured


def test_main_prints_and_copies(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    no_side_effects: None,
) -> None:
    provider = FakeProvider()
    captured = _capture(monkeypatch, provider)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")

    cli.main(["--provider", "deepseek"])

    assert len(provider.prompts) == 1
    assert "DIFF" in provider.prompts[0]
    assert "STAT" in provider.prompts[0]
    assert "RECENT" in provider.prompts[0]
    assert captured["copied"] == "Generated message\n"
    assert "Generated message" in capsys.readouterr().err


def test_main_passes_provider_and_model(
    monkeypatch: pytest.MonkeyPatch,
    no_side_effects: None,
) -> None:
    captured = _capture(monkeypatch, FakeProvider())
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")

    cli.main(["--provider", "deepseek", "--model", "custom-model"])

    settings = captured["settings"]
    assert isinstance(settings, Settings)
    assert settings.provider == "deepseek"
    assert settings.model == "custom-model"


def test_main_reports_first_run_config(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sample = Path("/tmp/cm-test/.env.sample")
    monkeypatch.setattr(cli, "ensure_config_dir", lambda: sample)
    monkeypatch.setattr(cli, "load_env_file", lambda: None)
    monkeypatch.setattr(cli, "build_provider", lambda settings: FakeProvider())
    monkeypatch.setattr(cli, "copy_to_clipboard", lambda text: True)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")

    cli.main(["--provider", "deepseek"])

    assert "Created config directory" in capsys.readouterr().err


def test_main_config_error_exits(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    no_side_effects: None,
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--provider", "deepseek"])

    assert excinfo.value.code == 1
    assert "DEEPSEEK_API_KEY is not set" in capsys.readouterr().err


def test_main_provider_error_exits(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    no_side_effects: None,
) -> None:
    _capture(monkeypatch, FakeProvider(error=AuthError("nope")))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")

    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--provider", "deepseek"])

    assert excinfo.value.code == 1
    assert "nope" in capsys.readouterr().err


def test_build_provider_selects_deepseek() -> None:
    settings = Settings.from_env({"DEEPSEEK_API_KEY": "secret"})
    assert isinstance(cli.build_provider(settings), DeepSeekProvider)


def test_build_provider_selects_bedrock() -> None:
    settings = Settings.from_env({})
    assert isinstance(cli.build_provider(settings), BedrockClaudeProvider)
