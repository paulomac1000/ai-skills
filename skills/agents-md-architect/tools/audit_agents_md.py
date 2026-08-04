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
REPOSITORY_ROOT = TOOLS.parents[2]
CONTRACTS = REPOSITORY_ROOT / "contracts"
for candidate in (TOOLS, CONTRACTS):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from agents_md_completion_evidence import (  # noqa: E402
    completion_command_rules,
    public_task_invocations,
)
from agents_md_parse import parse_visible_lines  # noqa: E402
from agents_md_python_evidence import _extract_python_invocations  # noqa: E402
from agents_md_shell_evidence import (  # noqa: E402
    _command_path_tokens,
    _extract_gate_invocations,
    _extract_shell_invocations,
    _extract_yaml_invocations,
    _normalize_invocation,
    _yaml_syntax_error,
)
from agents_md_types import (  # noqa: E402
    MAX_GATE_FILE_BYTES,
    MAX_GATE_FILES,
    MAX_GATE_TOTAL_BYTES,
    LanguageName,
    LayoutName,
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

Severity = Literal["error", "warning"]
LINT_LEAKAGE = re.compile(
    r"(?i)\b(?:line length|quote style|indent(?:ation)? width|ruff rule|eslint rule|prettier config|"
    r"formatter config|stylecop rule)\b"
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
class KnownCommands:
    """Static command evidence separated by public and internal execution surfaces."""

    public_entrypoints: frozenset[str]
    executed_commands: frozenset[str]


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


def _public_source_files(discovery: Discovery) -> tuple[str, ...]:
    manifests = (
        relative
        for relative in discovery.manifests
        if Path(relative).name.casefold() == "package.json"
        or Path(relative).suffix.casefold() in {".csproj", ".fsproj", ".vbproj", ".targets", ".proj"}
    )
    return tuple(sorted(set((*discovery.task_runners, *manifests))))


def _normalize_many(commands: Iterable[str]) -> set[str]:
    return {normalized for command in commands if (normalized := _normalize_invocation(command)) is not None}


def _known_gate_commands(root: Path, discovery: Discovery) -> tuple[KnownCommands, list[AuditFinding]]:
    gate_sources = tuple(sorted(set((*discovery.ci_files, *discovery.task_runners))))
    public_sources = _public_source_files(discovery)
    sources = tuple(sorted(set((*gate_sources, *public_sources))))
    findings: list[AuditFinding] = []
    public_commands = _normalize_many(_entrypoint_invocations(discovery))
    executed_commands: set[str] = set()
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
        public_commands.update(_normalize_many(public_task_invocations(relative, text)))
        if relative in gate_sources:
            executed_commands.update(_normalize_many(_extract_source_invocations(relative, text)))
    return KnownCommands(frozenset(public_commands), frozenset(executed_commands)), findings


def _command_reference_status(root: Path, command: str, known_commands: KnownCommands) -> str:
    """Classify static command evidence without claiming execution."""
    normalized = _normalize_invocation(command)
    if normalized is not None and normalized in known_commands.public_entrypoints:
        return "located-public"
    if normalized is not None and normalized in known_commands.executed_commands:
        return "located-executed"
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
            status = _command_reference_status(safe_root, command_rule.command, known_commands)
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
