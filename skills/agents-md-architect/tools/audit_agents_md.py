#!/usr/bin/env python3
"""Audit AGENTS.md instruction trees without executing repository-controlled commands."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from agents_md_parse import parse_visible_lines, read_utf8_bounded  # noqa: E402
from agents_md_types import LanguageName, LayoutName  # noqa: E402
from discover_repository import Discovery, discover  # noqa: E402
from validate_agents_md import Finding, normalize_selection, validate_many  # noqa: E402

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
    path = root / relative
    if path.is_symlink():
        raise ValueError(f"refusing to read symlink: {relative}")
    resolved = path.resolve(strict=True)
    resolved.relative_to(root)
    if not resolved.is_file():
        raise ValueError(f"not a regular file: {relative}")
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


def _known_gate_text(root: Path, discovery: Discovery) -> str:
    parts: list[str] = []
    for relative in (*discovery.ci_files, *discovery.task_runners):
        try:
            parts.append(_read_text(root, relative))
        except ValueError:
            continue
    return "\n".join(parts)


def _command_path_tokens(command: str) -> tuple[str, ...]:
    paths: list[str] = []
    for token in command.split():
        cleaned = token.strip("'\"()[]{};,:")
        if "/" not in cleaned and "\\" not in cleaned:
            continue
        candidate = Path(cleaned)
        if candidate.is_absolute() or ".." in candidate.parts:
            continue
        paths.append(candidate.as_posix())
    return tuple(paths)


def _command_reference_status(root: Path, command: str, discovery: Discovery, gate_text: str) -> str:
    """Classify static command evidence without claiming execution."""
    normalized = " ".join(command.split())
    normalized_gate = " ".join(gate_text.split())
    if normalized and normalized in normalized_gate:
        return "located"
    known_entrypoints = set(discovery.task_runners) | set(discovery.ci_files)
    path_tokens = _command_path_tokens(command)
    command_tokens = command.split()
    for token in path_tokens:
        if token not in known_entrypoints:
            continue
        try:
            position = next(index for index, value in enumerate(command_tokens) if token in value)
        except StopIteration:
            continue
        if position == len(command_tokens) - 1:
            return "located"
    if any((root / token).is_file() for token in path_tokens):
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
    findings: list[AuditFinding] = []

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
    findings.extend(
        _convert(item) for item in validate_many(paths, domain_profile, safe_root, selected_layout, language)
    )

    texts: dict[str, str] = {}
    for relative in discovery.agent_files:
        try:
            texts[relative] = _read_text(safe_root, relative)
        except ValueError as error:
            findings.append(AuditFinding(relative, "error", "security.unreadable", 1, str(error)))

    reference_paragraphs: dict[str, tuple[str, int]] = {}
    for reference in ("README.md", "CHANGELOG.md"):
        if reference not in discovery.files:
            continue
        try:
            for paragraph, paragraph_line in _paragraphs(_read_text(safe_root, reference)).items():
                reference_paragraphs.setdefault(paragraph, (reference, paragraph_line))
        except ValueError:
            continue

    gate_text = _known_gate_text(safe_root, discovery)
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
                status = _command_reference_status(safe_root, command, discovery, gate_text)
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
