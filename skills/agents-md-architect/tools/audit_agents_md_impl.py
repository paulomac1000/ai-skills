#!/usr/bin/env python3
"""Audit AGENTS.md instruction trees without executing repository-controlled commands."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path, PureWindowsPath
from typing import Literal
from urllib.parse import unquote

TOOLS = Path(__file__).resolve().parent
REPOSITORY_ROOT = TOOLS.parents[2]
CONTRACTS = REPOSITORY_ROOT / "contracts"
for candidate in (TOOLS, CONTRACTS):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from agents_md_command import CommandInvocation, invocation_from_argv, parse_invocation  # noqa: E402
from agents_md_completion_evidence import (  # noqa: E402
    completion_command_rules,
    public_task_invocations,
)
from agents_md_parse import iter_references, parse_visible_lines, resolve_reference  # noqa: E402
from agents_md_python_evidence import _extract_python_invocations  # noqa: E402
from agents_md_shell_evidence import (  # noqa: E402
    _command_path_tokens,
    _extract_gate_invocations,
    _extract_yaml_command_evidence,
    _yaml_syntax_error,
)
from agents_md_shell_evidence import (  # noqa: E402
    _extract_shell_invocations as _shell_invocations,
)
from agents_md_shell_evidence import (  # noqa: E402
    _extract_yaml_invocations as _yaml_invocations,
)
from agents_md_types import (  # noqa: E402
    MAX_GATE_FILE_BYTES,
    MAX_GATE_FILES,
    MAX_GATE_TOTAL_BYTES,
    LanguageName,
    LayoutName,
    ParsedDocument,
)
from confined_io import ConfinedReadError, read_utf8_bounded  # noqa: E402
from discover_repository import Discovery, discover  # noqa: E402
from validate_agents_md import (  # noqa: E402
    CODEX_DEFAULT_PROJECT_DOC_MAX_BYTES,
    Finding,
    PlatformName,
    normalize_selection,
    validate_many_with_documents,
)

_extract_shell_invocations = _shell_invocations
_extract_yaml_invocations = _yaml_invocations

Severity = Literal["error", "warning"]
LINT_LEAKAGE = re.compile(
    r"(?i)\b(?:line length|quote style|indent(?:ation)? width|ruff rule|eslint rule|prettier config|"
    r"formatter config|stylecop rule)\b"
)

PROGRESSIVE_ROUTE_PREFIX = re.compile(r"<!--\s*agents-md:\s*route\b", re.I)
PROGRESSIVE_ROUTE_MARKER = re.compile(r"<!--\s*agents-md:\s*route(?P<attributes>.*?)-->\s*$", re.I)
PROGRESSIVE_ROUTE_ATTRIBUTE = re.compile(r'(?P<name>[a-z][a-z0-9-]*)="(?P<value>[^"]*)"')
CONDITIONAL_OWNER_MARKER = re.compile(r"<!--\s*agents-md:\s*conditional-owner\s*-->\s*$", re.I)
PROGRESSIVE_ROUTE_REQUIRED = frozenset({"owner", "when", "purpose"})
PROGRESSIVE_ROUTE_OPTIONAL = frozenset({"invoke-owner"})
PROGRESSIVE_OWNER_SCAN_LIMIT = 4096
PROGRESSIVE_OWNER_READ_LIMIT = 256 * 1024
PROGRESSIVE_ROUTING_PROOF_BOUNDARY = (
    "Static routing audit proves declared marker syntax, confinement, owner uniqueness, and structural pre-load "
    "reachability only; semantic trigger timing and actual platform loading require behavioral/provider evidence."
)


@dataclass(frozen=True)
class AuditFinding:
    """One repository-level instruction audit result."""

    path: str
    severity: Severity
    code: str
    line: int
    message: str


@dataclass(frozen=True)
class CommandEvidence:
    """One exact invocation bound to the directory from which it is executable."""

    working_directory: str
    invocation: CommandInvocation


@dataclass(frozen=True)
class KnownCommands:
    """Static command evidence separated by public and internal execution surfaces."""

    public_entrypoints: frozenset[CommandEvidence]
    executed_commands: frozenset[CommandEvidence]


@dataclass(frozen=True)
class ProgressiveRoute:
    """One mechanically declared conditional route owned by an instruction file."""

    source: str
    line: int
    owner: str
    trigger: str
    purpose: str
    invocation_owner: str | None


def _parse_progressive_route_marker(line: str) -> tuple[dict[str, str] | None, str | None]:
    stripped = line.strip()
    if PROGRESSIVE_ROUTE_PREFIX.search(stripped) is None:
        return None, None
    marker = PROGRESSIVE_ROUTE_MARKER.fullmatch(stripped)
    if marker is None:
        return None, "Malformed agents-md route marker."

    raw = marker.group("attributes")
    attributes: dict[str, str] = {}
    cursor = 0
    for match in PROGRESSIVE_ROUTE_ATTRIBUTE.finditer(raw):
        if raw[cursor : match.start()].strip():
            return None, "Route marker contains invalid attribute syntax."
        name = match.group("name").casefold()
        value = match.group("value").strip()
        if name in attributes:
            return None, f"Route marker repeats attribute {name!r}."
        attributes[name] = value
        cursor = match.end()
    if raw[cursor:].strip():
        return None, "Route marker contains invalid trailing syntax."

    allowed = PROGRESSIVE_ROUTE_REQUIRED | PROGRESSIVE_ROUTE_OPTIONAL
    unknown = sorted(set(attributes) - allowed)
    missing = sorted(PROGRESSIVE_ROUTE_REQUIRED - set(attributes))
    empty = sorted(name for name, value in attributes.items() if not value)
    if unknown:
        return None, f"Route marker contains unsupported attributes: {unknown}."
    if missing:
        return None, f"Route marker is missing required attributes: {missing}."
    if empty:
        return None, f"Route marker attributes must be non-empty: {empty}."
    return attributes, None


def _resolve_progressive_target(
    root: Path,
    source_relative: str,
    target: str,
    *,
    line: int,
    kind: Literal["route-owner", "invocation-owner"],
) -> tuple[str | None, list[AuditFinding]]:
    code_prefix = "routing.route-owner" if kind == "route-owner" else "routing.invocation-owner"
    label = "Conditional route owner" if kind == "route-owner" else "Canonical invocation owner"
    normalized_target = unquote(target.split("#", 1)[0]).strip()
    if Path(normalized_target).is_absolute() or PureWindowsPath(normalized_target).is_absolute():
        return None, [
            AuditFinding(
                source_relative,
                "error",
                f"{code_prefix}-absolute",
                line,
                f"{label} must be repository-relative: {target}",
            )
        ]
    if normalized_target.casefold().startswith(("http://", "https://", "mailto:", "tel:", "data:")):
        return None, [
            AuditFinding(
                source_relative,
                "error",
                f"{code_prefix}-external",
                line,
                f"{label} must be a repository-relative regular file: {target}",
            )
        ]

    if kind == "route-owner" and Path(normalized_target).suffix.casefold() not in {".md", ".markdown"}:
        return None, [
            AuditFinding(
                source_relative,
                "error",
                "routing.route-owner-format",
                line,
                f"Mechanical conditional owners must be Markdown files: {target}",
            )
        ]

    resolved, issue = resolve_reference(root / "AGENTS.md", root, target)
    if resolved is None:
        return None, [
            AuditFinding(
                source_relative,
                "error",
                f"{code_prefix}-invalid",
                line,
                f"{label} could not be resolved safely: {target}",
            )
        ]
    if issue is not None:
        suffix = {"outside": "outside", "symlink": "symlink", "unreadable": "unreadable"}.get(issue, "invalid")
        return None, [
            AuditFinding(
                source_relative,
                "error",
                f"{code_prefix}-{suffix}",
                line,
                f"{label} is not a confined regular file: {target}",
            )
        ]
    try:
        exists = resolved.exists()
        regular = resolved.is_file() if exists else False
    except (OSError, RuntimeError):
        return None, [
            AuditFinding(
                source_relative,
                "error",
                f"{code_prefix}-unreadable",
                line,
                f"{label} could not be inspected safely: {target}",
            )
        ]
    if not exists:
        return None, [
            AuditFinding(
                source_relative,
                "error",
                f"{code_prefix}-missing",
                line,
                f"{label} does not exist: {target}",
            )
        ]
    if not regular:
        return None, [
            AuditFinding(
                source_relative,
                "error",
                f"{code_prefix}-type",
                line,
                f"{label} must resolve to a regular file: {target}",
            )
        ]
    return resolved.relative_to(root).as_posix(), []


def _is_indented_code_line(line: str) -> bool:
    return line.startswith("\t") or line.startswith("    ")


def _routing_active_lines(lines: Sequence[tuple[int, str]]) -> list[tuple[int, str]]:
    """Return routing evidence outside fenced/indented code and ordinary HTML comments."""
    active: list[tuple[int, str]] = []
    in_html_comment = False

    for line_number, source_line in lines:
        stripped = source_line.strip()
        indented_code = _is_indented_code_line(source_line)
        if not in_html_comment and not indented_code and PROGRESSIVE_ROUTE_PREFIX.search(stripped) is not None:
            # Keep malformed route candidates visible so the route parser can fail closed.
            active.append((line_number, source_line))
            continue
        if (
            not in_html_comment
            and not indented_code
            and CONDITIONAL_OWNER_MARKER.fullmatch(stripped) is not None
        ):
            active.append((line_number, source_line))
            continue
        if indented_code and not in_html_comment:
            # An indented code sample cannot open a Markdown HTML comment.
            continue

        value = source_line
        visible_parts: list[str] = []
        while value:
            if in_html_comment:
                end = value.find("-->")
                if end < 0:
                    value = ""
                    break
                visible_parts.append(" ")
                value = value[end + 3 :]
                in_html_comment = False
                continue

            start = value.find("<!--")
            if start < 0:
                visible_parts.append(value)
                break
            visible_parts.append(value[:start])
            visible_parts.append(" ")
            end = value.find("-->", start + 4)
            if end < 0:
                in_html_comment = True
                break
            value = value[end + 3 :]

        if indented_code:
            continue
        visible = "".join(visible_parts)
        if visible.strip():
            active.append((line_number, visible))
        elif not source_line.strip():
            active.append((line_number, ""))

    return active


def _conditional_owner_markers(
    root: Path,
    discovery: Discovery,
    routed_owners: set[str],
) -> tuple[dict[str, int], set[str], list[AuditFinding]]:
    candidates = sorted(
        relative for relative in discovery.files if Path(relative).suffix.casefold() in {".md", ".markdown"}
    )
    if len(candidates) > PROGRESSIVE_OWNER_SCAN_LIMIT:
        return (
            {},
            set(),
            [
                AuditFinding(
                    root.as_posix(),
                    "error",
                    "routing.conditional-owner-scan-budget",
                    1,
                    (
                        f"Conditional-owner scan has {len(candidates)} Markdown files, above the "
                        f"{PROGRESSIVE_OWNER_SCAN_LIMIT} file proof budget."
                    ),
                )
            ],
        )

    owners: dict[str, int] = {}
    unreadable: set[str] = set()
    findings: list[AuditFinding] = []
    for relative in candidates:
        try:
            text = _read_text(root, relative, PROGRESSIVE_OWNER_READ_LIMIT)
        except ValueError as error:
            if relative in routed_owners:
                unreadable.add(relative)
                findings.append(
                    AuditFinding(
                        relative,
                        "error",
                        "routing.conditional-owner-unreadable",
                        1,
                        f"Routed conditional-owner evidence could not be read: {error}",
                    )
                )
            continue
        visible_lines, _unclosed = parse_visible_lines(text)
        routing_lines = _routing_active_lines(visible_lines)
        marker_lines = [
            line_number
            for line_number, line in routing_lines
            if CONDITIONAL_OWNER_MARKER.fullmatch(line.strip()) is not None
        ]
        if len(marker_lines) > 1:
            findings.append(
                AuditFinding(
                    relative,
                    "error",
                    "routing.conditional-owner-marker-duplicate",
                    marker_lines[1],
                    "A conditional owner declares agents-md: conditional-owner more than once.",
                )
            )
        if marker_lines:
            owners[relative] = marker_lines[0]
    return owners, unreadable, findings


def _route_prose_line_numbers(
    routing_lines: Sequence[tuple[int, str]],
    marker_index: int,
) -> set[int]:
    line_numbers: set[int] = set()
    started = False
    for line_number, candidate in routing_lines[marker_index + 1 :]:
        stripped = candidate.strip()
        if not started:
            if not stripped or stripped.startswith("<!--"):
                continue
            if stripped.startswith("#") or PROGRESSIVE_ROUTE_PREFIX.search(stripped) is not None:
                return set()
            started = True
            line_numbers.add(line_number)
            continue

        if not stripped:
            break
        if stripped.startswith("#") or PROGRESSIVE_ROUTE_PREFIX.search(stripped) is not None:
            break
        if stripped.startswith("<!--"):
            continue
        line_numbers.add(line_number)
    return line_numbers


def _has_readable_route_prose(
    root: Path,
    document: ParsedDocument,
    routing_lines: Sequence[tuple[int, str]],
    marker_index: int,
    owner_relative: str,
) -> bool:
    prose_lines = _route_prose_line_numbers(routing_lines, marker_index)
    if not prose_lines:
        return False
    for reference_line, target in iter_references(routing_lines):
        if reference_line not in prose_lines:
            continue
        resolved, issue = resolve_reference(document.path, root, target)
        if resolved is None or issue is not None:
            continue
        try:
            relative = resolved.relative_to(root).as_posix()
        except ValueError:
            continue
        if relative == owner_relative:
            return True
    return False


def _progressive_routing_findings(
    root: Path,
    discovery: Discovery,
    documents: Sequence[ParsedDocument],
) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    routes_by_owner: dict[str, list[ProgressiveRoute]] = {}

    for document in documents:
        relative = document.relative_path
        routing_lines = _routing_active_lines(document.visible_lines)
        for marker_index, (line_number, line) in enumerate(routing_lines):
            attributes, error = _parse_progressive_route_marker(line)
            if error is not None:
                findings.append(AuditFinding(relative, "error", "routing.route-marker-invalid", line_number, error))
                continue
            if attributes is None:
                continue

            owner, owner_findings = _resolve_progressive_target(
                root,
                relative,
                attributes["owner"],
                line=line_number,
                kind="route-owner",
            )
            findings.extend(owner_findings)
            invocation_owner = attributes.get("invoke-owner")
            if invocation_owner is not None:
                _resolved_invocation, invocation_findings = _resolve_progressive_target(
                    root,
                    relative,
                    invocation_owner,
                    line=line_number,
                    kind="invocation-owner",
                )
                findings.extend(invocation_findings)
            if owner is None:
                continue
            readable_route = _has_readable_route_prose(
                root,
                document,
                routing_lines,
                marker_index,
                owner,
            )
            if not readable_route:
                findings.append(
                    AuditFinding(
                        relative,
                        "error",
                        "routing.route-prose-missing",
                        line_number,
                        "Route marker must be followed by readable prose linking to its conditional owner.",
                    )
                )
                continue
            if owner == relative:
                findings.append(
                    AuditFinding(
                        relative,
                        "error",
                        "routing.trigger-self-reference",
                        line_number,
                        "A conditional owner cannot trigger itself from inside the unopened destination.",
                    )
                )
                continue
            route = ProgressiveRoute(
                source=relative,
                line=line_number,
                owner=owner,
                trigger=attributes["when"],
                purpose=attributes["purpose"],
                invocation_owner=invocation_owner,
            )
            routes_by_owner.setdefault(owner, []).append(route)

    conditional_owners, unreadable_owners, owner_findings = _conditional_owner_markers(
        root,
        discovery,
        set(routes_by_owner),
    )
    findings.extend(owner_findings)

    for owner, routes in sorted(routes_by_owner.items()):
        if owner not in conditional_owners and owner not in unreadable_owners:
            for route in routes:
                findings.append(
                    AuditFinding(
                        route.source,
                        "error",
                        "routing.conditional-owner-marker-missing",
                        route.line,
                        (
                            f"Mechanically declared route target {owner!r} must declare "
                            "agents-md: conditional-owner in the destination."
                        ),
                    )
                )
        if len(routes) > 1:
            sources = ", ".join(f"{route.source}:{route.line}" for route in routes)
            for route in routes:
                findings.append(
                    AuditFinding(
                        route.source,
                        "error",
                        "routing.trigger-owner-duplicate",
                        route.line,
                        f"Conditional owner {owner!r} has multiple editable trigger owners: {sources}.",
                    )
                )

    for owner, marker_line in sorted(conditional_owners.items()):
        if not routes_by_owner.get(owner):
            findings.append(
                AuditFinding(
                    owner,
                    "error",
                    "routing.trigger-unreachable",
                    marker_line,
                    (
                        "Conditional owner has no reachable agents-md: route in the applicable instruction tree; "
                        "a trigger inside the unopened destination does not count."
                    ),
                )
            )

    return findings


def _extract_source_invocations(relative: str, text: str) -> set[str]:
    if Path(relative).suffix.casefold() == ".py":
        return _extract_python_invocations(text)
    return _extract_gate_invocations(relative, text)


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
    try:
        text, _count = read_utf8_bounded(path, root, max_bytes)
    except ConfinedReadError as error:
        raise ValueError(error.message) from error
    return text


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


def _normalized_working_directory(path: Path) -> str:
    value = path.as_posix()
    return "." if value in {"", "."} else value


def _source_working_directory(relative: str, *, executed: bool = False) -> str:
    path = Path(relative)
    if relative.startswith((".github/workflows/", "scripts/", "bin/")) or relative in {
        ".circleci/config.yml",
        ".gitlab-ci.yml",
        "Jenkinsfile",
        "azure-pipelines.yml",
        "azure-pipelines.yaml",
    }:
        return "."
    if executed and path.suffix.casefold() in {".py", ".ps1", ".sh"}:
        return "."
    return _normalized_working_directory(path.parent)


def _evidence_from_argv(working_directory: str, argv: Iterable[str]) -> CommandEvidence | None:
    invocation = invocation_from_argv(argv)
    if invocation is None:
        return None
    return CommandEvidence(working_directory, invocation)


def _entrypoint_invocations(discovery: Discovery) -> set[CommandEvidence]:
    invocations: set[CommandEvidence] = set()
    for relative in discovery.task_runners:
        path = Path(relative)
        suffix = path.suffix.casefold()
        argument_sets: tuple[tuple[str, ...], ...] = ()
        if suffix == ".py":
            argument_sets = (("python", relative), ("python3", relative))
        elif suffix == ".sh":
            argument_sets = (("bash", relative), ("sh", relative), (f"./{relative}",))
        elif suffix == ".ps1":
            argument_sets = (("pwsh", relative), ("powershell", relative))
        elif not suffix and relative.startswith("bin/"):
            argument_sets = ((relative,), (f"./{relative}",))
        for argv in argument_sets:
            evidence = _evidence_from_argv(".", argv)
            if evidence is not None:
                invocations.add(evidence)
    return invocations


def _public_source_files(discovery: Discovery) -> tuple[str, ...]:
    manifests = (
        relative
        for relative in discovery.manifests
        if Path(relative).name.casefold() == "package.json"
        or Path(relative).suffix.casefold() in {".csproj", ".fsproj", ".vbproj", ".targets", ".proj"}
    )
    return tuple(sorted(set((*discovery.task_runners, *manifests))))


def _parse_many(commands: Iterable[str], working_directory: str) -> set[CommandEvidence]:
    """Parse commands without collapsing argument or working-directory boundaries."""
    return {
        CommandEvidence(working_directory, invocation)
        for command in commands
        if (invocation := parse_invocation(command)) is not None
    }


def _executed_source_evidence(relative: str, text: str) -> set[CommandEvidence]:
    working_directory = _source_working_directory(relative, executed=True)
    if Path(relative).suffix.casefold() in {".yml", ".yaml"}:
        evidence: set[CommandEvidence] = set()
        for command_directory, command in _extract_yaml_command_evidence(relative, text, working_directory):
            evidence.update(_parse_many((command,), command_directory))
        return evidence
    return _parse_many(_extract_source_invocations(relative, text), working_directory)


def _known_gate_commands(root: Path, discovery: Discovery) -> tuple[KnownCommands, list[AuditFinding]]:
    gate_sources = tuple(sorted(set((*discovery.ci_files, *discovery.task_runners))))
    public_sources = _public_source_files(discovery)
    sources = tuple(sorted(set((*gate_sources, *public_sources))))
    findings: list[AuditFinding] = []
    public_commands = set(_entrypoint_invocations(discovery))
    executed_commands: set[CommandEvidence] = set()
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
        return KnownCommands(frozenset(public_commands), frozenset()), findings

    total_bytes = 0
    for relative in sources:
        try:
            path = _confined_file(root, relative)
            text, byte_count = read_utf8_bounded(path, root, MAX_GATE_FILE_BYTES)
        except (ValueError, ConfinedReadError) as error:
            findings.append(AuditFinding(relative, "error", "evidence.gate-source-unreadable", 1, str(error)))
            continue
        total_bytes += byte_count
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
            syntax_error = _yaml_syntax_error(text)
            if syntax_error is not None:
                findings.append(AuditFinding(relative, "error", "evidence.invalid-yaml", 1, syntax_error))
                continue
        public_commands.update(
            _parse_many(public_task_invocations(relative, text), _source_working_directory(relative))
        )
        if relative in gate_sources:
            executed_commands.update(_executed_source_evidence(relative, text))
    return KnownCommands(frozenset(public_commands), frozenset(executed_commands)), findings


def _command_reference_status(
    root: Path,
    command: str,
    known_commands: KnownCommands,
    working_directory: str = ".",
) -> str:
    """Classify static command evidence without discarding its execution directory."""
    invocation = parse_invocation(command)
    evidence = CommandEvidence(working_directory, invocation) if invocation is not None else None
    if evidence is not None and evidence in known_commands.public_entrypoints:
        return "located-public"
    if evidence is not None and evidence in known_commands.executed_commands:
        return "located-executed"
    for token in _command_path_tokens(command):
        candidate = (Path(working_directory) / token).as_posix()
        try:
            _confined_file(root, candidate)
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
    platform: PlatformName = "generic",
    project_doc_max_bytes: int = CODEX_DEFAULT_PROJECT_DOC_MAX_BYTES,
    project_doc_fallback_filenames: Sequence[str] = (),
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
        paths,
        domain_profile,
        safe_root,
        selected_layout,
        language,
        platform,
        project_doc_max_bytes,
        project_doc_fallback_filenames,
    )
    findings.extend(_convert(item) for item in validation_findings)
    findings.extend(_progressive_routing_findings(safe_root, discovery, documents))

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
    for document in documents:
        relative = document.relative_path
        for paragraph, line_number in _paragraphs(document.text).items():
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

        for line_number, line in document.visible_lines:
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

        for command_rule in completion_command_rules(document.text):
            command_directory = _normalized_working_directory(Path(relative).parent)
            status = _command_reference_status(
                safe_root,
                command_rule.command,
                known_commands,
                command_directory,
            )
            if status == "unlocated":
                findings.append(
                    AuditFinding(
                        relative,
                        "error",
                        "commands.unlocated-full-gate",
                        command_rule.line,
                        "Completion command could not be located in discovered CI or repository task runners: "
                        + command_rule.command,
                    )
                )
            elif status == "unverified":
                findings.append(
                    AuditFinding(
                        relative,
                        "warning",
                        "commands.unverified-full-gate",
                        command_rule.line,
                        f"A referenced path exists, but the exact completion invocation was not located: {command_rule.command}",
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
    parser.add_argument(
        "--platform",
        choices=("generic", "codex"),
        default="generic",
        help="optional platform-specific effective-instruction validation",
    )
    parser.add_argument(
        "--project-doc-max-bytes",
        type=int,
        default=CODEX_DEFAULT_PROJECT_DOC_MAX_BYTES,
        help="Codex project_doc_max_bytes value (default: 32768)",
    )
    parser.add_argument(
        "--project-doc-fallback-filename",
        action="append",
        default=[],
        help="Codex project_doc_fallback_filenames entry; repeat to preserve configured order",
    )
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    parser.add_argument("--format", choices=("json", "text"), default="text", dest="output_format")
    return parser


def _render_text(findings: Iterable[AuditFinding]) -> str:
    return "\n".join(f"{item.path}:{item.line}: {item.severity}: {item.code}: {item.message}" for item in findings)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        discovery, findings = audit(
            args.root,
            args.profile,
            args.layout,
            args.language,
            args.platform,
            args.project_doc_max_bytes,
            args.project_doc_fallback_filename,
        )
    except ValueError as error:
        print(str(error))
        return 2
    if args.output_format == "json":
        print(
            json.dumps(
                {
                    "discovery": asdict(discovery),
                    "findings": [asdict(item) for item in findings],
                    "proof_boundary": PROGRESSIVE_ROUTING_PROOF_BOUNDARY,
                },
                indent=2,
                sort_keys=True,
            )
        )
    elif findings:
        print(_render_text(findings))
        print(f"Proof boundary: {PROGRESSIVE_ROUTING_PROOF_BOUNDARY}")
    else:
        print("AGENTS.md audit passed.")
        print(f"Proof boundary: {PROGRESSIVE_ROUTING_PROOF_BOUNDARY}")
    has_error = any(item.severity == "error" for item in findings)
    has_warning = any(item.severity == "warning" for item in findings)
    return 1 if has_error or (args.strict and has_warning) else 0


if __name__ == "__main__":
    raise SystemExit(main())
