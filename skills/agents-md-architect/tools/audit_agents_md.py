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

from discover_repository import Discovery, discover  # noqa: E402
from validate_agents_md import Finding, ProfileName, validate_path  # noqa: E402

Severity = Literal["error", "warning"]
CODE_SPAN = re.compile(r"`([^`\n]+)`")
LINT_LEAKAGE = re.compile(
    r"(?i)\b(?:line length|quote style|indent(?:ation)? width|ruff rule|eslint rule|prettier config|"
    r"formatter config|stylecop rule)\b"
)
POSITIVE_RULE = re.compile(r"(?i)\b(?:must|required|always|shall)\b")
NEGATIVE_RULE = re.compile(r"(?i)\b(?:must not|do not|never|forbidden|shall not)\b")
MODAL_WORDS = re.compile(r"(?i)\b(?:must not|do not|shall not|must|required|always|never|forbidden|shall)\b")
FULL_GATE_LINE = re.compile(r"(?i)\b(?:full gate|complete gate|completion check|hosted ci|ci gate)\b")


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


def _read_text(root: Path, relative: str) -> str:
    return _confined_file(root, relative).read_text(encoding="utf-8")


def _visible_lines(text: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    fence: str | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        marker = "```" if stripped.startswith("```") else "~~~" if stripped.startswith("~~~") else None
        if marker:
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            continue
        if fence is None:
            lines.append((number, line))
    return lines


def _paragraphs(text: str) -> dict[str, int]:
    result: dict[str, int] = {}
    block: list[str] = []
    start = 1
    for number, line in _visible_lines(text) + [(len(text.splitlines()) + 1, "")]:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            if not block:
                start = number
            block.append(stripped)
            continue
        if block:
            normalized = re.sub(r"[^a-z0-9]+", " ", " ".join(block).casefold()).strip()
            if len(normalized.split()) >= 12:
                result.setdefault(normalized, start)
            block = []
    return result


def _rule_signature(line: str) -> tuple[str, bool] | None:
    stripped = re.sub(r"^\s*[-*]\s+", "", line).strip()
    negative = bool(NEGATIVE_RULE.search(stripped))
    positive = bool(POSITIVE_RULE.search(stripped))
    if not negative and not positive:
        return None
    key = MODAL_WORDS.sub("", stripped.casefold())
    key = re.sub(r"[^a-z0-9]+", " ", key).strip()
    return (key, negative) if len(key.split()) >= 3 else None


def _known_gate_text(root: Path, discovery: Discovery) -> str:
    parts: list[str] = []
    for relative in (*discovery.ci_files, *discovery.task_runners):
        try:
            parts.append(_read_text(root, relative))
        except (UnicodeDecodeError, ValueError):
            continue
    return "\n".join(parts)


def _command_has_existing_path(root: Path, command: str) -> bool:
    for token in command.split():
        cleaned = token.strip("'\"()[]{};,:")
        if "/" not in cleaned and "\\" not in cleaned:
            continue
        candidate = Path(cleaned)
        if candidate.is_absolute() or ".." in candidate.parts:
            return False
        if (root / candidate).exists():
            return True
    return False


def _convert(finding: Finding) -> AuditFinding:
    return AuditFinding(finding.path, finding.severity, finding.code, finding.line, finding.message)


def audit(root: Path, profile: ProfileName = "application") -> tuple[Discovery, list[AuditFinding]]:
    """Audit root and nested instructions using only static, repository-confined reads."""
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

    texts: dict[str, str] = {}
    for relative in discovery.agent_files:
        try:
            text = _read_text(safe_root, relative)
        except (UnicodeDecodeError, ValueError) as error:
            findings.append(AuditFinding(relative, "error", "security.unreadable", 1, str(error)))
            continue
        texts[relative] = text
        findings.extend(_convert(item) for item in validate_path(safe_root / relative, profile, safe_root))

    root_text = texts.get("AGENTS.md")
    reference_paragraphs: dict[str, tuple[str, int]] = {}
    for reference in ("README.md", "CHANGELOG.md"):
        if reference not in discovery.files:
            continue
        try:
            for paragraph, paragraph_line in _paragraphs(_read_text(safe_root, reference)).items():
                reference_paragraphs.setdefault(paragraph, (reference, paragraph_line))
        except (UnicodeDecodeError, ValueError):
            continue

    gate_text = _known_gate_text(safe_root, discovery)
    root_rules: dict[str, tuple[bool, int]] = {}
    if root_text:
        for line_number, line in _visible_lines(root_text):
            signature = _rule_signature(line)
            if signature:
                root_rules.setdefault(signature[0], (signature[1], line_number))

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

        for line_number, line in _visible_lines(text):
            if LINT_LEAKAGE.search(line):
                findings.append(
                    AuditFinding(
                        relative,
                        "warning",
                        "content.lint-leakage",
                        line_number,
                        (
                            "Keep formatter and linter configuration executable; document only a non-obvious "
                            "repository exception."
                        ),
                    )
                )
            if FULL_GATE_LINE.search(line):
                for command in CODE_SPAN.findall(line):
                    if command not in gate_text and not _command_has_existing_path(safe_root, command):
                        findings.append(
                            AuditFinding(
                                relative,
                                "error",
                                "commands.unverified-full-gate",
                                line_number,
                                f"Claimed completion command is not backed by discovered CI or a repository path: {command}",
                            )
                        )

            if relative == "AGENTS.md":
                continue
            signature = _rule_signature(line)
            if not signature:
                continue
            inherited = root_rules.get(signature[0])
            if inherited and inherited[0] != signature[1]:
                findings.append(
                    AuditFinding(
                        relative,
                        "error",
                        "nested.conflict",
                        line_number,
                        f"Local rule conflicts with root AGENTS.md line {inherited[1]}.",
                    )
                )
            elif inherited:
                findings.append(
                    AuditFinding(
                        relative,
                        "warning",
                        "nested.duplicate-inherited-rule",
                        line_number,
                        f"Local rule duplicates root AGENTS.md line {inherited[1]}; keep only the local difference.",
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
    )
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    parser.add_argument("--format", choices=("json", "text"), default="text", dest="output_format")
    return parser


def _render_text(findings: Iterable[AuditFinding]) -> str:
    return "\n".join(f"{item.path}:{item.line}: {item.severity}: {item.code}: {item.message}" for item in findings)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        discovery, findings = audit(args.root, args.profile)
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
