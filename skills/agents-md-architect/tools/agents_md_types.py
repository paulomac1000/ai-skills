"""Shared models and lexical contracts for AGENTS.md validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Severity = Literal["error", "warning"]
DomainProfileName = Literal["router", "application", "mcp-server", "safety-critical"]
LayoutName = Literal["single", "monorepo"]
LanguageName = Literal["en", "pl", "other"]
ProfileName = DomainProfileName
LegacyProfileName = Literal["monorepo"]

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
ABSOLUTE_HOST_PATH = re.compile(r"(?:/var/apps/|/home/[A-Za-z0-9_.-]+/|/Users/[A-Za-z0-9_.-]+/|[A-Za-z]:\\Users\\)")
PLACEHOLDER = re.compile(r"\bREPLACE_[A-Z0-9_]+\b|<command>|<path>|<owner>|TODO(?:\([^)]*\))?:", re.I)
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
CONTEXT_WAIVER = re.compile(r'<!--\s*agents-md:\s*waive\s+context-budget\s+reason="(?P<reason>[^"]+)"\s*-->', re.I)
CONTRACT_MARKER = re.compile(r"<!--\s*agents-md:\s*contract\s+(?P<name>[a-z][a-z0-9-]*)\s*-->", re.I)
COMMAND_LINE = re.compile(r"^\s*[-*]\s*(?P<label>[^:]{2,80}):\s*`(?P<command>[^`]+)`\s*[.;]?\s*$")

LANGUAGE_NEGATIVE_DIRECTIVE: dict[LanguageName, re.Pattern[str] | None] = {
    "en": re.compile(r"\b(?:must not|do not|don't|never|forbidden|prohibited|may not|cannot)\b", re.I),
    "pl": re.compile(
        r"\b(?:nie wolno|nie należy|nie można|nie edytuj|nie modyfikuj|nie zmieniaj|zakazane|zabronione|nigdy nie)\b",
        re.I,
    ),
    "other": None,
}
LANGUAGE_POSITIVE_DIRECTIVE: dict[LanguageName, re.Pattern[str] | None] = {
    "en": re.compile(r"\b(?:must|always|required|shall|may|allowed|permit(?:ted)?|edit directly)\b", re.I),
    "pl": re.compile(
        r"\b(?:musi|muszą|należy|zawsze|wymagane|wymagany|dozwolone|dozwolony|można|edytuj bezpośrednio)\b",
        re.I,
    ),
    "other": None,
}

PROFILE_BUDGETS: dict[DomainProfileName, tuple[int, int]] = {
    "router": (60, 6_000),
    "application": (120, 12_000),
    "mcp-server": (150, 16_000),
    "safety-critical": (180, 20_000),
}
LAYOUT_BUDGETS: dict[LayoutName, tuple[int, int]] = {
    "single": (0, 0),
    "monorepo": (150, 16_000),
}

ENGLISH_CONCEPT_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
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

POLISH_CONCEPT_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "scope": (re.compile(r"\bzakres\b", re.I), re.compile(r"\b(?:dotyczy|obowiązuje)\b", re.I)),
    "precedence": (
        re.compile(r"\bprecedencj", re.I),
        re.compile(r"\bdziedzicz", re.I),
        re.compile(r"\bzagnieżdżon", re.I),
    ),
    "routing": (
        re.compile(r"\brouting|trasowan|kierowan", re.I),
        re.compile(r"\bgdy\s+(?:zmieniasz|edytujesz|pracujesz|dodajesz|aktualizujesz)\b", re.I),
        re.compile(r"\bprzepływ pracy\b", re.I),
    ),
    "commands": (
        re.compile(r"\bkomend", re.I),
        re.compile(r"\bbudow", re.I),
        re.compile(r"\btest", re.I),
        re.compile(r"\bweryfikac", re.I),
    ),
    "completion": (
        re.compile(r"\bdefinicja ukończenia\b", re.I),
        re.compile(r"\bzakończen|ukończen|gotowe\b", re.I),
        re.compile(r"\bprzed\s+(?:raportowaniem|zakończeniem)\b", re.I),
    ),
    "safety": (
        re.compile(r"\bbezpieczeństw", re.I),
        re.compile(r"\bzabronion|zakazan", re.I),
        re.compile(r"\bdestrukcyjn", re.I),
    ),
    "data": (
        re.compile(r"\bgranice danych\b", re.I),
        re.compile(r"\bdane (?:wrażliwe|prywatne|osobowe)\b", re.I),
        re.compile(r"\bsekret|tajemnic", re.I),
    ),
    "nested": (
        re.compile(r"\bzagnieżdżon", re.I),
        re.compile(r"\bpoddrzew", re.I),
        re.compile(r"\blokalne różnice\b", re.I),
    ),
    "risk": (
        re.compile(r"\bryzyk", re.I),
        re.compile(r"\btylko do odczytu\b", re.I),
        re.compile(r"\bzapis\b", re.I),
        re.compile(r"\bskutk(?:i|ów) uboczn", re.I),
    ),
    "local": (
        re.compile(r"\blokalne różnice\b", re.I),
        re.compile(r"\bdla tego poddrzewa\b", re.I),
        re.compile(r"\blokalne komendy\b", re.I),
    ),
}

CONCEPT_PATTERNS_BY_LANGUAGE: dict[LanguageName, dict[str, tuple[re.Pattern[str], ...]] | None] = {
    "en": ENGLISH_CONCEPT_PATTERNS,
    "pl": POLISH_CONCEPT_PATTERNS,
    "other": None,
}

PROFILE_REQUIREMENTS: dict[DomainProfileName, tuple[str, ...]] = {
    "router": ("scope", "routing", "safety", "completion"),
    "application": ("scope", "commands", "safety", "completion"),
    "mcp-server": ("scope", "commands", "safety", "risk", "completion"),
    "safety-critical": ("scope", "commands", "safety", "data", "completion"),
}
LAYOUT_ROOT_REQUIREMENTS: dict[LayoutName, tuple[str, ...]] = {
    "single": (),
    "monorepo": ("precedence", "nested"),
}
NESTED_LAYOUT_REQUIREMENTS = ("scope", "local", "commands", "completion")
DOMAIN_NESTED_REQUIREMENTS: dict[DomainProfileName, tuple[str, ...]] = {
    "router": ("routing", "safety"),
    "application": ("safety",),
    "mcp-server": ("safety", "risk"),
    "safety-critical": ("safety", "data"),
}

PATH_SUFFIXES = {
    ".cs",
    ".csproj",
    ".json",
    ".md",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".toml",
    ".yaml",
    ".yml",
}
PATH_NAMES = {"AGENTS.md", "CHANGELOG.md", "CLAUDE.md", "GEMINI.md", "README.md"}
PATH_CUE = re.compile(
    r"(?i)\b(?:read|owner|source of truth|canonical|generated|file|path|entrypoint|script|workflow|"
    r"reference|configuration|config|schema|manifest|test|przeczytaj|właściciel|plik|ścieżka|skrypt|test)\b"
)

MAX_INSTRUCTION_FILE_BYTES = 256 * 1024
MAX_INSTRUCTION_TREE_BYTES = 2 * 1024 * 1024
MAX_INSTRUCTION_FILES = 128
MAX_DISCOVERY_ENTRIES = 100_000
MAX_DISCOVERY_DEPTH = 64
MAX_GATE_FILES = 64
MAX_GATE_FILE_BYTES = 256 * 1024
MAX_GATE_TOTAL_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class Finding:
    """One validation result associated with a source line."""

    path: str
    severity: Severity
    code: str
    line: int
    message: str


@dataclass(frozen=True)
class ReadResult:
    text: str | None
    byte_count: int
    code: str | None
    message: str | None


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
    contracts: frozenset[str]
    directives: tuple[Directive, ...]
    commands: tuple[CommandRule, ...]
    ownership: tuple[OwnershipRule, ...]
    meaningful_lines: frozenset[str]


def effective_budget(profile: DomainProfileName, layout: LayoutName) -> tuple[int, int]:
    profile_lines, profile_bytes = PROFILE_BUDGETS[profile]
    layout_lines, layout_bytes = LAYOUT_BUDGETS[layout]
    return max(profile_lines, layout_lines), max(profile_bytes, layout_bytes)


def _normalize_heading(value: str) -> str:
    normalized = re.sub(r"[`*_~]", "", value.casefold())
    return re.sub(r"[^\w]+", "-", normalized, flags=re.UNICODE).strip("-")


def _normalize_rule(value: str) -> str:
    value = re.sub(r"`[^`]+`", "<path>", value.casefold())
    value = re.sub(
        r"\b(?:local|subtree|inherited|repository-root|root|lokaln\w*|poddrzew\w*|dziedziczon\w*|główn\w*)\b",
        " ",
        value,
        flags=re.UNICODE,
    )
    return " ".join(re.sub(r"[^\w]+", " ", value, flags=re.UNICODE).split())


def _strip_destination(raw: str) -> str:
    value = raw.strip()
    if value.startswith("<") and ">" in value:
        return value[1 : value.index(">")]
    return value.split(maxsplit=1)[0]


def _is_external(target: str) -> bool:
    return target.casefold().startswith(("http://", "https://", "mailto:", "tel:", "data:"))
