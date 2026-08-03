#!/usr/bin/env python3
"""Validate AGENTS.md files for scope, routing, safety, and instruction-tree drift."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Literal, cast

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from agents_md_codex_platform import (  # noqa: E402
    CODEX_DEFAULT_PROJECT_DOC_MAX_BYTES,
    _validate_codex_context,
)
from agents_md_codex_platform import (  # noqa: E402
    _normalize_fallback_filenames as _normalize_fallback_filenames,
)
from agents_md_document_rules import (  # noqa: E402
    _active_context_waivers as _active_context_waivers,
)
from agents_md_document_rules import (  # noqa: E402
    _ordered_requirements as _ordered_requirements,
)
from agents_md_document_rules import _validate_document  # noqa: E402
from agents_md_parse import parse_document, read_utf8_bounded, trusted_input, trusted_root  # noqa: E402
from agents_md_tree_validation import (  # noqa: E402
    _ancestor_chain as _ancestor_chain,
)
from agents_md_tree_validation import _validate_topology  # noqa: E402
from agents_md_tree_validation import (  # noqa: E402
    _validate_tree as _validate_tree,
)
from agents_md_types import (  # noqa: E402
    MAX_INSTRUCTION_FILES,
    MAX_INSTRUCTION_TREE_BYTES,
    DomainProfileName,
    Finding,
    LanguageName,
    LayoutName,
    ParsedDocument,
)

PlatformName = Literal["generic", "codex"]
LEGACY_PROFILE_CHOICES = ("router", "application", "monorepo", "mcp-server", "safety-critical")
DOMAIN_PROFILE_CHOICES = ("router", "application", "mcp-server", "safety-critical")
LAYOUT_CHOICES = ("single", "monorepo")
LANGUAGE_CHOICES = ("en", "pl", "other")
PLATFORM_CHOICES = ("generic", "codex")


def normalize_selection(
    profile: str,
    layout: LayoutName | None = None,
) -> tuple[DomainProfileName, LayoutName]:
    """Normalize the legacy monorepo profile into independent domain/layout axes."""
    if profile == "monorepo":
        if layout not in (None, "monorepo"):
            raise ValueError("The legacy monorepo profile cannot be combined with --layout single.")
        return "application", "monorepo"
    if profile not in DOMAIN_PROFILE_CHOICES:
        raise ValueError(f"Unsupported domain profile: {profile}")
    return cast(DomainProfileName, profile), layout or "single"


def _read_document(
    path: Path,
    root: Path,
    language: LanguageName,
) -> tuple[ParsedDocument | None, int | None, Finding | None, int]:
    trusted, code, message = trusted_input(path, root)
    if code is not None or trusted is None:
        return None, None, Finding(str(path), "error", code or "input.invalid", 1, message or "Invalid input."), 0
    result = read_utf8_bounded(trusted)
    if result.code is not None or result.text is None:
        return (
            None,
            None,
            Finding(
                str(trusted),
                "error",
                result.code or "input.read-error",
                1,
                result.message or "Read failed.",
            ),
            result.byte_count,
        )
    document, unclosed_fence = parse_document(trusted, root, result.text, language)
    return document, unclosed_fence, None, result.byte_count


def validate_path(
    path: Path,
    profile: str = "application",
    repository_root: Path | None = None,
    layout: LayoutName | None = None,
    language: LanguageName = "en",
    platform: PlatformName = "generic",
    project_doc_max_bytes: int = CODEX_DEFAULT_PROJECT_DOC_MAX_BYTES,
    project_doc_fallback_filenames: Iterable[str] = (),
) -> list[Finding]:
    """Validate one AGENTS.md file inside a trusted repository boundary."""
    try:
        domain_profile, selected_layout = normalize_selection(profile, layout)
    except ValueError as error:
        return [Finding(str(path), "error", "input.invalid-selection", 1, str(error))]
    root, code, message = trusted_root(repository_root)
    if code is not None or root is None:
        return [
            Finding(
                str(repository_root or Path.cwd()),
                "error",
                code or "input.invalid-root",
                1,
                message or "Invalid root.",
            )
        ]
    document, unclosed_fence, finding, _ = _read_document(path, root, language)
    if finding is not None or document is None:
        return [finding] if finding is not None else []
    findings = _validate_document(document, domain_profile, selected_layout, language, root, unclosed_fence)
    if platform == "codex":
        findings.extend(_validate_codex_context(root, project_doc_fallback_filenames, project_doc_max_bytes))
    return sorted(findings, key=lambda item: (item.path, item.line, item.severity, item.code, item.message))


def validate_many_with_documents(
    paths: Iterable[Path],
    profile: str = "application",
    repository_root: Path | None = None,
    layout: LayoutName | None = None,
    language: LanguageName = "en",
    platform: PlatformName = "generic",
    project_doc_max_bytes: int = CODEX_DEFAULT_PROJECT_DOC_MAX_BYTES,
    project_doc_fallback_filenames: Iterable[str] = (),
) -> tuple[list[Finding], list[ParsedDocument]]:
    """Load and validate one bounded instruction tree exactly once."""
    try:
        domain_profile, selected_layout = normalize_selection(profile, layout)
    except ValueError as error:
        return (
            [
                Finding(
                    str(repository_root or Path.cwd()),
                    "error",
                    "input.invalid-selection",
                    1,
                    str(error),
                )
            ],
            [],
        )
    root, code, message = trusted_root(repository_root)
    if code is not None or root is None:
        return (
            [
                Finding(
                    str(repository_root or Path.cwd()),
                    "error",
                    code or "input.invalid-root",
                    1,
                    message or "Invalid root.",
                )
            ],
            [],
        )

    unique_paths = sorted(set(paths), key=lambda item: item.as_posix())
    if len(unique_paths) > MAX_INSTRUCTION_FILES:
        return (
            [
                Finding(
                    str(root),
                    "error",
                    "input.too-many-files",
                    1,
                    f"Instruction tree contains {len(unique_paths)} files; "
                    f"maximum supported count is {MAX_INSTRUCTION_FILES}.",
                )
            ],
            [],
        )

    findings: list[Finding] = []
    documents: list[ParsedDocument] = []
    total_bytes = 0
    for path in unique_paths:
        document, unclosed_fence, finding, byte_count = _read_document(path, root, language)
        total_bytes += byte_count
        if total_bytes > MAX_INSTRUCTION_TREE_BYTES:
            findings.append(
                Finding(
                    str(root),
                    "error",
                    "input.tree-too-large",
                    1,
                    f"Instruction tree exceeds {MAX_INSTRUCTION_TREE_BYTES} bytes.",
                )
            )
            break
        if finding is not None or document is None:
            if finding is not None:
                findings.append(finding)
            continue
        documents.append(document)
        findings.extend(_validate_document(document, domain_profile, selected_layout, language, root, unclosed_fence))

    findings.extend(_validate_topology(documents, root, selected_layout))
    if platform == "codex":
        findings.extend(_validate_codex_context(root, project_doc_fallback_filenames, project_doc_max_bytes))
    ordered = sorted(findings, key=lambda item: (item.path, item.line, item.severity, item.code, item.message))
    return ordered, documents


def validate_many(
    paths: Iterable[Path],
    profile: str = "application",
    repository_root: Path | None = None,
    layout: LayoutName | None = None,
    language: LanguageName = "en",
    platform: PlatformName = "generic",
    project_doc_max_bytes: int = CODEX_DEFAULT_PROJECT_DOC_MAX_BYTES,
    project_doc_fallback_filenames: Iterable[str] = (),
) -> list[Finding]:
    """Validate files together using the shared bounded instruction-tree load."""
    findings, _ = validate_many_with_documents(
        paths,
        profile,
        repository_root,
        layout,
        language,
        platform,
        project_doc_max_bytes,
        project_doc_fallback_filenames,
    )
    return findings


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="AGENTS.md files to validate")
    parser.add_argument(
        "--profile",
        choices=LEGACY_PROFILE_CHOICES,
        default="application",
        help="domain profile; legacy 'monorepo' maps to --layout monorepo --profile application",
    )
    parser.add_argument(
        "--layout",
        choices=LAYOUT_CHOICES,
        default=None,
        help="instruction layout, independent from the domain profile",
    )
    parser.add_argument(
        "--language",
        choices=LANGUAGE_CHOICES,
        default="en",
        help="natural-language contract used for lexical checks; use 'other' with explicit contract markers",
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path.cwd(),
        help="trusted root used to confine inputs and references (default: current directory)",
    )
    parser.add_argument(
        "--platform",
        choices=PLATFORM_CHOICES,
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
    parser.add_argument("--format", choices=("text", "json"), default="text", dest="output_format")
    return parser


def _render_text(findings: Sequence[Finding]) -> str:
    return "\n".join(f"{item.path}:{item.line}: {item.severity}: {item.code}: {item.message}" for item in findings)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line validator and return a process exit code."""
    args = _parser().parse_args(argv)
    findings = validate_many(
        args.paths,
        args.profile,
        args.repository_root,
        args.layout,
        args.language,
        args.platform,
        args.project_doc_max_bytes,
        args.project_doc_fallback_filename,
    )
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
