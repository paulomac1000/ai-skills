#!/usr/bin/env python3
"""Audit AGENTS.md instruction trees without executing repository-controlled commands."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from dataclasses import asdict
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent
_CONTRACTS = _TOOLS.parents[2] / "contracts"
for _candidate in (_TOOLS, _CONTRACTS):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import audit_agents_md_impl as _impl  # noqa: E402
from agents_md_gate_sources import GateSourceInventory, classify_gate_sources  # noqa: E402
from agents_md_types import (  # noqa: E402
    MAX_GATE_FILE_BYTES,
    MAX_GATE_FILES,
    MAX_GATE_TOTAL_BYTES,
    LanguageName,
    LayoutName,
)
from confined_io import ConfinedReadError, read_utf8_bounded  # noqa: E402
from runtime_fact_classification import FINDING_CODE, volatile_binding_message  # noqa: E402

AuditFinding = _impl.AuditFinding
CommandEvidence = _impl.CommandEvidence
KnownCommands = _impl.KnownCommands
Finding = _impl.Finding
PlatformName = _impl.PlatformName
CODEX_DEFAULT_PROJECT_DOC_MAX_BYTES = _impl.CODEX_DEFAULT_PROJECT_DOC_MAX_BYTES

# Preserve the tested facade surface while the implementation is split into
# bounded helper modules. Consumers that import the audit entrypoint must not
# have to know the internal module topology.
_extract_python_invocations = _impl._extract_python_invocations
_extract_gate_invocations = _impl._extract_gate_invocations
_extract_yaml_invocations = _impl._extract_yaml_invocations
_extract_shell_invocations = _impl._extract_shell_invocations
_command_reference_status = _impl._command_reference_status
_read_text = _impl._read_text
discover = _impl.discover


def _known_gate_commands_with_inventory(
    root: Path,
    discovery: _impl.Discovery,
) -> tuple[KnownCommands, GateSourceInventory, list[AuditFinding]]:
    """Collect command evidence while applying the policy budget only to real entrypoints."""
    inventory = classify_gate_sources(root, discovery, limit=MAX_GATE_FILES)
    gate_sources = tuple(sorted(set((*discovery.ci_files, *discovery.task_runners))))
    public_sources = _impl._public_source_files(discovery)
    sources = tuple(sorted(set((*gate_sources, *public_sources))))
    findings: list[AuditFinding] = []
    public_commands = set(_impl._entrypoint_invocations(discovery))
    executed_commands: set[CommandEvidence] = set()

    if inventory.count > inventory.limit:
        counted = [item.path for item in inventory.sources if item.counted]
        preview = ", ".join(counted[:12])
        suffix = "" if len(counted) <= 12 else f", ... (+{len(counted) - 12} more)"
        findings.append(
            AuditFinding(
                root.as_posix(),
                "error",
                "evidence.too-many-gate-sources",
                1,
                (
                    f"Found {inventory.count} classified CI/task entrypoints; limit {inventory.limit}; "
                    f"headroom {inventory.headroom}. Counted: {preview}{suffix}"
                ),
            )
        )

    total_bytes = 0
    for relative in sources:
        try:
            path = _impl._confined_file(root, relative)
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
            syntax_error = _impl._yaml_syntax_error(text)
            if syntax_error is not None:
                findings.append(AuditFinding(relative, "error", "evidence.invalid-yaml", 1, syntax_error))
                continue
        public_commands.update(
            _impl._parse_many(
                _impl.public_task_invocations(relative, text),
                _impl._source_working_directory(relative),
            )
        )
        if relative in gate_sources:
            executed_commands.update(_impl._executed_source_evidence(relative, text))
    return KnownCommands(frozenset(public_commands), frozenset(executed_commands)), inventory, findings


def _known_gate_commands(
    root: Path,
    discovery: _impl.Discovery,
) -> tuple[KnownCommands, list[AuditFinding]]:
    """Return the compatibility facade used by existing audit consumers."""
    known, _inventory, findings = _known_gate_commands_with_inventory(root, discovery)
    return known, findings


def audit(
    root: Path,
    profile: str = "application",
    layout: LayoutName | None = None,
    language: LanguageName = "en",
    platform: PlatformName = "generic",
    project_doc_max_bytes: int = CODEX_DEFAULT_PROJECT_DOC_MAX_BYTES,
    project_doc_fallback_filenames: Sequence[str] = (),
) -> tuple[_impl.Discovery, list[AuditFinding]]:
    """Audit root and nested instructions using only static, repository-confined reads."""
    domain_profile, selected_layout = _impl.normalize_selection(profile, layout)
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
    validation_findings, documents = _impl.validate_many_with_documents(
        paths,
        domain_profile,
        safe_root,
        selected_layout,
        language,
        platform,
        project_doc_max_bytes,
        project_doc_fallback_filenames,
    )
    findings.extend(_impl._convert(item) for item in validation_findings)

    reference_paragraphs: dict[str, tuple[str, int]] = {}
    for reference in ("README.md", "CHANGELOG.md"):
        if reference not in discovery.files:
            continue
        try:
            for paragraph, paragraph_line in _impl._paragraphs(_read_text(safe_root, reference)).items():
                reference_paragraphs.setdefault(paragraph, (reference, paragraph_line))
        except ValueError:
            continue

    known_commands, _inventory, gate_findings = _known_gate_commands_with_inventory(safe_root, discovery)
    findings.extend(gate_findings)
    for document in documents:
        relative = document.relative_path
        for paragraph, line_number in _impl._paragraphs(document.text).items():
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
            runtime_message = volatile_binding_message(line)
            if runtime_message is not None:
                findings.append(
                    AuditFinding(
                        relative,
                        "warning",
                        FINDING_CODE,
                        line_number,
                        runtime_message,
                    )
                )
            if _impl.LINT_LEAKAGE.search(line):
                findings.append(
                    AuditFinding(
                        relative,
                        "warning",
                        "content.lint-leakage",
                        line_number,
                        "Keep formatter and linter configuration executable; document only a non-obvious repository exception.",
                    )
                )

        for command_rule in _impl.completion_command_rules(document.text):
            command_directory = _impl._normalized_working_directory(Path(relative).parent)
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
        inventory = classify_gate_sources(Path(discovery.root), discovery, limit=MAX_GATE_FILES)
    except ValueError as error:
        print(str(error))
        return 2
    if args.output_format == "json":
        print(
            json.dumps(
                {
                    "discovery": asdict(discovery),
                    "gate_source_inventory": asdict(inventory),
                    "findings": [asdict(item) for item in findings],
                },
                indent=2,
                sort_keys=True,
            )
        )
    elif findings:
        print(_render_text(findings))
    else:
        print(
            "AGENTS.md audit passed. "
            f"Gate entrypoints: {inventory.count}/{inventory.limit}; headroom {inventory.headroom}."
        )
    has_error = any(item.severity == "error" for item in findings)
    has_warning = any(item.severity == "warning" for item in findings)
    return 1 if has_error or (args.strict and has_warning) else 0


if __name__ == "__main__":
    raise SystemExit(main())
