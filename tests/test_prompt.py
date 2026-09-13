from __future__ import annotations

from cm.prompt import build_prompt, wrap_message


def test_build_prompt_includes_all_context() -> None:
    prompt = build_prompt("DIFF-CONTENT", "STAT-CONTENT", "abc123 recent commit")

    assert "DIFF-CONTENT" in prompt
    assert "STAT-CONTENT" in prompt
    assert "abc123 recent commit" in prompt
    assert "Recent commit messages" in prompt


def test_wrap_message_wraps_bullets() -> None:
    long_line = "* " + "word " * 30
    result = wrap_message(long_line)
    lines = result.splitlines()

    assert len(lines) > 1
    for line in lines:
        assert len(line) <= 72
    assert lines[0].startswith("* ")
    assert lines[1].startswith("  ")


def test_wrap_message_leaves_other_lines_alone() -> None:
    message = "Subject line\n\nplain body line"
    assert wrap_message(message) == message
