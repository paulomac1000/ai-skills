"""Structured completion-gate and public task-runner evidence extraction."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from pathlib import Path

import yaml
from agents_md_parse import parse_visible_lines
from agents_md_types import HEADING, CommandRule, _normalize_rule

_CODE_SPAN = re.compile(r"`([^`\n]+)`")
_COMPLETION_LABEL = re.compile(
    r"(?ix)\b(?:"
    r"full(?:\s+completion)?\s+gate|"
    r"complete\s+gate|"
    r"completion\s+(?:gate|check)|"
    r"hosted\s+ci|ci\s+gate|"
    r"pełn(?:a|y)\s+(?:bramka|gate|weryfikacja)|"
    r"bramka\s+(?:ukończenia|zakończenia)|"
    r"pełn(?:a|y)\s+test"
    r")\b"
)
_LABEL_LINE = re.compile(r"^\s*(?:[-+*]\s+)?(?P<label>[^:|]{2,120})\s*:\s*(?P<tail>.*)$")
_FENCE = re.compile(r"^[ \t]{0,3}(?P<marker>`{3,}|~{3,})(?P<info>[^\r\n]*)$")
_LOCAL_CUE = re.compile(r"\b(?:local|subtree|override|lokaln\w*|poddrzew\w*|wyjątek)\b", re.I)
_MAKE_TARGET = re.compile(r"^(?P<targets>[A-Za-z0-9_.-]+(?:\s+[A-Za-z0-9_.-]+)*)\s*:(?!=)")
_JUST_RECIPE = re.compile(r"^@?(?P<name>[A-Za-z_][A-Za-z0-9_-]*)(?:\s+[^:=#][^:#]*)?:\s*(?:#.*)?$")


def _deduplicated_rules(values: Iterable[CommandRule]) -> tuple[CommandRule, ...]:
    seen: set[tuple[str, str]] = set()
    result: list[CommandRule] = []
    for value in values:
        key = (value.key, " ".join(value.command.split()))
        if not value.command.strip() or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return tuple(result)


def _rule(label: str, command: str, line: int, context: str = "") -> CommandRule:
    return CommandRule(
        key=_normalize_rule(label),
        command=command.strip(),
        line=line,
        explicit_local=bool(_LOCAL_CUE.search(label + " " + context)),
    )


def _table_cells(line: str) -> tuple[str, ...]:
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|")):
        return ()
    return tuple(cell.strip() for cell in stripped[1:-1].split("|"))


def _visible_completion_rules(text: str) -> list[CommandRule]:
    visible, _ = parse_visible_lines(text)
    rules: list[CommandRule] = []
    in_completion_section = False
    section_label = "full gate"
    pending_label: tuple[str, int] | None = None

    for line_number, line in visible:
        heading = HEADING.fullmatch(line)
        if heading is not None:
            title = heading.group("title")
            in_completion_section = _COMPLETION_LABEL.search(title) is not None
            section_label = title if in_completion_section else "full gate"
            pending_label = None
            continue

        cells = _table_cells(line)
        if cells:
            label_cell = next((cell for cell in cells if _COMPLETION_LABEL.search(cell)), None)
            if label_cell is not None:
                for cell in cells:
                    if cell == label_cell:
                        continue
                    for command in _CODE_SPAN.findall(cell):
                        rules.append(_rule(label_cell, command, line_number, line))
                continue

        label_match = _LABEL_LINE.fullmatch(line)
        if label_match is not None and _COMPLETION_LABEL.search(label_match.group("label")):
            label = label_match.group("label")
            commands = _CODE_SPAN.findall(label_match.group("tail"))
            if commands:
                rules.extend(_rule(label, command, line_number, line) for command in commands)
                pending_label = None
            else:
                pending_label = (label, line_number)
            continue

        if pending_label is not None:
            if not line.strip():
                continue
            commands = _CODE_SPAN.findall(line)
            if commands:
                label, _label_line = pending_label
                rules.extend(_rule(label, command, line_number, line) for command in commands)
                pending_label = None
                continue
            pending_label = None

        if in_completion_section:
            for command in _CODE_SPAN.findall(line):
                rules.append(_rule(section_label, command, line_number, line))

    return rules


def _logical_block_commands(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    commands: list[tuple[int, str]] = []
    current: list[str] = []
    start_line = 1
    for line_number, source in lines:
        value = source.strip()
        if not value or value.startswith("#"):
            continue
        if value.startswith(("$ ", "> ")):
            value = value[2:].lstrip()
        if not current:
            start_line = line_number
        if value.endswith("\\"):
            current.append(value[:-1].rstrip())
            continue
        current.append(value)
        commands.append((start_line, " ".join(current)))
        current = []
    if current:
        commands.append((start_line, " ".join(current)))
    return commands


def _fenced_completion_rules(text: str) -> list[CommandRule]:
    rules: list[CommandRule] = []
    in_completion_section = False
    section_label = "full gate"
    pending_label: tuple[str, int] | None = None
    fence_marker: str | None = None
    fence_label = "full gate"
    capture = False
    body: list[tuple[int, str]] = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        if fence_marker is not None:
            stripped = line.lstrip(" \t")
            if re.fullmatch(rf"{re.escape(fence_marker[0])}{{{len(fence_marker)},}}[ \t]*", stripped):
                if capture:
                    rules.extend(
                        _rule(fence_label, command, command_line, fence_label)
                        for command_line, command in _logical_block_commands(body)
                    )
                fence_marker = None
                capture = False
                body = []
                pending_label = None
            elif capture:
                body.append((line_number, line))
            continue

        heading = HEADING.fullmatch(line)
        if heading is not None:
            title = heading.group("title")
            in_completion_section = _COMPLETION_LABEL.search(title) is not None
            section_label = title if in_completion_section else "full gate"
            pending_label = None
            continue

        label_match = _LABEL_LINE.fullmatch(line)
        if label_match is not None and _COMPLETION_LABEL.search(label_match.group("label")):
            if not _CODE_SPAN.findall(label_match.group("tail")):
                pending_label = (label_match.group("label"), line_number)
            continue

        opener = _FENCE.fullmatch(line)
        if opener is not None:
            fence_marker = opener.group("marker")
            capture = in_completion_section or pending_label is not None
            fence_label = pending_label[0] if pending_label is not None else section_label
            body = []
            continue

        if pending_label is not None and line.strip() and not _CODE_SPAN.findall(line):
            pending_label = None

    return rules


def completion_command_rules(text: str) -> tuple[CommandRule, ...]:
    """Return completion commands from supported Markdown structures."""
    return _deduplicated_rules((*_visible_completion_rules(text), *_fenced_completion_rules(text)))


def _make_invocations(text: str) -> set[str]:
    commands: set[str] = set()
    for line in text.splitlines():
        if not line or line[0].isspace() or line.lstrip().startswith("#"):
            continue
        match = _MAKE_TARGET.match(line)
        if match is None:
            continue
        for target in match.group("targets").split():
            if target.startswith(".") or any(token in target for token in ("%", "$", "/")):
                continue
            commands.add(f"make {target}")
    return commands


def _just_invocations(text: str) -> set[str]:
    commands: set[str] = set()
    for line in text.splitlines():
        if not line or line[0].isspace() or line.lstrip().startswith(("#", "set ", "import ", "mod ")):
            continue
        match = _JUST_RECIPE.fullmatch(line)
        if match is not None:
            commands.add(f"just {match.group('name')}")
    return commands


def _taskfile_invocations(text: str) -> set[str]:
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError:
        return set()
    if not isinstance(document, dict) or not isinstance(document.get("tasks"), dict):
        return set()
    return {f"task {name}" for name in document["tasks"] if isinstance(name, str) and name.strip()}


def _package_invocations(text: str) -> set[str]:
    try:
        document = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return set()
    scripts = document.get("scripts") if isinstance(document, dict) else None
    if not isinstance(scripts, dict):
        return set()
    commands: set[str] = set()
    for name, value in scripts.items():
        if not isinstance(name, str) or not name.strip() or not isinstance(value, str):
            continue
        commands.update(
            {
                f"npm run {name}",
                f"pnpm run {name}",
                f"pnpm {name}",
                f"yarn {name}",
            }
        )
    return commands


def _msbuild_invocations(text: str) -> set[str]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return set()
    commands: set[str] = set()
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "Target":
            continue
        name = element.attrib.get("Name", "").strip()
        if name:
            commands.update({f"dotnet build -t:{name}", f"dotnet msbuild -t:{name}"})
    return commands


def public_task_invocations(relative: str, text: str) -> set[str]:
    """Return stable public commands exposed by a repository task-runner definition."""
    name = Path(relative).name
    folded = name.casefold()
    if folded == "makefile" or folded.endswith(".mk"):
        return _make_invocations(text)
    if folded == "justfile":
        return _just_invocations(text)
    if folded in {"taskfile.yml", "taskfile.yaml"}:
        return _taskfile_invocations(text)
    if folded == "package.json":
        return _package_invocations(text)
    if Path(relative).suffix.casefold() in {".csproj", ".fsproj", ".vbproj", ".targets", ".proj"}:
        return _msbuild_invocations(text)
    return set()
