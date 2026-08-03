#!/usr/bin/env python3
"""Audit AGENTS.md instruction trees without executing repository-controlled commands."""

from __future__ import annotations

import argparse
import ast
import json
import re
import shlex
import sys
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, cast

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from agents_md_parse import parse_visible_lines, read_utf8_bounded  # noqa: E402
from agents_md_types import (  # noqa: E402
    MAX_GATE_FILE_BYTES,
    MAX_GATE_FILES,
    MAX_GATE_TOTAL_BYTES,
    LanguageName,
    LayoutName,
)
from discover_repository import Discovery, discover  # noqa: E402
from validate_agents_md import Finding, normalize_selection, validate_many_with_documents  # noqa: E402

Severity = Literal["error", "warning"]
CODE_SPAN = re.compile(r"`([^`\n]+)`")
LINT_LEAKAGE = re.compile(
    r"(?i)\b(?:line length|quote style|indent(?:ation)? width|ruff rule|eslint rule|prettier config|"
    r"formatter config|stylecop rule)\b"
)
FULL_GATE_LINE = re.compile(
    r"(?i)\b(?:full gate|complete gate|completion check|hosted ci|ci gate|pełna bramka|pełny gate)\b"
)


@dataclass(frozen=True)
class AuditFinding:
    """One repository-level instruction audit result."""

    path: str
    severity: Severity
    code: str
    line: int
    message: str


def _confined_file(root: Path, relative: str) -> Path:
    try:
        path = root / relative
        if path.is_symlink():
            raise ValueError(f"refusing to read symlink: {relative}")
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
        if not resolved.is_file():
            raise ValueError(f"not a regular file: {relative}")
    except ValueError:
        raise
    except (OSError, RuntimeError) as error:
        raise ValueError(f"unreadable file {relative}: {error}") from error
    return resolved


def _read_text(root: Path, relative: str, max_bytes: int = 2 * 1024 * 1024) -> str:
    path = _confined_file(root, relative)
    result = read_utf8_bounded(path, max_bytes=max_bytes)
    if result.code is not None or result.text is None:
        raise ValueError(result.message or result.code or "unreadable file")
    return result.text


def _paragraphs(text: str) -> dict[str, int]:
    result: dict[str, int] = {}
    block: list[str] = []
    start = 1
    visible, _ = parse_visible_lines(text)
    for number, line in visible + [(len(text.splitlines()) + 1, "")]:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            if not block:
                start = number
            block.append(stripped)
            continue
        if block:
            normalized = re.sub(r"[^\w]+", " ", " ".join(block).casefold(), flags=re.UNICODE).strip()
            if len(normalized.split()) >= 12:
                result.setdefault(normalized, start)
            block = []
    return result


def _normalize_invocation(command: str) -> str | None:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return None
    return " ".join(tokens) if tokens else None


def _add_command_segments(invocations: set[str], command: str) -> None:
    for segment in re.split(r"\s*(?:&&|\|\||;)\s*", command):
        normalized = _normalize_invocation(segment.strip())
        if normalized is not None:
            invocations.add(normalized)


YAML_MAPPING = re.compile(r"^(?P<indent> *)(?P<list>-\s*)?(?P<key>[A-Za-z_][A-Za-z0-9_-]*):(?:\s*(?P<value>.*))?$")
YAML_BLOCK_STYLES = {"|", ">", "|-", "|+", ">-", ">+"}


def _yaml_indent(line: str) -> int | None:
    prefix = line[: len(line) - len(line.lstrip(" \t"))]
    return None if "\t" in prefix else len(prefix)


def _strip_yaml_comment(value: str) -> str:
    quote: str | None = None
    escaped = False
    for index, character in enumerate(value):
        if escaped:
            escaped = False
            continue
        if character == "\\" and quote == '"':
            escaped = True
            continue
        if character in "'\"":
            if quote is None:
                quote = character
            elif quote == character:
                quote = None
            continue
        if character == "#" and quote is None and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    return value.rstrip()


def _unquote_scalar(value: str) -> str:
    stripped = _strip_yaml_comment(value).strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in "'\"":
        return stripped[1:-1]
    return stripped


def _fold_yaml_lines(lines: list[str]) -> str:
    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        if line:
            current.append(line.strip())
            continue
        if current:
            paragraphs.append(" ".join(current))
            current = []
        paragraphs.append("")
    if current:
        paragraphs.append(" ".join(current))
    return "\n".join(paragraphs).strip()


def _read_yaml_scalar(
    lines: list[str],
    index: int,
    parent_indent: int,
    raw_value: str,
) -> tuple[str, str | None, int]:
    value = _strip_yaml_comment(raw_value).strip()
    if value not in YAML_BLOCK_STYLES:
        return _unquote_scalar(value), None, index + 1

    body: list[str] = []
    cursor = index + 1
    while cursor < len(lines):
        candidate = lines[cursor]
        candidate_indent = _yaml_indent(candidate)
        if candidate.strip() and (candidate_indent is None or candidate_indent <= parent_indent):
            break
        body.append(candidate)
        cursor += 1

    nonblank_indents = [indent for line in body if line.strip() and (indent := _yaml_indent(line)) is not None]
    content_indent = min(nonblank_indents, default=parent_indent + 1)
    content = [line[content_indent:].rstrip() if line.strip() else "" for line in body]
    style = value[0]
    if style == "|":
        return "\n".join(content).strip("\n"), style, cursor
    return _fold_yaml_lines(content), style, cursor


def _yaml_scalar_nodes(text: str) -> list[tuple[tuple[str, ...], str, str | None]]:
    lines = text.splitlines()
    stack: list[tuple[int, str]] = []
    nodes: list[tuple[tuple[str, ...], str, str | None]] = []
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        indent = _yaml_indent(raw_line)
        if indent is None or not stripped or stripped.startswith("#"):
            index += 1
            continue

        while stack and stack[-1][0] >= indent:
            stack.pop()
        match = YAML_MAPPING.fullmatch(raw_line)
        if match is None:
            if stripped.startswith("- "):
                stack.append((indent, "[]"))
                value = _unquote_scalar(stripped[2:])
                if value:
                    nodes.append((tuple(item[1] for item in stack), value, None))
            index += 1
            continue

        is_list_item = match.group("list") is not None
        if is_list_item:
            stack.append((indent, "[]"))
        key = match.group("key")
        raw_value = match.group("value") or ""
        path = tuple(item[1] for item in stack) + (key,)
        cleaned = _strip_yaml_comment(raw_value).strip()
        if not cleaned:
            stack.append((indent + (1 if is_list_item else 0), key))
            index += 1
            continue

        value, style, next_index = _read_yaml_scalar(lines, index, indent, raw_value)
        if value:
            nodes.append((path, value, style))
        index = next_index
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
            and path[-1]
            in {
                "script",
                "bash",
                "pwsh",
                "powershell",
            }
        )
    if name in {"taskfile.yml", "taskfile.yaml"}:
        return (len(path) == 4 and path[0] == "tasks" and path[2:] == ("cmds", "[]")) or (
            len(path) == 5 and path[0] == "tasks" and path[2:] == ("cmds", "[]", "cmd")
        )
    if relative == ".gitlab-ci.yml":
        executable_keys = {"script", "before_script", "after_script"}
        return (len(path) >= 2 and path[-2] in executable_keys and path[-1] == "[]") or path[-1] in executable_keys
    return False


def _extract_yaml_invocations(relative: str, text: str) -> set[str]:
    invocations: set[str] = set()
    for path, value, style in _yaml_scalar_nodes(text):
        if not _yaml_node_is_executable(relative, path):
            continue
        if style == "|":
            invocations.update(_extract_shell_invocations(value))
        else:
            _add_command_segments(invocations, value)
    return invocations


def _literal_python_command(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple)):
        values: list[str] = []
        for element in node.elts:
            if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
                return None
            values.append(element.value)
        return shlex.join(values)
    return None


def _extract_python_invocations(text: str) -> set[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    invocations: set[str] = set()
    subprocess_calls = {"run", "call", "check_call", "check_output", "Popen"}
    subprocess_modules = {"subprocess"}
    os_modules = {"os"}
    subprocess_functions: set[str] = set()
    system_functions: set[str] = set()

    for node in cast(list[ast.AST], tree.body):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local_name = alias.asname or alias.name
                if alias.name == "subprocess":
                    subprocess_modules.add(local_name)
                elif alias.name == "os":
                    os_modules.add(local_name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == "subprocess":
                for alias in node.names:
                    if alias.name in subprocess_calls:
                        subprocess_functions.add(alias.asname or alias.name)
            elif node.module == "os":
                for alias in node.names:
                    if alias.name == "system":
                        system_functions.add(alias.asname or alias.name)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        accepted = False
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            owner = node.func.value.id
            accepted = (owner in subprocess_modules and node.func.attr in subprocess_calls) or (
                owner in os_modules and node.func.attr == "system"
            )
        elif isinstance(node.func, ast.Name):
            accepted = node.func.id in subprocess_functions or node.func.id in system_functions
        if not accepted:
            continue
        argument = node.args[0] if node.args else None
        if argument is None:
            argument = next(
                (keyword.value for keyword in node.keywords if keyword.arg in {"args", "command"}),
                None,
            )
        if argument is None:
            continue
        command = _literal_python_command(argument)
        if command is not None:
            _add_command_segments(invocations, command)
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
    if suffix == ".py":
        return _extract_python_invocations(text)
    if suffix == ".ps1":
        return _extract_powershell_invocations(text)
    if suffix == ".sh" or not suffix and relative.startswith("bin/"):
        return _extract_shell_invocations(text)
    return set()


def _entrypoint_invocations(discovery: Discovery) -> set[str]:
    invocations: set[str] = set()
    for relative in discovery.task_runners:
        path = Path(relative)
        suffix = path.suffix.casefold()
        if suffix == ".py":
            invocations.update({f"python {relative}", f"python3 {relative}"})
        elif suffix == ".sh":
            invocations.update({f"bash {relative}", f"sh {relative}", f"./{relative}"})
        elif suffix == ".ps1":
            invocations.update({f"pwsh {relative}", f"powershell {relative}"})
        elif not suffix and relative.startswith("bin/"):
            invocations.update({relative, f"./{relative}"})
    return invocations


def _known_gate_commands(root: Path, discovery: Discovery) -> tuple[set[str], list[AuditFinding]]:
    sources = tuple(sorted(set((*discovery.ci_files, *discovery.task_runners))))
    findings: list[AuditFinding] = []
    commands = _entrypoint_invocations(discovery)
    if len(sources) > MAX_GATE_FILES:
        findings.append(
            AuditFinding(
                root.as_posix(),
                "error",
                "evidence.too-many-gate-sources",
                1,
                f"Found {len(sources)} CI/task sources; maximum supported count is {MAX_GATE_FILES}.",
            )
        )
        return commands, findings

    total_bytes = 0
    for relative in sources:
        try:
            path = _confined_file(root, relative)
        except ValueError as error:
            findings.append(AuditFinding(relative, "error", "evidence.gate-source-unreadable", 1, str(error)))
            continue
        result = read_utf8_bounded(path, max_bytes=MAX_GATE_FILE_BYTES)
        if result.code is not None or result.text is None:
            findings.append(
                AuditFinding(
                    relative,
                    "error",
                    "evidence.gate-source-unreadable",
                    1,
                    result.message or result.code or "unreadable gate source",
                )
            )
            continue
        total_bytes += result.byte_count
        if total_bytes > MAX_GATE_TOTAL_BYTES:
            findings.append(
                AuditFinding(
                    root.as_posix(),
                    "error",
                    "evidence.gate-sources-too-large",
                    1,
                    f"CI/task source aggregate exceeds {MAX_GATE_TOTAL_BYTES} bytes.",
                )
            )
            break
        commands.update(_extract_gate_invocations(relative, result.text))
    return commands, findings


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


def _command_reference_status(root: Path, command: str, known_commands: set[str]) -> str:
    """Classify static command evidence without claiming execution."""
    normalized = _normalize_invocation(command)
    if normalized is not None and normalized in known_commands:
        return "located"
    for token in _command_path_tokens(command):
        try:
            _confined_file(root, token)
        except ValueError:
            continue
        return "unverified"
    return "unlocated"


def _convert(finding: Finding) -> AuditFinding:
    return AuditFinding(finding.path, finding.severity, finding.code, finding.line, finding.message)


def audit(
    root: Path,
    profile: str = "application",
    layout: LayoutName | None = None,
    language: LanguageName = "en",
) -> tuple[Discovery, list[AuditFinding]]:
    """Audit root and nested instructions using only static, repository-confined reads."""
    domain_profile, selected_layout = normalize_selection(profile, layout)
    discovery = discover(root)
    safe_root = Path(discovery.root)
    findings: list[AuditFinding] = [
        AuditFinding(safe_root.as_posix(), "error", "discovery.incomplete", 1, issue) for issue in discovery.issues
    ]

    for relative in discovery.symlinks:
        if Path(relative).name == "AGENTS.md":
            findings.append(
                AuditFinding(
                    relative,
                    "error",
                    "security.symlink-agents",
                    1,
                    "AGENTS.md must be a regular in-repository file.",
                )
            )

    paths = [safe_root / relative for relative in discovery.agent_files]
    validation_findings, documents = validate_many_with_documents(
        paths, domain_profile, safe_root, selected_layout, language
    )
    findings.extend(_convert(item) for item in validation_findings)
    texts = {document.relative_path: document.text for document in documents}

    reference_paragraphs: dict[str, tuple[str, int]] = {}
    for reference in ("README.md", "CHANGELOG.md"):
        if reference not in discovery.files:
            continue
        try:
            for paragraph, paragraph_line in _paragraphs(_read_text(safe_root, reference)).items():
                reference_paragraphs.setdefault(paragraph, (reference, paragraph_line))
        except ValueError:
            continue

    known_commands, gate_findings = _known_gate_commands(safe_root, discovery)
    findings.extend(gate_findings)
    for relative, text in texts.items():
        for paragraph, line_number in _paragraphs(text).items():
            source = reference_paragraphs.get(paragraph)
            if source:
                findings.append(
                    AuditFinding(
                        relative,
                        "warning",
                        "content.documentation-duplication",
                        line_number,
                        f"Instruction text duplicates {source[0]} instead of routing to its owner.",
                    )
                )

        visible, _ = parse_visible_lines(text)
        for line_number, line in visible:
            if LINT_LEAKAGE.search(line):
                findings.append(
                    AuditFinding(
                        relative,
                        "warning",
                        "content.lint-leakage",
                        line_number,
                        (
                            "Keep formatter and linter configuration executable; "
                            "document only a non-obvious repository exception."
                        ),
                    )
                )
            if not FULL_GATE_LINE.search(line):
                continue
            for command in CODE_SPAN.findall(line):
                status = _command_reference_status(safe_root, command, known_commands)
                if status == "unlocated":
                    findings.append(
                        AuditFinding(
                            relative,
                            "error",
                            "commands.unlocated-full-gate",
                            line_number,
                            (
                                "Completion command could not be located in discovered CI "
                                f"or repository task runners: {command}"
                            ),
                        )
                    )
                elif status == "unverified":
                    findings.append(
                        AuditFinding(
                            relative,
                            "warning",
                            "commands.unverified-full-gate",
                            line_number,
                            f"A referenced path exists, but the exact completion invocation was not located: {command}",
                        )
                    )

    ordered = sorted(findings, key=lambda item: (item.path, item.line, item.severity, item.code, item.message))
    return discovery, ordered


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd())
    parser.add_argument(
        "--profile",
        choices=("router", "application", "monorepo", "mcp-server", "safety-critical"),
        default="application",
        help="domain profile; legacy monorepo maps to application plus monorepo layout",
    )
    parser.add_argument("--layout", choices=("single", "monorepo"), default=None)
    parser.add_argument("--language", choices=("en", "pl", "other"), default="en")
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    parser.add_argument("--format", choices=("json", "text"), default="text", dest="output_format")
    return parser


def _render_text(findings: Iterable[AuditFinding]) -> str:
    return "\n".join(f"{item.path}:{item.line}: {item.severity}: {item.code}: {item.message}" for item in findings)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        discovery, findings = audit(args.root, args.profile, args.layout, args.language)
    except ValueError as error:
        print(str(error))
        return 2
    if args.output_format == "json":
        print(
            json.dumps(
                {"discovery": asdict(discovery), "findings": [asdict(item) for item in findings]},
                indent=2,
                sort_keys=True,
            )
        )
    elif findings:
        print(_render_text(findings))
    else:
        print("AGENTS.md audit passed.")
    has_error = any(item.severity == "error" for item in findings)
    has_warning = any(item.severity == "warning" for item in findings)
    return 1 if has_error or (args.strict and has_warning) else 0


if __name__ == "__main__":
    raise SystemExit(main())
