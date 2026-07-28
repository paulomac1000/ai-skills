"""Shared models and lexical contracts for AGENTS.md validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


Severity = Literal["error", "warning"]
ProfileName = Literal["router", "application", "monorepo", "mcp-server", "safety-critical"]

HEADING = re.compile(r"^(?P<level>#{1,6})\s+(?P<title>.+?)\s*$")
FENCE_OPENER = re.compile(r"^(?P<indent>[ \t]{0,3})(?P<marker>`{3,}|~{3,})(?P<info>[^\r\n]*)$")
INLINE_LINK = re.compile(r"(?<!!)\[(?P<label>[^\]\n]+)\]\((?P<target>[^)\n]+)\)")
REFERENCE_DEFINITION = re.compile(r"^[ ]{0,3}\[(?P<label>[^\]\n]+)\]:\s*(?P<target>\S+)")
REFERENCE_USAGE = re.compile(r"(?<!!)\[(?P<label>[^\]\n]+)\]\[(?P<ref>[^\]\n]*)\]")
BARE_REFERENCE = re.compile(r"^\s*[-*]\s+(?:\[[^\]]+\]\([^)]+\)|`[^`]+`)\s*[.;]?\s*$")
VERSIONED_NAME = re.compile(
    r"(?i)(?:agents|implementation|workflow|config|architecture|standard|current)"
    r"[-_ ]?v\d+\b|\b(?:final|new)[-_ ]?v?\d+\b"
)
VOLATILE_COUNT = re.compile(r"(?i)\b\d+\s+(?:tests?|tools?|modules?|files?|services?|workflows?|agents?)\b")
ABSOLUTE_HOST_PATH = re.compile(r"(?:/var/apps/|/home/[A-Za-z0-9_.-]+/|[A-Za-z]:\\Users\\)")
PLACEHOLDER = re.compile(r"REPLACE_WITH|<command>|<path>|<owner>|TODO(?:\([^)]*\))?:", re.I)
GENERIC_ADVICE = re.compile(
    r"(?i)\b(?:write clean code|follow best practices|use meaningful names|be careful|keep it simple)\b"
)
KEYWORD_APPROVAL = re.compile(
    r"(?i)CONSENT_KEYWORDS|has_user_consent|approval_keywords|keyword.{0,20}(?:consent|approval)"
)
POSITIVE_CI_GUARANTEE = re.compile(
    r"(?i)(?:if|when).{0,45}(?:local|pre-commit|hook).{0,45}(?:pass|green).{0,45}"
    r"CI.{0,25}(?:will pass|passes|is guaranteed|guaranteed to pass)"
)
CHANGELOG_HEADING = re.compile(r"(?i)^#{1,6}\s+(?:change\s*log|changelog|history)\s*$")
CONTEXT_WAIVER = re.compile(
    r'<!--\s*agents-md:\s*waive\s+context-budget\s+reason="(?P<reason>[^"]+)"\s*-->', re.I
)
COMMAND_LINE = re.compile(r"^\s*[-*]\s*(?P<label>[^:]{2,80}):\s*`(?P<command>[^`]+)`\s*[.;]?\s*$")
NEGATIVE_DIRECTIVE = re.compile(r"\b(?:must not|do not|don't|never|forbidden|prohibited|may not|cannot)\b", re.I)
POSITIVE_DIRECTIVE = re.compile(r"\b(?:must|always|required|shall|may|allowed|permit(?:ted)?|edit directly)\b", re.I)

PROFILE_BUDGETS: dict[ProfileName, tuple[int, int]] = {
    "router": (60, 6_000),
    "application": (120, 12_000),
    "monorepo": (150, 16_000),
    "mcp-server": (150, 16_000),
    "safety-critical": (180, 20_000),
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
    "local": (
        re.compile(r"\blocal differences\b", re.I),
        re.compile(r"\bfor this subtree\b", re.I),
        re.compile(r"\blocal commands\b", re.I),
    ),
}

PROFILE_REQUIREMENTS: dict[ProfileName, tuple[str, ...]] = {
    "router": ("scope", "routing", "completion"),
    "application": ("scope", "commands", "completion"),
    "monorepo": ("scope", "precedence", "nested", "commands", "completion"),
    "mcp-server": ("scope", "commands", "safety", "risk", "completion"),
    "safety-critical": ("scope", "commands", "safety", "data", "completion"),
}
NESTED_MONOREPO_REQUIREMENTS = ("scope", "local", "commands", "completion")

PATH_SUFFIXES = {
    ".cs",
    ".csproj",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".yaml",
    ".yml",
}
PATH_NAMES = {"AGENTS.md", "CHANGELOG.md", "CLAUDE.md", "GEMINI.md", "README.md"}
PATH_CUE = re.compile(
    r"(?i)\b(?:read|owner|source of truth|canonical|generated|file|path|entrypoint|script|workflow|"
    r"reference|configuration|config|schema|manifest|test)\b"
)


@dataclass(frozen=True)
class Finding:
    """One validation result associated with a source line."""

    path: str
    severity: Severity
    code: str
    line: int
    message: str


@dataclass(frozen=True)
class Directive:
    category: str
    polarity: Literal["allow", "deny"]
    line: int
    text: str
    explicit_override: bool


@dataclass(frozen=True)
class CommandRule:
    key: str
    command: str
    line: int
    explicit_local: bool


@dataclass(frozen=True)
class OwnershipRule:
    key: str
    target: str
    line: int
    explicit_local: bool


@dataclass(frozen=True)
class ParsedDocument:
    path: Path
    relative_path: str
    text: str
    visible_lines: tuple[tuple[int, str], ...]
    sections: dict[str, str]
    directives: tuple[Directive, ...]
    commands: tuple[CommandRule, ...]
    ownership: tuple[OwnershipRule, ...]
    meaningful_lines: frozenset[str]


def _normalize_heading(value: str) -> str:
    normalized = re.sub(r"[`*_~]", "", value.casefold())
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")


def _normalize_rule(value: str) -> str:
    value = re.sub(r"`[^`]+`", "<path>", value.casefold())
    value = re.sub(r"\b(?:local|subtree|inherited|repository-root|root)\b", " ", value)
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def _strip_destination(raw: str) -> str:
    value = raw.strip()
    if value.startswith("<") and ">" in value:
        return value[1 : value.index(">")]
    return value.split(maxsplit=1)[0]


def _is_external(target: str) -> bool:
    return target.casefold().startswith(("http://", "https://", "mailto:", "tel:", "data:"))
