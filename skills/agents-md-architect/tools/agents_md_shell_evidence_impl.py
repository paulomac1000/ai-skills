"""Structural YAML and shell command evidence for AGENTS.md audits."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

INVALID_YAML_MESSAGE = "YAML source is syntactically invalid and cannot establish command evidence."
_GITLAB_EXECUTABLE_KEYS = frozenset({"script", "before_script", "after_script"})
_GITLAB_RESERVED_TOP_LEVEL = frozenset(
    {
        "after_script",
        "before_script",
        "cache",
        "default",
        "image",
        "include",
        "services",
        "spec",
        "stages",
        "types",
        "variables",
        "workflow",
    }
)


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


def _gitlab_node_is_executable(path: tuple[str, ...]) -> bool:
    """Accept GitLab commands only from global defaults or top-level job scopes."""
    if not path:
        return False

    if path[0] in {"before_script", "after_script"}:
        return len(path) == 1 or (len(path) == 2 and path[1] == "[]")

    if path[0] == "default":
        return (len(path) == 2 and path[1] in {"before_script", "after_script"}) or (
            len(path) == 3 and path[1] in {"before_script", "after_script"} and path[2] == "[]"
        )

    if path[0] in _GITLAB_RESERVED_TOP_LEVEL:
        return False

    return (len(path) == 2 and path[1] in _GITLAB_EXECUTABLE_KEYS) or (
        len(path) == 3 and path[1] in _GITLAB_EXECUTABLE_KEYS and path[2] == "[]"
    )


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
        return _gitlab_node_is_executable(path)
    return False


def _yaml_node_uses_powershell(relative: str, path: tuple[str, ...]) -> bool:
    name = Path(relative).name.casefold()
    return (
        name in {"azure-pipelines.yml", "azure-pipelines.yaml"}
        and bool(path)
        and path[-1]
        in {
            "pwsh",
            "powershell",
        }
    )


def _mapping_value(node: Node | None, key: str) -> Node | None:
    if not isinstance(node, MappingNode):
        return None
    for key_node, value_node in node.value:
        if isinstance(key_node, ScalarNode) and key_node.value == key:
            return value_node
    return None


def _scalar_value(node: Node | None) -> str | None:
    return node.value if isinstance(node, ScalarNode) else None


def _normalize_working_directory(value: str) -> str | None:
    candidate = value.strip().replace("\\", "/")
    if not candidate or "${{" in candidate or "$((" in candidate or "$(" in candidate:
        return None
    if candidate.startswith(("/", "~", "//")) or re.match(r"^[A-Za-z]:", candidate):
        return None
    parts = tuple(part for part in candidate.split("/") if part not in {"", "."})
    if ".." in parts:
        return None
    normalized = "/".join(parts)
    return normalized or "."


def _working_directory_override(node: Node | None, inherited: str | None) -> str | None:
    if node is None:
        return inherited
    value = _scalar_value(node)
    return _normalize_working_directory(value) if value is not None else None


def _shell_override(node: Node | None, inherited: str | None) -> str | None:
    if node is None:
        return inherited
    value = _scalar_value(node)
    if value is None or "${{" in value:
        return None
    return value.strip().casefold()


def _github_condition_is_statically_false(node: Node | None) -> bool:
    value = _scalar_value(_mapping_value(node, "if"))
    if value is None:
        return False
    normalized = "".join(value.split()).casefold()
    return normalized in {"false", "${{false}}"}


def _github_run_defaults(node: Node | None) -> tuple[Node | None, Node | None]:
    run = _mapping_value(_mapping_value(node, "defaults"), "run")
    return _mapping_value(run, "working-directory"), _mapping_value(run, "shell")


def _github_runner_default_shell(job: Node) -> tuple[bool, str | None]:
    runs_on = _mapping_value(job, "runs-on")
    if runs_on is None:
        return False, None
    values: list[str] = []
    if isinstance(runs_on, ScalarNode):
        values.append(runs_on.value)
    elif isinstance(runs_on, SequenceNode):
        for item in runs_on.value:
            if not isinstance(item, ScalarNode):
                return False, None
            values.append(item.value)
    else:
        return False, None
    if not values or any(not value.strip() for value in values):
        return False, None
    if any("${{" in value for value in values):
        return True, None
    labels = tuple(value.casefold() for value in values)
    if any("windows" in value for value in labels):
        return True, "pwsh"
    if any(any(marker in value for marker in ("ubuntu", "linux", "macos")) for value in labels):
        return True, ""
    return True, None


def _github_shell_kind(shell: str) -> str | None:
    executable = shell.split(maxsplit=1)[0] if shell else ""
    if executable in {"pwsh", "powershell"}:
        return "powershell"
    if executable in {"", "bash", "sh"}:
        return "shell"
    return None


def _extract_github_yaml_command_evidence(
    root: Node,
    default_working_directory: str,
) -> set[tuple[str, str]]:
    evidence: set[tuple[str, str]] = set()
    workflow_cwd_node, workflow_shell_node = _github_run_defaults(root)
    workflow_cwd = _working_directory_override(workflow_cwd_node, default_working_directory)
    jobs = _mapping_value(root, "jobs")
    if not isinstance(jobs, MappingNode):
        return evidence

    for _job_key, job in jobs.value:
        if not isinstance(job, MappingNode) or _github_condition_is_statically_false(job):
            continue
        has_runner, runner_shell = _github_runner_default_shell(job)
        if not has_runner:
            continue
        job_cwd_node, job_shell_node = _github_run_defaults(job)
        job_cwd = _working_directory_override(job_cwd_node, workflow_cwd)
        workflow_shell = _shell_override(workflow_shell_node, runner_shell)
        job_shell = _shell_override(job_shell_node, workflow_shell)
        steps = _mapping_value(job, "steps")
        if not isinstance(steps, SequenceNode):
            continue
        for step in steps.value:
            if not isinstance(step, MappingNode) or _github_condition_is_statically_false(step):
                continue
            run = _scalar_value(_mapping_value(step, "run"))
            if run is None:
                continue
            working_directory = _working_directory_override(_mapping_value(step, "working-directory"), job_cwd)
            shell = _shell_override(_mapping_value(step, "shell"), job_shell)
            if working_directory is None or shell is None:
                continue
            shell_kind = _github_shell_kind(shell)
            if shell_kind is None:
                continue
            commands = (
                _extract_powershell_invocations(run) if shell_kind == "powershell" else _extract_shell_invocations(run)
            )
            evidence.update((working_directory, command) for command in commands)
    return evidence


def _has_duplicate_yaml_mapping_key(node: Node) -> bool:
    if isinstance(node, SequenceNode):
        return any(_has_duplicate_yaml_mapping_key(item) for item in node.value)
    if not isinstance(node, MappingNode):
        return False
    keys: set[tuple[str, str]] = set()
    for key_node, value_node in node.value:
        if isinstance(key_node, ScalarNode):
            identity = (key_node.tag, key_node.value)
            if identity in keys:
                return True
            keys.add(identity)
        if _has_duplicate_yaml_mapping_key(value_node):
            return True
    return False


def _compose_yaml(text: str) -> Node | None:
    try:
        root = yaml.compose(text, Loader=yaml.SafeLoader)
    except (yaml.YAMLError, RecursionError):
        return None
    if root is not None and _has_duplicate_yaml_mapping_key(root):
        return None
    return root


def _yaml_syntax_error(text: str) -> str | None:
    """Return a stable error that never includes repository-controlled excerpts."""
    try:
        root = yaml.compose(text, Loader=yaml.SafeLoader)
    except (yaml.YAMLError, RecursionError):
        return INVALID_YAML_MESSAGE
    if root is not None and _has_duplicate_yaml_mapping_key(root):
        return INVALID_YAML_MESSAGE
    return None


def _extract_yaml_command_evidence(
    relative: str,
    text: str,
    default_working_directory: str = ".",
) -> set[tuple[str, str]]:
    root = _compose_yaml(text)
    if root is None:
        return set()
    if relative.startswith(".github/workflows/"):
        return _extract_github_yaml_command_evidence(root, default_working_directory)

    evidence: set[tuple[str, str]] = set()
    for path, value, _style in _yaml_scalar_nodes(root):
        if not _yaml_node_is_executable(relative, path):
            continue
        commands = (
            _extract_powershell_invocations(value)
            if _yaml_node_uses_powershell(relative, path)
            else _extract_shell_invocations(value)
        )
        evidence.update((default_working_directory, command) for command in commands)
    return evidence


def _extract_yaml_invocations(relative: str, text: str) -> set[str]:
    return {command for _working_directory, command in _extract_yaml_command_evidence(relative, text)}


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


def _strip_shell_comment(line: str) -> str:
    """Remove an active POSIX-shell comment without touching quoted or escaped hashes."""
    quote: str | None = None
    escaped = False
    for index, character in enumerate(line):
        if escaped:
            escaped = False
            continue
        if character == "\\" and quote != "'":
            escaped = True
            continue
        if quote is not None:
            if character == quote:
                quote = None
            continue
        if character in "'\"":
            quote = character
            continue
        if character == "#" and (index == 0 or line[index - 1].isspace() or line[index - 1] in ";|&()<>"):
            return line[:index].rstrip()
    return line.rstrip()


def _extract_shell_invocations(text: str) -> set[str]:
    invocations: set[str] = set()
    heredoc_end: str | None = None
    for raw_line in _logical_shell_lines(text):
        line = raw_line.strip()
        if heredoc_end is not None:
            if line == heredoc_end:
                heredoc_end = None
            continue
        line = _strip_shell_comment(line).strip()
        if not line:
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


def _strip_powershell_comments(line: str, in_block_comment: bool) -> tuple[str, bool]:
    """Remove PowerShell comments while preserving quoted strings and backtick escapes."""
    output: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(line):
        if in_block_comment:
            end = line.find("#>", index)
            if end < 0:
                return "".join(output).rstrip(), True
            in_block_comment = False
            index = end + 2
            continue

        character = line[index]
        if quote == '"' and character == "`":
            output.append(character)
            if index + 1 < len(line):
                output.append(line[index + 1])
                index += 2
            else:
                index += 1
            continue
        if quote == "'" and character == "'" and index + 1 < len(line) and line[index + 1] == "'":
            output.extend(("'", "'"))
            index += 2
            continue
        if quote is not None:
            output.append(character)
            if character == quote:
                quote = None
            index += 1
            continue
        if character in "'\"":
            quote = character
            output.append(character)
            index += 1
            continue
        if line.startswith("<#", index):
            in_block_comment = True
            index += 2
            continue
        if character == "#":
            break
        output.append(character)
        index += 1
    return "".join(output).rstrip(), in_block_comment


def _extract_powershell_invocations(text: str) -> set[str]:
    invocations: set[str] = set()
    in_block_comment = False
    here_string_end: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if here_string_end is not None:
            if line == here_string_end:
                here_string_end = None
            continue
        line, in_block_comment = _strip_powershell_comments(line, in_block_comment)
        line = line.strip()
        if not line:
            continue
        if line.endswith('@"') or line.endswith("@'"):
            here_string_end = '"@' if line.endswith('@"') else "'@"
            continue
        _add_command_segments(invocations, line)
    return invocations


_JUST_RECIPE_HEADER = re.compile(r"^@?[A-Za-z_][\w-]*(?:\s+[^\s:]+)*\s*:(?!=)")


def _extract_recipe_invocations(text: str, *, makefile: bool) -> set[str]:
    invocations: set[str] = set()
    in_recipe = False
    for raw_line in text.splitlines():
        if makefile:
            if raw_line.startswith("\t"):
                invocations.update(_extract_shell_invocations(raw_line.lstrip().lstrip("@-+")))
            continue
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not raw_line[:1].isspace():
            in_recipe = _JUST_RECIPE_HEADER.match(stripped) is not None
            continue
        if in_recipe:
            invocations.update(_extract_shell_invocations(stripped))
    return invocations


def _strip_groovy_comments(text: str) -> str:
    """Strip Groovy line and block comments without treating markers inside strings as comments."""
    output: list[str] = []
    quote: str | None = None
    escaped = False
    in_block_comment = False
    index = 0
    while index < len(text):
        if in_block_comment:
            if text.startswith("*/", index):
                in_block_comment = False
                index += 2
            else:
                if text[index] == "\n":
                    output.append("\n")
                index += 1
            continue
        character = text[index]
        if escaped:
            output.append(character)
            escaped = False
            index += 1
            continue
        if quote is not None:
            output.append(character)
            if character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            index += 1
            continue
        if character in "'\"":
            quote = character
            output.append(character)
            index += 1
            continue
        if text.startswith("//", index):
            newline = text.find("\n", index + 2)
            if newline < 0:
                break
            output.append("\n")
            index = newline + 1
            continue
        if text.startswith("/*", index):
            in_block_comment = True
            index += 2
            continue
        output.append(character)
        index += 1
    return "".join(output)


def _extract_jenkins_invocations(text: str) -> set[str]:
    invocations: set[str] = set()
    cleaned = _strip_groovy_comments(text)
    multiline = re.compile(
        r"(?ms)^[ \t]*(?P<step>sh|bat|powershell|pwsh)\s*(?:\(\s*)?(?:script\s*:\s*)?"
        r"(?P<quote>'''|\"\"\")(?P<command>.*?)(?P=quote)\s*\)?\s*;?[ \t]*$"
    )
    masked = list(cleaned)
    for match in multiline.finditer(cleaned):
        extractor = (
            _extract_powershell_invocations
            if match.group("step") in {"powershell", "pwsh"}
            else _extract_shell_invocations
        )
        invocations.update(extractor(match.group("command")))
        for index in range(match.start(), match.end()):
            if masked[index] != "\n":
                masked[index] = " "

    single_line = re.compile(
        r"^\s*(?P<step>sh|bat|powershell|pwsh)\s*(?:\(\s*)?(?:script\s*:\s*)?"
        r"(?P<quote>['\"])(?P<command>(?:\\.|(?!\2).)*?)(?P=quote)\s*\)?\s*;?\s*$"
    )
    for line in "".join(masked).splitlines():
        single_match = single_line.fullmatch(line)
        if single_match is None:
            continue
        extractor = (
            _extract_powershell_invocations
            if single_match.group("step") in {"powershell", "pwsh"}
            else _extract_shell_invocations
        )
        invocations.update(extractor(single_match.group("command")))
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
