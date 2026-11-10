from __future__ import annotations

import importlib.metadata
from pathlib import Path

import pytest
from click.testing import CliRunner

from cm import cli
from cm.config import Settings
from cm.providers import AuthError, BedrockClaudeProvider, DeepSeekProvider


class FakeProvider:
    def __init__(
        self, error: Exception | None = None, message: str = "Generated message"
    ) -> None:
        self.prompts: list[str] = []
        self._error = error
        self._message = message

    def generate(self, prompt: str) -> str:
        if self._error is not None:
            raise self._error
        self.prompts.append(prompt)
        return self._message


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


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
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    no_side_effects: None,
) -> None:
    provider = FakeProvider()
    captured = _capture(monkeypatch, provider)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")

    result = runner.invoke(cli.main, ["--provider", "deepseek", "generate"])

    assert result.exit_code == 0
    assert len(provider.prompts) == 1
    assert "DIFF" in provider.prompts[0]
    assert "STAT" in provider.prompts[0]
    assert "RECENT" in provider.prompts[0]
    assert captured["copied"] == "Generated message\n"
    assert "Generated message" in result.stderr


def test_main_passes_provider_and_model(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    no_side_effects: None,
) -> None:
    captured = _capture(monkeypatch, FakeProvider())
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")

    result = runner.invoke(
        cli.main, ["--provider", "deepseek", "--model", "custom-model", "generate"]
    )

    assert result.exit_code == 0
    settings = captured["settings"]
    assert isinstance(settings, Settings)
    assert settings.provider == "deepseek"
    assert settings.model == "custom-model"


def test_main_reports_first_run_config(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sample = Path("/tmp/cm-test/.env.sample")
    monkeypatch.setattr(cli, "ensure_config_dir", lambda: sample)
    monkeypatch.setattr(cli, "load_env_file", lambda: None)
    monkeypatch.setattr(cli, "build_provider", lambda settings: FakeProvider())
    monkeypatch.setattr(cli, "copy_to_clipboard", lambda text: True)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")

    result = runner.invoke(cli.main, ["--provider", "deepseek", "generate"])

    assert result.exit_code == 0
    assert "Created config directory" in result.stderr


def test_main_config_error_exits(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    no_side_effects: None,
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    result = runner.invoke(cli.main, ["--provider", "deepseek", "generate"])

    assert result.exit_code == 1
    assert "DEEPSEEK_API_KEY is not set" in result.stderr


def test_main_provider_error_exits(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    no_side_effects: None,
) -> None:
    _capture(monkeypatch, FakeProvider(error=AuthError("nope")))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")

    result = runner.invoke(cli.main, ["--provider", "deepseek", "generate"])

    assert result.exit_code == 1
    assert "nope" in result.stderr


def test_main_does_not_treat_message_as_markup(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    no_side_effects: None,
) -> None:
    _capture(monkeypatch, FakeProvider(message="[bold]Generated[/]"))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")

    result = runner.invoke(cli.main, ["--provider", "deepseek", "generate"])

    assert result.exit_code == 0
    assert "[bold]Generated[/]" in result.stderr


def test_bare_cm_errors(runner: CliRunner) -> None:
    result = runner.invoke(cli.main, [])

    assert result.exit_code == 2
    assert "Missing command" in result.stderr


def test_staged_flag_reaches_generate(
    runner: CliRunner,
    monkeypatch: pytest.MonkeyPatch,
    no_side_effects: None,
) -> None:
    captured: dict[str, bool] = {}

    def fake_get_diff(staged: bool = False) -> str:
        captured["staged"] = staged
        return "DIFF"

    monkeypatch.setattr(cli.git, "get_diff", fake_get_diff)
    _capture(monkeypatch, FakeProvider())
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")

    result = runner.invoke(cli.main, ["--staged", "generate"])

    assert result.exit_code == 0
    assert captured["staged"] is True


def test_help_supports_dash_h(runner: CliRunner) -> None:
    result = runner.invoke(cli.main, ["-h"])

    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert "--completions" in result.output
    assert "--config" in result.output
    assert "generate" in result.output


def test_generate_help(runner: CliRunner) -> None:
    result = runner.invoke(cli.main, ["generate", "--help"])

    assert result.exit_code == 0
    assert "Generate a commit message" in result.output


def test_version_comes_from_package_metadata(runner: CliRunner) -> None:
    result = runner.invoke(cli.main, ["--version"])

    assert result.exit_code == 0
    assert importlib.metadata.version("cm") in result.output


def test_config_prints_path_and_exits(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / "config" / ".env"
    monkeypatch.setattr(cli, "DEFAULT_ENV_FILE", env_file)

    result = runner.invoke(cli.main, ["--config"])

    assert result.exit_code == 0
    assert result.stdout.strip() == str(env_file)


def test_completions_writes_script(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "completions" / "cm"
    monkeypatch.setattr(cli, "installed_bash_version", lambda: (5, 2))

    def install() -> Path:
        target.parent.mkdir(parents=True)
        target.write_text("script", encoding="utf-8")
        return target

    monkeypatch.setattr(cli, "install_completion", install)

    result = runner.invoke(cli.main, ["--completions"])

    assert result.exit_code == 0
    assert str(target) in result.stdout
    assert f"source {target}" in result.stdout
    assert target.read_text(encoding="utf-8") == "script"


def test_completions_warns_on_old_bash(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli, "install_completion", lambda: tmp_path / "cm")
    monkeypatch.setattr(cli, "installed_bash_version", lambda: (3, 2))
    monkeypatch.setattr(cli.sys, "platform", "linux")

    result = runner.invoke(cli.main, ["--completions"])

    assert result.exit_code == 0
    assert "older than 4.4" in result.stderr


def _patch_commit(
    monkeypatch: pytest.MonkeyPatch,
    *,
    staged: bool,
    run_result: bool = True,
) -> dict[str, object]:
    captured: dict[str, object] = {}

    def fake_generate(_settings: Settings, *, staged: bool, console: object) -> str:
        captured["staged"] = staged
        return "Generated message"

    def fake_commit(_message: str) -> str:
        return "ok"

    def fake_commit_all(_message: str) -> str:
        return "ok"

    def fake_run(message: str, commit: object) -> bool:
        captured["message"] = message
        captured["commit_kind"] = "staged" if commit is fake_commit else "all"
        return run_result

    settings = Settings.from_env({"DEEPSEEK_API_KEY": "secret"})
    monkeypatch.setattr(cli, "_load_settings", lambda options, console: settings)
    monkeypatch.setattr(cli, "_generate_message", fake_generate)
    monkeypatch.setattr(cli.git, "has_staged_changes", lambda: staged)
    monkeypatch.setattr(cli.git, "commit", fake_commit)
    monkeypatch.setattr(cli.git, "commit_all", fake_commit_all)
    monkeypatch.setattr(cli, "_run_commit_app", fake_run)
    return captured


def test_commit_with_nothing_staged_generates_all_and_commits_all(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = _patch_commit(monkeypatch, staged=False)

    result = runner.invoke(cli.main, ["commit"])

    assert result.exit_code == 0
    assert captured["staged"] is False
    assert captured["message"] == "Generated message"
    assert captured["commit_kind"] == "all"
    assert "Committed" in result.stderr


def test_commit_with_staged_changes_uses_staged_diff(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = _patch_commit(monkeypatch, staged=True)

    result = runner.invoke(cli.main, ["commit"])

    assert result.exit_code == 0
    assert captured["staged"] is True
    assert captured["commit_kind"] == "staged"


def test_commit_staged_requires_staged_changes(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured = _patch_commit(monkeypatch, staged=False)

    result = runner.invoke(cli.main, ["--staged", "commit"])

    assert result.exit_code == 1
    assert "no staged changes" in result.stderr
    assert "message" not in captured


def test_commit_cancel_does_not_report_success(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_commit(monkeypatch, staged=True, run_result=False)

    result = runner.invoke(cli.main, ["commit"])

    assert result.exit_code == 0
    assert "Commit cancelled" in result.stderr


def test_commit_reports_git_error(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail() -> bool:
        raise cli.git.GitError("not a git repository")

    monkeypatch.setattr(cli.git, "has_staged_changes", fail)

    result = runner.invoke(cli.main, ["commit"])

    assert result.exit_code == 1
    assert "not a git repository" in result.stderr


def test_build_provider_selects_deepseek() -> None:
    settings = Settings.from_env({"DEEPSEEK_API_KEY": "secret"})
    assert isinstance(cli.build_provider(settings), DeepSeekProvider)


def test_build_provider_selects_bedrock() -> None:
    settings = Settings.from_env({})
    assert isinstance(cli.build_provider(settings), BedrockClaudeProvider)
