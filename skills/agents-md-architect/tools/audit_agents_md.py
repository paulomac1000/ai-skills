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
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

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
BindingKind = Literal["subprocess-module", "os-module", "subprocess-function", "os-system", "other"]
CODE_SPAN = re.compile(r"`([^`\n]+)`")
LINT_LEAKAGE = re.compile(
    r"(?i)\b(?:line length|quote style|indent(?:ation)? width|ruff rule|eslint rule|prettier config|"
    r"formatter config|stylecop rule)\b"
)
FULL_GATE_LINE = re.compile(
    r"(?i)\b(?:full gate|complete gate|completion check|hosted ci|ci gate|pełna bramka|pełny gate)\b"
)
INVALID_YAML_MESSAGE = "YAML source is syntactically invalid and cannot establish command evidence."
SUBPROCESS_CALLS = frozenset({"run", "call", "check_call", "check_output", "Popen"})


@dataclass(frozen=True)
class AuditFinding:
    """One repository-level instruction audit result."""

    path: str
    severity: Severity
    code: str
    line: int
    message: str


@dataclass
class _PythonScope:
    """Lexical Python bindings used to prove process execution conservatively."""

    parent: _PythonScope | None = None
    bindings: dict[str, BindingKind] = field(default_factory=dict)

    def clone(self) -> _PythonScope:
        return _PythonScope(self.parent, dict(self.bindings))

    def resolve(self, name: str) -> BindingKind | None:
        if name in self.bindings:
            return self.bindings[name]
        return self.parent.resolve(name) if self.parent is not None else None


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


def _bound_names(target: ast.AST) -> set[str]:
    names: set[str] = set()
    if isinstance(target, ast.Name):
        names.add(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for item in target.elts:
            names.update(_bound_names(item))
    elif isinstance(target, ast.Starred):
        names.update(_bound_names(target.value))
    return names


def _function_local_names(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda) -> set[str]:
    names = {argument.arg for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)}
    if node.args.vararg is not None:
        names.add(node.args.vararg.arg)
    if node.args.kwarg is not None:
        names.add(node.args.kwarg.arg)
    body: list[ast.stmt] = list(node.body) if not isinstance(node, ast.Lambda) else []

    class Collector(ast.NodeVisitor):
        def visit_FunctionDef(self, child: ast.FunctionDef) -> None:
            names.add(child.name)

        def visit_AsyncFunctionDef(self, child: ast.AsyncFunctionDef) -> None:
            names.add(child.name)

        def visit_ClassDef(self, child: ast.ClassDef) -> None:
            names.add(child.name)

        def visit_Lambda(self, child: ast.Lambda) -> None:
            return

        def visit_Name(self, child: ast.Name) -> None:
            if isinstance(child.ctx, (ast.Store, ast.Del)):
                names.add(child.id)

        def visit_Import(self, child: ast.Import) -> None:
            for alias in child.names:
                names.add(alias.asname or alias.name.split(".", 1)[0])

        def visit_ImportFrom(self, child: ast.ImportFrom) -> None:
            for alias in child.names:
                if alias.name != "*":
                    names.add(alias.asname or alias.name)

        def visit_Global(self, child: ast.Global) -> None:
            names.difference_update(child.names)

        def visit_Nonlocal(self, child: ast.Nonlocal) -> None:
            names.difference_update(child.names)

    collector = Collector()
    for statement in body:
        collector.visit(statement)
    return names


class _PythonInvocationVisitor:
    def __init__(self) -> None:
        self.invocations: set[str] = set()

    def process_statements(self, statements: Sequence[ast.stmt], scope: _PythonScope) -> None:
        for statement in statements:
            self.process_statement(statement, scope)

    def process_statement(self, node: ast.stmt, scope: _PythonScope) -> None:
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".", 1)[0]
                kind: BindingKind = "other"
                if alias.name == "subprocess":
                    kind = "subprocess-module"
                elif alias.name == "os":
                    kind = "os-module"
                scope.bindings[local] = kind
            return
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue
                local = alias.asname or alias.name
                kind: BindingKind = "other"
                if node.module == "subprocess" and alias.name in SUBPROCESS_CALLS:
                    kind = "subprocess-function"
                elif node.module == "os" and alias.name == "system":
                    kind = "os-system"
                scope.bindings[local] = kind
            return
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                self.process_expression(decorator, scope)
            for default in (*node.args.defaults, *node.args.kw_defaults):
                if default is not None:
                    self.process_expression(default, scope)
            scope.bindings[node.name] = "other"
            child = _PythonScope(scope)
            child.bindings.update({name: "other" for name in _function_local_names(node)})
            self.process_statements(node.body, child)
            return
        if isinstance(node, ast.ClassDef):
            for item in (*node.decorator_list, *node.bases, *node.keywords):
                expression = item.value if isinstance(item, ast.keyword) else item
                self.process_expression(expression, scope)
            scope.bindings[node.name] = "other"
            self.process_statements(node.body, _PythonScope(scope))
            return
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
            value = getattr(node, "value", None)
            if isinstance(value, ast.AST):
                self.process_expression(value, scope)
            targets: list[ast.AST] = []
            if isinstance(node, ast.Assign):
                targets.extend(node.targets)
            else:
                target = getattr(node, "target", None)
                if isinstance(target, ast.AST):
                    targets.append(target)
            for target in targets:
                for name in _bound_names(target):
                    scope.bindings[name] = "other"
            return
        if isinstance(node, (ast.For, ast.AsyncFor)):
            self.process_expression(node.iter, scope)
            branch = scope.clone()
            for name in _bound_names(node.target):
                branch.bindings[name] = "other"
            self.process_statements(node.body, branch)
            self.process_statements(node.orelse, scope.clone())
            return
        if isinstance(node, (ast.With, ast.AsyncWith)):
            branch = scope.clone()
            for item in node.items:
                self.process_expression(item.context_expr, scope)
                if item.optional_vars is not None:
                    for name in _bound_names(item.optional_vars):
                        branch.bindings[name] = "other"
            self.process_statements(node.body, branch)
            return
        if isinstance(node, ast.If):
            self.process_expression(node.test, scope)
            self.process_statements(node.body, scope.clone())
            self.process_statements(node.orelse, scope.clone())
            return
        if isinstance(node, (ast.Try, ast.TryStar)):
            self.process_statements(node.body, scope.clone())
            for handler in node.handlers:
                branch = scope.clone()
                if handler.name:
                    branch.bindings[handler.name] = "other"
                if handler.type is not None:
                    self.process_expression(handler.type, scope)
                self.process_statements(handler.body, branch)
            self.process_statements(node.orelse, scope.clone())
            self.process_statements(node.finalbody, scope.clone())
            return
        if isinstance(node, ast.While):
            self.process_expression(node.test, scope)
            self.process_statements(node.body, scope.clone())
            self.process_statements(node.orelse, scope.clone())
            return
        if isinstance(node, ast.Match):
            self.process_expression(node.subject, scope)
            for case in node.cases:
                branch = scope.clone()
                if case.guard is not None:
                    self.process_expression(case.guard, branch)
                self.process_statements(case.body, branch)
            return
        if isinstance(node, ast.Expr):
            self.process_expression(node.value, scope)
            return
        if isinstance(node, ast.Return) and node.value is not None:
            self.process_expression(node.value, scope)
            return
        if isinstance(node, ast.Raise):
            if node.exc is not None:
                self.process_expression(node.exc, scope)
            if node.cause is not None:
                self.process_expression(node.cause, scope)
            return
        if isinstance(node, ast.Assert):
            self.process_expression(node.test, scope)
            if node.msg is not None:
                self.process_expression(node.msg, scope)
            return
        if isinstance(node, ast.Delete):
            for target in node.targets:
                for name in _bound_names(target):
                    scope.bindings[name] = "other"

    def process_expression(self, node: ast.AST, scope: _PythonScope) -> None:
        if isinstance(node, ast.Call):
            self._process_call(node, scope)
        elif isinstance(node, ast.Lambda):
            child = _PythonScope(scope)
            child.bindings.update({name: "other" for name in _function_local_names(node)})
            self.process_expression(node.body, child)
            return
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.expr) and not isinstance(node, ast.Lambda):
                self.process_expression(child, scope)

    def _process_call(self, node: ast.Call, scope: _PythonScope) -> None:
        accepted = False
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            owner = scope.resolve(node.func.value.id)
            accepted = (owner == "subprocess-module" and node.func.attr in SUBPROCESS_CALLS) or (
                owner == "os-module" and node.func.attr == "system"
            )
        elif isinstance(node.func, ast.Name):
            accepted = scope.resolve(node.func.id) in {"subprocess-function", "os-system"}
        if not accepted:
            return
        argument = node.args[0] if node.args else next(
            (keyword.value for keyword in node.keywords if keyword.arg in {"args", "command"}), None
        )
        if argument is None:
            return
        command = _literal_python_command(argument)
        if command is not None:
            _add_command_segments(self.invocations, command)


def _extract_python_invocations(text: str) -> set[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    visitor = _PythonInvocationVisitor()
    visitor.process_statements(tree.body, _PythonScope())
    return visitor.invocations


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
        if Path(relative).suffix.casefold() in {".yml", ".yaml"}:
            syntax_error = _yaml_syntax_error(result.text)
            if syntax_error is not None:
                findings.append(AuditFinding(relative, "error", "evidence.invalid-yaml", 1, syntax_error))
                continue
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
                AuditFinding(relative, "error", "security.symlink-agents", 1, "AGENTS.md must be a regular in-repository file.")
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
                        "Keep formatter and linter configuration executable; document only a non-obvious repository exception.",
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
                            "Completion command could not be located in discovered CI or repository task runners: " + command,
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
        print(json.dumps({"discovery": asdict(discovery), "findings": [asdict(item) for item in findings]}, indent=2, sort_keys=True))
    elif findings:
        print(_render_text(findings))
    else:
        print("AGENTS.md audit passed.")
    has_error = any(item.severity == "error" for item in findings)
    has_warning = any(item.severity == "warning" for item in findings)
    return 1 if has_error or (args.strict and has_warning) else 0


if __name__ == "__main__":
    raise SystemExit(main())
