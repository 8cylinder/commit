from __future__ import annotations

import shlex
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

import click
import pytest

from cm import cli, completions


def _complete(
    tmp_path: Path,
    group: click.Group,
    words: list[str],
    *,
    prog_name: str = "demo",
    cword: int | None = None,
    cwd: Path | None = None,
) -> list[str]:
    script = completions.generate_bash_completion(group, prog_name, "9.9.9")
    path = tmp_path / "completion.bash"
    path.write_text(script, encoding="utf-8")

    if cword is None:
        cword = len(words) - 1
    quoted_words = " ".join(shlex.quote(word) for word in words)
    command = f"""
source {shlex.quote(str(path))}
COMP_WORDS=({quoted_words})
COMP_CWORD={cword}
_{prog_name}_complete
if (( ${{#COMPREPLY[@]}} )); then printf '%s\\n' "${{COMPREPLY[@]}}"; fi
"""
    result = subprocess.run(
        ["bash", "-c", command],
        capture_output=True,
        text=True,
        cwd=cwd or tmp_path,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.splitlines()


@pytest.fixture
def demo(tmp_path: Path) -> click.Group:
    @click.group(cls=cli.AppGroup)
    @click.option("--mode", "-m", type=click.Choice(["fast", "slow"]))
    @click.option("--out", type=click.Path(file_okay=False))
    @click.option("--file", type=click.Path(dir_okay=False))
    @click.option("--path", type=click.Path())
    @click.option("--pair", type=(click.Choice(["a", "b"]), click.Path()))
    @click.option("--hidden-opt", hidden=True)
    @click.option("--tag", multiple=True)
    @click.option("--count", count=True)
    def group() -> None:
        """Demo group."""

    @group.command()
    def visible() -> None:
        """Visible command."""

    @group.command(hidden=True)
    def secret() -> None:
        """Hidden command."""

    return group


def test_completion_path_prefers_bash_completion_user_dir(
    tmp_path: Path,
) -> None:
    environ = {
        "BASH_COMPLETION_USER_DIR": f"{tmp_path / 'one'}:{tmp_path / 'two'}",
        "XDG_DATA_HOME": str(tmp_path / "xdg"),
    }

    path = completions.completion_path(environ)

    assert path == (
        tmp_path / "one" / "bash-completion" / "completions" / "cm.bash"
    )


def test_completion_path_skips_empty_user_dir_entries(tmp_path: Path) -> None:
    environ = {
        "BASH_COMPLETION_USER_DIR": f":{tmp_path / 'two'}",
        "XDG_DATA_HOME": str(tmp_path / "xdg"),
    }

    path = completions.completion_path(environ)

    assert path == (
        tmp_path / "two" / "bash-completion" / "completions" / "cm.bash"
    )


def test_completion_path_uses_xdg_data_home(tmp_path: Path) -> None:
    path = completions.completion_path({"XDG_DATA_HOME": str(tmp_path)})

    assert path == tmp_path / "bash-completion" / "completions" / "cm.bash"


def test_completion_path_empty_user_dir_falls_through(tmp_path: Path) -> None:
    path = completions.completion_path(
        {
            "BASH_COMPLETION_USER_DIR": "",
            "XDG_DATA_HOME": str(tmp_path),
        }
    )

    assert path == tmp_path / "bash-completion" / "completions" / "cm.bash"


def test_completion_path_falls_back_to_local_share(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    path = completions.completion_path({})

    assert path == (
        tmp_path
        / ".local"
        / "share"
        / "bash-completion"
        / "completions"
        / "cm.bash"
    )


def test_completion_path_makes_relative_user_dir_absolute(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    path = completions.completion_path({"BASH_COMPLETION_USER_DIR": "relative"})

    assert path == (
        tmp_path / "relative" / "bash-completion" / "completions" / "cm.bash"
    )
    assert path.is_absolute()


def test_install_completion_writes_atomic_file(
    tmp_path: Path, demo: click.Group
) -> None:
    environ = {"XDG_DATA_HOME": str(tmp_path)}
    path = tmp_path / "bash-completion" / "completions" / "cm.bash"
    path.parent.mkdir(parents=True)
    path.write_text("old", encoding="utf-8")

    written = completions.install_bash_completion(
        demo, "demo", "9.9.9", environ
    )

    assert written == path
    assert "bash completion for demo 9.9.9" in path.read_text(encoding="utf-8")
    assert stat.S_IMODE(path.stat().st_mode) == 0o644


def test_generated_script_has_header_and_registration(
    tmp_path: Path, demo: click.Group
) -> None:
    script = completions.generate_bash_completion(demo, "demo", "9.9.9")

    assert "# bash completion for demo 9.9.9" in script
    assert "do not edit by hand" in script
    assert (
        "complete -o nosort -o bashdefault -o default -F _demo_complete demo"
        in script
    )
    assert "_demo_cmd_1" in script


def test_generated_script_passes_bash_syntax_check(
    tmp_path: Path, demo: click.Group
) -> None:
    script = completions.generate_bash_completion(demo, "demo", "9.9.9")
    path = tmp_path / "completion.bash"
    path.write_text(script, encoding="utf-8")

    result = subprocess.run(
        ["bash", "-n", str(path)], capture_output=True, text=True
    )

    assert result.returncode == 0, result.stderr


def test_completes_subcommands_and_hides_secret(
    tmp_path: Path, demo: click.Group
) -> None:
    assert _complete(tmp_path, demo, ["demo", ""]) == ["visible"]


def test_completes_options_and_hides_hidden_option(
    tmp_path: Path, demo: click.Group
) -> None:
    result = _complete(tmp_path, demo, ["demo", "-"])

    assert "--mode" in result
    assert "-m" in result
    assert "--tag" in result
    assert "--count" in result
    assert "--hidden-opt" not in result
    assert "--help" in result
    assert "-h" in result


def test_completes_choice_values(tmp_path: Path, demo: click.Group) -> None:
    result = _complete(tmp_path, demo, ["demo", "--mode", ""])

    assert result == ["fast", "slow"]


def test_completes_choice_after_equals(
    tmp_path: Path, demo: click.Group
) -> None:
    assert _complete(tmp_path, demo, ["demo", "--mode=f"]) == ["--mode=fast"]


def test_completes_only_value_after_equals(
    tmp_path: Path, demo: click.Group
) -> None:
    result = _complete(tmp_path, demo, ["demo", "--mode="])

    assert result == ["--mode=fast", "--mode=slow"]


def test_completes_path_after_equals(tmp_path: Path, demo: click.Group) -> None:
    (tmp_path / "equals.txt").write_text("x", encoding="utf-8")

    result = _complete(tmp_path, demo, ["demo", "--path=e"], cwd=tmp_path)

    assert "--path=equals.txt" in result


def test_completes_directories_for_dir_only_path(
    tmp_path: Path, demo: click.Group
) -> None:
    (tmp_path / "subdir").mkdir()

    result = _complete(tmp_path, demo, ["demo", "--out", ""], cwd=tmp_path)

    assert "subdir/" in result or "subdir" in result


def test_completes_files_for_file_only_path(
    tmp_path: Path, demo: click.Group
) -> None:
    (tmp_path / "afile.txt").write_text("x", encoding="utf-8")

    result = _complete(tmp_path, demo, ["demo", "--file", ""], cwd=tmp_path)

    assert "afile.txt" in result


def test_completes_files_and_dirs_for_general_path(
    tmp_path: Path, demo: click.Group
) -> None:
    (tmp_path / "afile.txt").write_text("x", encoding="utf-8")
    (tmp_path / "subdir").mkdir()

    result = _complete(tmp_path, demo, ["demo", "--path", ""], cwd=tmp_path)

    assert "afile.txt" in result
    assert "subdir/" in result or "subdir" in result


def test_completes_tuple_option_positions(
    tmp_path: Path, demo: click.Group
) -> None:
    (tmp_path / "tuplefile.txt").write_text("x", encoding="utf-8")

    first = _complete(tmp_path, demo, ["demo", "--pair", ""])
    second = _complete(
        tmp_path, demo, ["demo", "--pair", "a", ""], cwd=tmp_path
    )

    assert first == ["a", "b"]
    assert "tuplefile.txt" in second


def test_count_flag_does_not_consume_next_word(
    tmp_path: Path, demo: click.Group
) -> None:
    result = _complete(tmp_path, demo, ["demo", "--count", ""])

    assert "visible" in result


def test_variadic_positional_completion(tmp_path: Path) -> None:
    @click.group()
    def group() -> None:
        """Var group."""

    @group.command()
    @click.argument("names", nargs=-1, type=click.Choice(["x", "y"]))
    def names(names: tuple[str, ...]) -> None:
        """Take names."""

    result = _complete(tmp_path, group, ["group", "names", ""])

    assert result == ["x", "y"]


def test_help_option_can_be_disabled(tmp_path: Path) -> None:
    @click.group(add_help_option=False)
    def group() -> None:
        """No help group."""

    result = _complete(tmp_path, group, ["group", "-"])

    assert "--help" not in result
    assert "-h" not in result


def test_no_options_after_double_dash(
    tmp_path: Path, demo: click.Group
) -> None:
    result = _complete(tmp_path, demo, ["demo", "--", ""])

    assert result == []


def test_subcommand_options_are_leaf_options(
    tmp_path: Path,
) -> None:
    result = _complete(
        tmp_path, cli.main, ["cm", "generate", "-"], prog_name="cm"
    )

    assert result == ["-h", "--help"]


def test_root_completion_includes_commands_and_options(
    tmp_path: Path,
) -> None:
    commands = _complete(tmp_path, cli.main, ["cm", ""], prog_name="cm")
    options = _complete(tmp_path, cli.main, ["cm", "-"], prog_name="cm")

    assert "generate" in commands
    assert "commit" in commands
    for option in (
        "--color",
        "-s",
        "--staged",
        "--provider",
        "--model",
        "--config",
        "--completions",
        "--version",
        "--help",
        "-h",
    ):
        assert option in options


def test_completes_generate_without_parent_options(
    tmp_path: Path,
) -> None:
    result = _complete(
        tmp_path, cli.main, ["cm", "generate", ""], prog_name="cm"
    )

    assert result == []


def test_installed_bash_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(completions.shutil, "which", lambda name: "/bin/bash")
    monkeypatch.setattr(
        completions.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="5.2\n"),
    )

    assert completions.installed_bash_version() == (5, 2)


def test_installed_bash_version_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(completions.shutil, "which", lambda name: None)

    assert completions.installed_bash_version() is None


def test_installed_bash_version_subprocess_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(completions.shutil, "which", lambda name: "/bin/bash")

    def fail(
        *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        raise OSError("boom")

    monkeypatch.setattr(completions.subprocess, "run", fail)

    assert completions.installed_bash_version() is None
