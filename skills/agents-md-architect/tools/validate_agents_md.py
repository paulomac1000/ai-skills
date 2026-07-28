#!/usr/bin/env python3
"""Validate AGENTS.md files for structure, scope, routing, and common instruction smells."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import unquote

Severity = Literal["error", "warning"]
ProfileName = Literal["router", "application", "monorepo", "mcp-server", "safety-critical"]

FENCE = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>`{3,}|~{3,})")
HEADING = re.compile(r"^(?P<level>#{1,6})\s+(?P<title>.+?)\s*$")
INLINE_LINK = re.compile(r"(?<!!)\[[^\]\n]+\]\((?P<target>[^)\n]+)\)")
REFERENCE_DEFINITION = re.compile(r"^[ ]{0,3}\[(?P<label>[^\]\n]+)\]:\s*(?P<target>\S+)", re.M)
REFERENCE_USAGE = re.compile(r"(?<!!)\[(?P<label>[^\]\n]+)\]\[(?P<ref>[^\]\n]*)\]")
BARE_REFERENCE = re.compile(r"^\s*[-*]\s+(?:\[[^\]]+\]\([^)]+\)|`[^`]+`)\s*[.;]?\s*$")
VERSIONED_NAME = re.compile(
    r"(?i)(?:agents|implementation|workflow|config|architecture|standard|current)"
    r"[-_ ]?v\d+\b|\b(?:final|new)[-_ ]?v?\d+\b"
)
VOLATILE_COUNT = re.compile(r"(?i)\b\d+\s+(?:tests?|tools?|modules?|files?|services?|workflows?|agents?)\b")
ABSOLUTE_HOST_PATH = re.compile(r"(?:/var/apps/|/home/[A-Za-z0-9_.-]+/|[A-Za-z]:\\Users\\)")
PLACEHOLDER = re.compile(r"REPLACE_WITH|<command>|<path>|<owner>|TODO(?:\([^)]*\))?:", re.I)
FALSE_CI_GUARANTEE = re.compile(
    r"(?i)(?:if|when).{0,40}(?:local|pre-commit|hook).{0,40}(?:pass|green).{0,40}CI.{0,20}(?:pass|green|guaranteed)"
)
GENERIC_ADVICE = re.compile(
    r"(?i)\b(?:write clean code|follow best practices|use meaningful names|be careful|keep it simple)\b"
)
KEYWORD_APPROVAL = re.compile(
    r"(?i)CONSENT_KEYWORDS|has_user_consent|approval_keywords|keyword.{0,20}(?:consent|approval)"
)
CHANGELOG_HEADING = re.compile(r"(?i)^#{1,6}\s+(?:change\s*log|changelog|history)\s*$")

PROFILE_LIMITS: dict[ProfileName, tuple[int, int]] = {
    "router": (60, 100),
    "application": (120, 180),
    "monorepo": (150, 220),
    "mcp-server": (150, 220),
    "safety-critical": (180, 260),
}

CONCEPT_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "scope": (re.compile(r"\bscope\b", re.I), re.compile(r"\bappl(?:y|ies|icable)\b", re.I)),
    "precedence": (
        re.compile(r"\bprecedence\b", re.I),
        re.compile(r"\binherit(?:ed|ance)?\b", re.I),
        re.compile(r"\bnested\s+AGENTS\.md\b", re.I),
    ),
    "routing": (
        re.compile(r"\broute|routing\b", re.I),
        re.compile(r"\bwhen\s+(?:changing|editing|working|adding|updating)\b", re.I),
        re.compile(r"\bworkflow\b", re.I),
    ),
    "commands": (
        re.compile(r"\bcommands?\b", re.I),
        re.compile(r"\bbuild\b", re.I),
        re.compile(r"\btests?\b", re.I),
        re.compile(r"\bverification\b", re.I),
    ),
    "completion": (
        re.compile(r"definition of done", re.I),
        re.compile(r"\bcompletion\b", re.I),
        re.compile(r"before (?:reporting|completion|finishing)", re.I),
    ),
    "safety": (
        re.compile(r"\bsafety\b", re.I),
        re.compile(r"\bsecurity\b", re.I),
        re.compile(r"\bforbidden\b", re.I),
        re.compile(r"\bdestructive\b", re.I),
    ),
    "data": (
        re.compile(r"\bdata boundar(?:y|ies)\b", re.I),
        re.compile(r"\bsensitive data\b", re.I),
        re.compile(r"\bprivate data\b", re.I),
        re.compile(r"\bsecrets?\b", re.I),
    ),
    "nested": (
        re.compile(r"\bnested\b", re.I),
        re.compile(r"\bsubtree\b", re.I),
        re.compile(r"\bpath-scoped\b", re.I),
        re.compile(r"\blocal differences\b", re.I),
    ),
    "risk": (
        re.compile(r"\brisk\b", re.I),
        re.compile(r"\bread-only\b", re.I),
        re.compile(r"\bwrite\b", re.I),
        re.compile(r"\bside effects?\b", re.I),
    ),
}

PROFILE_REQUIREMENTS: dict[ProfileName, tuple[str, ...]] = {
    "router": ("scope", "routing", "completion"),
    "application": ("scope", "commands", "completion"),
    "monorepo": ("scope", "precedence", "nested", "commands", "completion"),
    "mcp-server": ("scope", "commands", "safety", "risk", "completion"),
    "safety-critical": ("scope", "commands", "safety", "data", "completion"),
}


@dataclass(frozen=True)
class Finding:
    """One validation result associated with a source line."""

    path: str
    severity: Severity
    code: str
    line: int
    message: str


def _normalize_heading(value: str) -> str:
    normalized = re.sub(r"[`*_~]", "", value.casefold())
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")


def _strip_destination(raw: str) -> str:
    value = raw.strip()
    if value.startswith("<") and ">" in value:
        return value[1 : value.index(">")]
    return value.split(maxsplit=1)[0]


def _is_external(target: str) -> bool:
    lowered = target.casefold()
    return lowered.startswith(("http://", "https://", "mailto:", "tel:", "data:"))


def _iter_source_lines(text: str) -> Iterator[tuple[int, str]]:
    """Yield non-fenced lines with 1-based source line numbers."""
    fence_character: str | None = None
    minimum_length = 0
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if fence_character is None:
            match = FENCE.match(line)
            if match and len(match.group("indent").expandtabs(4)) <= 3:
                marker = match.group("marker")
                fence_character = marker[0]
                minimum_length = len(marker)
                continue
            yield line_number, line
            continue

        closing = re.fullmatch(rf"{re.escape(fence_character)}{{{minimum_length},}}[ \t]*", stripped)
        if closing:
            fence_character = None
            minimum_length = 0


def _iter_links(text: str) -> Iterator[tuple[int, str]]:
    definitions: dict[str, str] = {}
    for match in REFERENCE_DEFINITION.finditer(text):
        definitions[match.group("label").casefold()] = _strip_destination(match.group("target"))

    for line_number, line in _iter_source_lines(text):
        for match in INLINE_LINK.finditer(line):
            yield line_number, _strip_destination(match.group("target"))
        for match in REFERENCE_USAGE.finditer(line):
            key = (match.group("ref") or match.group("label")).casefold()
            target = definitions.get(key)
            if target:
                yield line_number, target


def _has_concept(text: str, concept: str) -> bool:
    return any(pattern.search(text) for pattern in CONCEPT_PATTERNS[concept])


def _resolve_target(path: Path, repository_root: Path, target: str) -> Path | None:
    clean = unquote(target.split("#", 1)[0]).strip()
    if not clean or clean.startswith("#") or _is_external(clean):
        return None
    candidate = Path(clean)
    if candidate.is_absolute():
        return candidate
    return (path.parent / candidate).resolve(strict=False)


def validate_path(path: Path, profile: ProfileName, repository_root: Path | None = None) -> list[Finding]:
    """Validate one AGENTS.md file and return deterministic findings."""
    findings: list[Finding] = []
    if not path.is_file():
        return [Finding(str(path), "error", "input.missing", 1, "Input file does not exist.")]

    text = path.read_text(encoding="utf-8")
    root = (repository_root or path.parent).resolve(strict=False)
    visible_lines = list(_iter_source_lines(text))
    visible_text = "\n".join(line for _, line in visible_lines)
    headings: list[tuple[int, int, str]] = []
    for line_number, line in visible_lines:
        match = HEADING.fullmatch(line)
        if match:
            headings.append((line_number, len(match.group("level")), match.group("title")))

    h1 = [(line, title) for line, level, title in headings if level == 1]
    if len(h1) != 1:
        findings.append(
            Finding(str(path), "error", "structure.h1", 1, f"Expected exactly one H1 heading, found {len(h1)}.")
        )

    seen: dict[tuple[int, str], int] = {}
    for line_number, level, title in headings:
        key = (level, _normalize_heading(title))
        if key in seen:
            findings.append(
                Finding(
                    str(path),
                    "error",
                    "structure.duplicate-heading",
                    line_number,
                    f"Heading duplicates line {seen[key]} after normalization: {title}",
                )
            )
        else:
            seen[key] = line_number
        if CHANGELOG_HEADING.fullmatch("#" * level + " " + title):
            findings.append(
                Finding(str(path), "error", "content.changelog", line_number, "Move change history to CHANGELOG.md.")
            )

    recommended, hard = PROFILE_LIMITS[profile]
    line_count = len(text.splitlines())
    if line_count > hard:
        findings.append(
            Finding(
                str(path),
                "error",
                "context.hard-limit",
                1,
                f"{profile} profile has {line_count} lines; decompose or justify a maximum of {hard}.",
            )
        )
    elif line_count > recommended:
        findings.append(
            Finding(
                str(path),
                "warning",
                "context.review-limit",
                1,
                (
                    f"{profile} profile has {line_count} lines; review whether task-specific detail "
                    "should be routed elsewhere."
                ),
            )
        )

    for concept in PROFILE_REQUIREMENTS[profile]:
        if not _has_concept(visible_text, concept):
            findings.append(
                Finding(
                    str(path),
                    "error",
                    f"profile.missing-{concept}",
                    1,
                    f"The {profile} profile requires an explicit {concept.replace('-', ' ')} contract.",
                )
            )

    for line_number, line in visible_lines:
        checks: tuple[tuple[re.Pattern[str], Severity, str, str], ...] = (
            (
                BARE_REFERENCE,
                "warning",
                "routing.blind-reference",
                "Explain when this reference is used and what decision it owns.",
            ),
            (
                VERSIONED_NAME,
                "warning",
                "ownership.versioned-current-name",
                "Review whether this versioned current name is a bounded compatibility contract or migration residue.",
            ),
            (
                VOLATILE_COUNT,
                "warning",
                "content.volatile-count",
                "Move volatile counts to generated output or release evidence.",
            ),
            (
                ABSOLUTE_HOST_PATH,
                "warning",
                "portability.absolute-host-path",
                "Replace host-specific absolute paths with repository-relative or parameterized paths.",
            ),
            (
                PLACEHOLDER,
                "error",
                "content.placeholder",
                "Replace template placeholders before publishing AGENTS.md.",
            ),
            (
                FALSE_CI_GUARANTEE,
                "error",
                "evidence.false-ci-guarantee",
                "Local validation must not be described as a guarantee of hosted CI.",
            ),
            (
                GENERIC_ADVICE,
                "warning",
                "content.generic-advice",
                "Replace generic advice with a repository-specific command, invariant, or boundary.",
            ),
            (
                KEYWORD_APPROVAL,
                "error",
                "safety.keyword-approval",
                "Keyword matching is not a trusted human-approval mechanism.",
            ),
        )
        for pattern, severity, code, message in checks:
            if pattern.search(line):
                findings.append(Finding(str(path), severity, code, line_number, message))

    for line_number, target in _iter_links(text):
        resolved = _resolve_target(path, root, target)
        if resolved is None or _is_external(target):
            continue
        try:
            resolved.relative_to(root)
        except ValueError:
            findings.append(
                Finding(
                    str(path),
                    "error",
                    "links.outside-repository",
                    line_number,
                    f"Relative reference escapes the repository boundary: {target}",
                )
            )
            continue
        if not resolved.exists():
            findings.append(
                Finding(str(path), "error", "links.missing", line_number, f"Referenced path does not exist: {target}")
            )

    return sorted(findings, key=lambda item: (item.path, item.line, item.severity, item.code, item.message))


def validate_many(
    paths: Iterable[Path], profile: ProfileName, repository_root: Path | None = None
) -> list[Finding]:
    """Validate multiple files in deterministic order."""
    findings: list[Finding] = []
    for path in sorted(paths):
        findings.extend(validate_path(path, profile, repository_root))
    return findings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="AGENTS.md files to validate")
    parser.add_argument(
        "--profile",
        choices=tuple(PROFILE_REQUIREMENTS),
        default="application",
        help="instruction profile applied to all selected files",
    )
    parser.add_argument("--repository-root", type=Path, help="root used to confine and resolve relative links")
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    parser.add_argument("--format", choices=("text", "json"), default="text", dest="output_format")
    return parser


def _render_text(findings: Sequence[Finding]) -> str:
    return "\n".join(
        f"{item.path}:{item.line}: {item.severity}: {item.code}: {item.message}" for item in findings
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line validator and return a process exit code."""
    args = _parser().parse_args(argv)
    profile = args.profile
    assert profile in PROFILE_REQUIREMENTS
    findings = validate_many(args.paths, profile, args.repository_root)
    if args.output_format == "json":
        print(json.dumps([asdict(item) for item in findings], indent=2, sort_keys=True))
    elif findings:
        print(_render_text(findings))
    else:
        print("AGENTS.md validation passed.")
    has_error = any(item.severity == "error" for item in findings)
    has_warning = any(item.severity == "warning" for item in findings)
    return 1 if has_error or (args.strict and has_warning) else 0


if __name__ == "__main__":
    raise SystemExit(main())
