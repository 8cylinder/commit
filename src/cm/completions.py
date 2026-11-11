from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import tempfile
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import click

APP_NAME = "cm"
MIN_BASH_VERSION = (4, 4)
COMPLETION_FILENAME = f"{APP_NAME}.bash"

_BASH_VERSION = re.compile(r"(\d+)\.(\d+)")


@dataclass
class _Node:
    id: int
    command: click.Command
    func_name: str
    children: dict[str, _Node] = field(default_factory=dict)


@dataclass(frozen=True)
class _ValueOption:
    key: str
    opts: tuple[str, ...]
    count: int
    type: click.ParamType[Any]
    tuple_types: tuple[click.ParamType[Any], ...] | None = None


def _sanitize(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", name)


def _build_tree(
    command: click.Command, prog_name: str, counter: list[int]
) -> _Node:
    node_id = counter[0]
    counter[0] += 1
    if node_id == 0:
        func_name = f"_{_sanitize(prog_name)}_complete"
    else:
        func_name = f"_{_sanitize(prog_name)}_cmd_{node_id}"

    node = _Node(id=node_id, command=command, func_name=func_name)
    if isinstance(command, click.Group):
        for name, child in command.commands.items():
            if child.hidden:
                continue
            node.children[name] = _build_tree(child, prog_name, counter)
    return node


def _walk_nodes(node: _Node) -> Iterator[_Node]:
    yield node
    for child in node.children.values():
        yield from _walk_nodes(child)


def _is_visible(option: click.Option) -> bool:
    return not getattr(option, "hidden", False)


def _value_count(option: click.Option) -> int:
    if option.is_flag or getattr(option, "count", False):
        return 0
    nargs = option.nargs
    return nargs if nargs and nargs > 0 else 1


def _value_options(command: click.Command) -> list[_ValueOption]:
    options: list[_ValueOption] = []
    for param in command.params:
        if not isinstance(param, click.Option) or not _is_visible(param):
            continue
        count = _value_count(param)
        if count == 0:
            continue
        tuple_types: tuple[click.ParamType[Any], ...] | None = None
        if isinstance(param.type, click.Tuple):
            tuple_types = tuple(param.type.types)
            count = len(tuple_types)
        options.append(
            _ValueOption(
                key=f"v{len(options)}",
                opts=tuple(param.opts),
                count=count,
                type=param.type,
                tuple_types=tuple_types,
            )
        )
    return options


def _help_context(command: click.Command) -> click.Context:
    return click.Context(
        command,
        help_option_names=command.context_settings.get("help_option_names"),
    )


def _flag_options(command: click.Command) -> list[str]:
    flags: list[str] = []
    for param in command.params:
        if not isinstance(param, click.Option) or not _is_visible(param):
            continue
        if _value_count(param) == 0:
            flags.extend(param.opts)

    ctx = _help_context(command)
    if command.get_help_option(ctx) is not None:
        flags.extend(command.get_help_option_names(ctx))
    return list(dict.fromkeys(flags))


def _visible_option_names(command: click.Command) -> list[str]:
    names: list[str] = []
    for param in command.params:
        if isinstance(param, click.Option) and _is_visible(param):
            names.extend(param.opts)

    ctx = _help_context(command)
    if command.get_help_option(ctx) is not None:
        names.extend(command.get_help_option_names(ctx))
    return list(dict.fromkeys(names))


def _completion_call(param_type: click.ParamType[Any], var: str) -> str | None:
    if isinstance(param_type, click.Choice):
        choices = " ".join(
            shlex.quote(str(choice)) for choice in param_type.choices
        )
        call = f'_cm_complete_choice "${var}"'
        return f"{call} {choices}" if choices else call

    if isinstance(param_type, click.File):
        return f'_cm_complete_file "${var}"'

    if isinstance(param_type, click.Path):
        if not param_type.file_okay and not param_type.dir_okay:
            return None
        if param_type.dir_okay and not param_type.file_okay:
            return f'_cm_complete_dir "${var}"'
        if param_type.file_okay and not param_type.dir_okay:
            return f'_cm_complete_file "${var}"'
        return f'_cm_complete_path "${var}"'

    return None


def _scan_block(
    node: _Node, options: list[_ValueOption], flags: list[str]
) -> list[str]:
    lines = [
        "    local pos=0",
        "    local after_dd=0",
        "    local pending=0",
        '    local pending_opt=""',
        "    local pending_index=0",
        "    local i word",
        "    for ((i = start; i < COMP_CWORD; i++)); do",
        '        word="${COMP_WORDS[i]}"',
        "        if (( pending > 0 )); then",
        "            ((pending--))",
        "            ((pending_index++))",
        "            continue",
        "        fi",
        "        if (( after_dd )); then",
        "            ((pos++))",
        "            continue",
        "        fi",
        '        case "$word" in',
        "            --)",
        "                after_dd=1",
        "                ;;",
    ]

    if flags:
        pattern = "|".join(shlex.quote(flag) for flag in flags)
        lines.append(f"            {pattern})")
        lines.append("                ;;")

    for option in options:
        for opt in option.opts:
            quoted = shlex.quote(opt)
            lines.append(f"            {quoted})")
            lines.append(f"                pending={option.count}")
            lines.append(f"                pending_opt={option.key}")
            lines.append("                pending_index=0")
            lines.append("                ;;")
            lines.append(f"            {quoted}=*)")
            lines.append("                ;;")

    lines.extend(
        [
            "            -*)",
            "                ;;",
            "            *)",
        ]
    )
    if node.children:
        lines.append('                case "$word" in')
        for name, child in node.children.items():
            lines.append(
                f"                    {shlex.quote(name)}) "
                f"{child.func_name} $((i + 1)); return 0 ;;"
            )
        lines.append("                esac")
    lines.extend(
        [
            "                ((pos++))",
            "                ;;",
            "        esac",
            "    done",
        ]
    )
    return lines


def _equals_branch(options: list[_ValueOption]) -> list[str]:
    if not options:
        return []

    lines = [
        '    if (( ! after_dd )) && [[ "$cur" == -*=* ]]; then',
        '        local opt="${cur%%=*}"',
        '        local value="${cur#*=}"',
        "        local handled=0",
        '        case "$opt" in',
    ]
    for option in options:
        if option.tuple_types is not None:
            call = _completion_call(option.tuple_types[0], "value")
        else:
            call = _completion_call(option.type, "value")
        for opt in option.opts:
            quoted = shlex.quote(opt)
            if call is None:
                lines.append(f"            {quoted}) handled=1 ;;")
            else:
                lines.append(f"            {quoted}) {call}; handled=1 ;;")

    lines.extend(
        [
            "        esac",
            "        if (( handled )); then",
            "            local item",
            '            for item in "${!COMPREPLY[@]}"; do',
            '                COMPREPLY[$item]="${opt}=${COMPREPLY[$item]}"',
            "            done",
            "            compopt -o nospace 2>/dev/null || true",
            "            return 0",
            "        fi",
            "    fi",
        ]
    )
    return lines


def _pending_branch(options: list[_ValueOption]) -> list[str]:
    if not options:
        return []

    lines = [
        "    if (( pending > 0 )); then",
        '        case "$pending_opt" in',
    ]
    for option in options:
        if option.tuple_types is not None:
            lines.append(f"            {option.key})")
            lines.append('                case "$pending_index" in')
            for index, type_ in enumerate(option.tuple_types):
                call = _completion_call(type_, "cur")
                lines.append(
                    f"                    {index}) {call} ;;"
                    if call
                    else f"                    {index}) ;;"
                )
            lines.extend(["                esac", "                ;;"])
        else:
            call = _completion_call(option.type, "cur")
            lines.append(
                f"            {option.key}) {call} ;;"
                if call
                else f"            {option.key}) ;;"
            )

    lines.extend(["        esac", "        return 0", "    fi"])
    return lines


def _positional_entries(
    command: click.Command,
) -> tuple[
    list[tuple[int, click.ParamType[Any]]],
    tuple[int, click.ParamType[Any]] | None,
]:
    entries: list[tuple[int, click.ParamType[Any]]] = []
    variadic: tuple[int, click.ParamType[Any]] | None = None
    index = 0

    for param in command.params:
        if not isinstance(param, click.Argument):
            continue
        if getattr(param, "hidden", False):
            continue
        if param.nargs == -1:
            variadic = (index, param.type)
            break
        if isinstance(param.type, click.Tuple):
            types = list(param.type.types)
        else:
            types = [param.type] * (param.nargs if param.nargs > 0 else 1)
        for type_ in types:
            entries.append((index, type_))
            index += 1

    return entries, variadic


def _positional_case(command: click.Command) -> list[str]:
    entries, variadic = _positional_entries(command)
    if not entries and variadic is None:
        return []

    lines = ['    case "$pos" in']
    for index, type_ in entries:
        call = _completion_call(type_, "cur")
        lines.append(
            f"        {index}) {call} ;;" if call else f"        {index}) ;;"
        )
    if variadic is not None:
        start, type_ = variadic
        call = _completion_call(type_, "cur")
        lines.append(
            f"        {start}|*) {call} ;;"
            if call
            else f"        {start}|*) ;;"
        )
    lines.append("    esac")
    return lines


def _command_function(node: _Node) -> list[str]:
    options = _value_options(node.command)
    flags = _flag_options(node.command)
    option_names = _visible_option_names(node.command)

    lines = [
        f"{node.func_name}() {{",
        '    local start="${1:-1}"',
        '    local cur="${COMP_WORDS[COMP_CWORD]}"',
        '    local prev="${COMP_WORDS[COMP_CWORD-1]}"',
        "    COMPREPLY=()",
        "",
    ]
    lines.extend(_scan_block(node, options, flags))
    lines.append("")

    equals = _equals_branch(options)
    if equals:
        lines.extend(equals)
        lines.append("")

    pending = _pending_branch(options)
    if pending:
        lines.extend(pending)
        lines.append("")

    if option_names:
        calls = " ".join(shlex.quote(name) for name in option_names)
        lines.extend(
            [
                '    if (( ! after_dd )) && [[ "$cur" == -* ]]; then',
                f'        _cm_complete_choice "$cur" {calls}',
                "        return 0",
                "    fi",
                "",
            ]
        )

    if node.children:
        names = " ".join(shlex.quote(name) for name in node.children)
        lines.extend(
            [
                "    if (( ! after_dd )) && (( pos == 0 )); then",
                f'        _cm_complete_choice "$cur" {names}',
                "        return 0",
                "    fi",
                "",
            ]
        )

    positional = _positional_case(node.command)
    if positional:
        lines.extend(positional)
        lines.append("")

    lines.extend(["    return 0", "}"])
    return lines


_HELPERS = [
    "_cm_complete_choice() {",
    '    local cur="$1"',
    "    shift",
    "    local choice",
    "    COMPREPLY=()",
    '    for choice in "$@"; do',
    '        if [[ "$choice" == "$cur"* ]]; then',
    '            COMPREPLY+=( "$choice" )',
    "        fi",
    "    done",
    "    compopt -o nosort 2>/dev/null || true",
    "}",
    "",
    "_cm_complete_file() {",
    '    local cur="$1"',
    "    if declare -F _filedir >/dev/null 2>&1; then",
    "        _filedir",
    "    else",
    '        mapfile -t COMPREPLY < <(compgen -f -- "$cur")',
    "        compopt -o nospace 2>/dev/null || true",
    "    fi",
    "}",
    "",
    "_cm_complete_dir() {",
    '    local cur="$1"',
    "    if declare -F _filedir >/dev/null 2>&1; then",
    "        _filedir -d",
    "    else",
    '        mapfile -t COMPREPLY < <(compgen -d -- "$cur")',
    "        compopt -o nospace 2>/dev/null || true",
    "    fi",
    "}",
    "",
    "_cm_complete_path() {",
    '    local cur="$1"',
    "    if declare -F _filedir >/dev/null 2>&1; then",
    "        _filedir",
    "    else",
    '        mapfile -t COMPREPLY < <(compgen -f -- "$cur"; '
    'compgen -d -- "$cur")',
    "        compopt -o nospace 2>/dev/null || true",
    "    fi",
    "}",
]


def generate_bash_completion(
    group: click.Group, prog_name: str, version: str
) -> str:
    """Return the complete static bash completion script."""
    counter = [0]
    root = _build_tree(group, prog_name, counter)

    lines = [
        f"# bash completion for {prog_name} {version}",
        f"# Generated by `{prog_name} --completions`; do not edit by hand.",
        f"# Re-run `{prog_name} --completions` after changing commands "
        "or options.",
        "# This file is generated and will be overwritten.",
        "",
    ]
    lines.extend(_HELPERS)
    lines.append("")

    for node in _walk_nodes(root):
        lines.extend(_command_function(node))
        lines.append("")

    lines.append(
        "complete -o nosort -o bashdefault -o default "
        f"-F {root.func_name} {shlex.quote(prog_name)}"
    )
    return "\n".join(lines) + "\n"


def _absolute(path: Path) -> Path:
    return path if path.is_absolute() else path.absolute()


def completion_dir(environ: Mapping[str, str] | None = None) -> Path:
    """Return the bash-completion directory.

    The destination follows bash-completion's own search order:
    BASH_COMPLETION_USER_DIR, then XDG_DATA_HOME, then ~/.local/share.
    """
    env = os.environ if environ is None else environ

    user_dir = env.get("BASH_COMPLETION_USER_DIR")
    if user_dir:
        first = next((entry for entry in user_dir.split(":") if entry), None)
        if first:
            base = Path(first).expanduser()
            return _absolute(base) / "bash-completion" / "completions"

    data_home = env.get("XDG_DATA_HOME")
    base = (
        Path(data_home).expanduser()
        if data_home
        else Path.home() / ".local/share"
    )
    return _absolute(base) / "bash-completion" / "completions"


def completion_path(environ: Mapping[str, str] | None = None) -> Path:
    """Return the path where the completion script is written."""
    return completion_dir(environ) / COMPLETION_FILENAME


def install_bash_completion(
    group: click.Group,
    prog_name: str,
    version: str,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Write the completion script atomically and return its path."""
    path = completion_path(environ)
    path.parent.mkdir(parents=True, exist_ok=True)
    script = generate_bash_completion(group, prog_name, version)

    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", text=True
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(script)
        tmp.chmod(0o644)
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return path


def installed_bash_version() -> tuple[int, int] | None:
    """Return the (major, minor) version of the bash on PATH, if available."""
    bash = shutil.which("bash")
    if bash is None:
        return None

    try:
        result = subprocess.run(
            [
                bash,
                "-c",
                'printf "%s.%s\\n" "${BASH_VERSINFO[0]}" "${BASH_VERSINFO[1]}"',
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    match = _BASH_VERSION.search(result.stdout)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))
