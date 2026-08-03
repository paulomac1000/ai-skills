"""Structural YAML and shell command evidence for AGENTS.md audits."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

INVALID_YAML_MESSAGE = "YAML source is syntactically invalid and cannot establish command evidence."


def _normalize_invocation(command: str) -> str | None:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return None
    return " ".join(tokens) if tokens else None


def _command_segments(command: str) -> tuple[str, ...]:
    """Split shell command lists only at unquoted, unescaped separators."""
    segments: list[str] = []
    current: list[str] = []
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(command):
        character = command[index]
        if escaped:
            current.append(character)
            escaped = False
            index += 1
            continue
        if character == "\\" and quote != "'":
            current.append(character)
            escaped = True
            index += 1
            continue
        if quote is not None:
            current.append(character)
            if character == quote:
                quote = None
            index += 1
            continue
        if character in "'\"":
            quote = character
            current.append(character)
            index += 1
            continue
        separator_length = 0
        if character == ";":
            separator_length = 1
        elif command.startswith("&&", index) or command.startswith("||", index):
            separator_length = 2
        if separator_length:
            segment = "".join(current).strip()
            if segment:
                segments.append(segment)
            current = []
            index += separator_length
            continue
        current.append(character)
        index += 1
    segment = "".join(current).strip()
    if segment:
        segments.append(segment)
    return tuple(segments)


def _add_command_segments(invocations: set[str], command: str) -> None:
    for segment in _command_segments(command):
        normalized = _normalize_invocation(segment)
        if normalized is not None:
            invocations.add(normalized)


def _yaml_scalar_nodes(node: Node | None) -> list[tuple[tuple[str, ...], str, str | None]]:
    """Return scalar paths from a validated YAML syntax tree."""
    nodes: list[tuple[tuple[str, ...], str, str | None]] = []

    def visit(current: Node, path: tuple[str, ...]) -> None:
        if isinstance(current, ScalarNode):
            nodes.append((path, current.value, current.style))
            return
        if isinstance(current, SequenceNode):
            for item in current.value:
                visit(item, (*path, "[]"))
            return
        if isinstance(current, MappingNode):
            for key_node, value_node in current.value:
                if not isinstance(key_node, ScalarNode):
                    continue
                visit(value_node, (*path, key_node.value))

    if node is not None:
        visit(node, ())
    return nodes


def _yaml_node_is_executable(relative: str, path: tuple[str, ...]) -> bool:
    name = Path(relative).name.casefold()
    if relative.startswith(".github/workflows/"):
        return len(path) == 5 and path[0] == "jobs" and path[2:] == ("steps", "[]", "run")
    if relative == ".circleci/config.yml":
        return (len(path) == 5 and path[0] == "jobs" and path[2:] == ("steps", "[]", "run")) or (
            len(path) == 6 and path[0] == "jobs" and path[2:] == ("steps", "[]", "run", "command")
        )
    if name in {"azure-pipelines.yml", "azure-pipelines.yaml"}:
        return (
            len(path) >= 3
            and path[-3] == "steps"
            and path[-2] == "[]"
            and path[-1] in {"script", "bash", "pwsh", "powershell"}
        )
    if name in {"taskfile.yml", "taskfile.yaml"}:
        return (len(path) == 4 and path[0] == "tasks" and path[2:] == ("cmds", "[]")) or (
            len(path) == 5 and path[0] == "tasks" and path[2:] == ("cmds", "[]", "cmd")
        )
    if relative == ".gitlab-ci.yml":
        executable_keys = {"script", "before_script", "after_script"}
        return (len(path) >= 2 and path[-2] in executable_keys and path[-1] == "[]") or path[-1] in executable_keys
    return False


def _compose_yaml(text: str) -> Node | None:
    try:
        return yaml.compose(text, Loader=yaml.SafeLoader)
    except (yaml.YAMLError, RecursionError):
        return None


def _yaml_syntax_error(text: str) -> str | None:
    """Return a stable error that never includes repository-controlled excerpts."""
    try:
        yaml.compose(text, Loader=yaml.SafeLoader)
    except (yaml.YAMLError, RecursionError):
        return INVALID_YAML_MESSAGE
    return None


def _extract_yaml_invocations(relative: str, text: str) -> set[str]:
    root = _compose_yaml(text)
    if root is None:
        return set()
    invocations: set[str] = set()
    for path, value, style in _yaml_scalar_nodes(root):
        if not _yaml_node_is_executable(relative, path):
            continue
        if style == "|":
            invocations.update(_extract_shell_invocations(value))
        else:
            _add_command_segments(invocations, value)
    return invocations


def _shell_line_continues(line: str) -> bool:
    """Return whether the physical shell line ends in an active backslash-newline."""
    quote: str | None = None
    escaped = False
    for character in line.rstrip():
        if quote == "'":
            if character == "'":
                quote = None
            continue
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character in "'\"":
            quote = character if quote is None else None if quote == character else quote
    return escaped


def _logical_shell_lines(text: str) -> list[str]:
    """Join backslash-continued physical lines before shell normalization."""
    logical: list[str] = []
    pending = ""
    for raw_line in text.splitlines():
        candidate = raw_line.rstrip()
        combined = f"{pending}{candidate.lstrip()}" if pending else candidate
        if _shell_line_continues(combined):
            pending = f"{combined.rstrip()[:-1]} "
            continue
        logical.append(combined)
        pending = ""
    if pending:
        logical.append(pending.rstrip())
    return logical


def _extract_shell_invocations(text: str) -> set[str]:
    invocations: set[str] = set()
    heredoc_end: str | None = None
    for raw_line in _logical_shell_lines(text):
        line = raw_line.strip()
        if heredoc_end is not None:
            if line == heredoc_end:
                heredoc_end = None
            continue
        if not line or line.startswith("#"):
            continue
        heredoc = re.search(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1", line)
        if heredoc is not None:
            command = line[: heredoc.start()].rstrip()
            if command:
                _add_command_segments(invocations, command)
            heredoc_end = heredoc.group(2)
            continue
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\s*\(\)\s*\{?", line):
            continue
        if re.fullmatch(r"[{}]", line):
            continue
        _add_command_segments(invocations, line)
    return invocations


def _extract_powershell_invocations(text: str) -> set[str]:
    invocations: set[str] = set()
    in_block_comment = False
    here_string_end: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if in_block_comment:
            if "#>" in line:
                in_block_comment = False
            continue
        if here_string_end is not None:
            if line == here_string_end:
                here_string_end = None
            continue
        if line.startswith("<#"):
            in_block_comment = "#>" not in line
            continue
        if not line or line.startswith("#"):
            continue
        if line.endswith('@"') or line.endswith("@'"):
            here_string_end = '"@' if line.endswith('@"') else "'@"
            continue
        _add_command_segments(invocations, line)
    return invocations


def _extract_recipe_invocations(text: str, *, makefile: bool) -> set[str]:
    invocations: set[str] = set()
    in_recipe = False
    for raw_line in text.splitlines():
        if makefile:
            if raw_line.startswith("\t"):
                _add_command_segments(invocations, raw_line.lstrip().lstrip("@-+"))
            continue
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not raw_line[:1].isspace():
            in_recipe = stripped.endswith(":")
            continue
        if in_recipe:
            _add_command_segments(invocations, stripped)
    return invocations


def _extract_jenkins_invocations(text: str) -> set[str]:
    invocations: set[str] = set()
    pattern = re.compile(
        r"\b(?:sh|bat|powershell|pwsh)\s*(?:\(\s*)?(?:script\s*:\s*)?"
        r"(?P<quote>['\"])(?P<command>.*?)(?P=quote)"
    )
    for match in pattern.finditer(text):
        _add_command_segments(invocations, match.group("command"))
    return invocations


def _extract_gate_invocations(relative: str, text: str) -> set[str]:
    path = Path(relative)
    name = path.name
    suffix = path.suffix.casefold()
    if suffix in {".yml", ".yaml"}:
        return _extract_yaml_invocations(relative, text)
    if name == "Jenkinsfile":
        return _extract_jenkins_invocations(text)
    if name.casefold() == "makefile":
        return _extract_recipe_invocations(text, makefile=True)
    if name.casefold() == "justfile":
        return _extract_recipe_invocations(text, makefile=False)
    if suffix == ".ps1":
        return _extract_powershell_invocations(text)
    if suffix == ".sh" or not suffix and relative.startswith("bin/"):
        return _extract_shell_invocations(text)
    return set()


def _command_path_tokens(command: str) -> tuple[str, ...]:
    paths: list[str] = []
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return ()
    for token in tokens:
        cleaned = token.strip("'\"()[]{};,:")
        if "/" not in cleaned and "\\" not in cleaned:
            continue
        candidate = Path(cleaned)
        if candidate.is_absolute() or ".." in candidate.parts:
            continue
        paths.append(candidate.as_posix())
    return tuple(paths)
