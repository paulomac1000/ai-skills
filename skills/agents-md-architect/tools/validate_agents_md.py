#!/usr/bin/env python3
"""Validate AGENTS.md files for scope, routing, safety, and instruction-tree drift."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import cast

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from agents_md_parse import (  # noqa: E402
    document_has_concept,
    is_negated_ci_rule,
    is_negated_keyword_rule,
    iter_references,
    parse_document,
    read_utf8_bounded,
    resolve_reference,
    trusted_input,
    trusted_root,
)
from agents_md_types import (  # noqa: E402
    ABSOLUTE_HOST_PATH,
    BARE_REFERENCE,
    CHANGELOG_HEADING,
    CONTEXT_WAIVER,
    DOMAIN_NESTED_REQUIREMENTS,
    GENERIC_ADVICE,
    HEADING,
    KEYWORD_APPROVAL,
    LAYOUT_ROOT_REQUIREMENTS,
    MAX_INSTRUCTION_FILES,
    MAX_INSTRUCTION_TREE_BYTES,
    NESTED_LAYOUT_REQUIREMENTS,
    PLACEHOLDER,
    POSITIVE_CI_GUARANTEE,
    PROFILE_REQUIREMENTS,
    VERSIONED_NAME,
    VOLATILE_COUNT,
    CommandRule,
    Directive,
    DomainProfileName,
    Finding,
    LanguageName,
    LayoutName,
    OwnershipRule,
    ParsedDocument,
    Severity,
    _normalize_heading,
    effective_budget,
)

LEGACY_PROFILE_CHOICES = ("router", "application", "monorepo", "mcp-server", "safety-critical")
DOMAIN_PROFILE_CHOICES = ("router", "application", "mcp-server", "safety-critical")
LAYOUT_CHOICES = ("single", "monorepo")
LANGUAGE_CHOICES = ("en", "pl", "other")


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


def _ordered_requirements(
    profile: DomainProfileName,
    layout: LayoutName,
    nested: bool,
) -> tuple[str, ...]:
    if nested and layout == "monorepo":
        values = (*NESTED_LAYOUT_REQUIREMENTS, *DOMAIN_NESTED_REQUIREMENTS[profile])
    else:
        values = (*PROFILE_REQUIREMENTS[profile], *LAYOUT_ROOT_REQUIREMENTS[layout])
    return tuple(dict.fromkeys(values))


def _validate_document(
    document: ParsedDocument,
    profile: DomainProfileName,
    layout: LayoutName,
    language: LanguageName,
    root: Path,
    unclosed_fence: int | None,
) -> list[Finding]:
    path = document.path
    text = document.text
    findings: list[Finding] = []
    if unclosed_fence is not None:
        findings.append(
            Finding(str(path), "error", "structure.unclosed-fence", unclosed_fence, "Fenced code block is not closed.")
        )

    headings: list[tuple[int, int, str]] = []
    for line_number, line in document.visible_lines:
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

    waiver = CONTEXT_WAIVER.search(text)
    if waiver is not None and len(waiver.group("reason").strip()) < 20:
        findings.append(
            Finding(
                str(path),
                "error",
                "context.invalid-waiver",
                1,
                "Context-budget waiver reason must contain at least 20 characters.",
            )
        )
    if waiver is None:
        line_budget, byte_budget = effective_budget(profile, layout)
        line_count = len(text.splitlines())
        byte_count = len(text.encode("utf-8"))
        if line_count > line_budget or byte_count > byte_budget:
            findings.append(
                Finding(
                    str(path),
                    "warning",
                    "context.review-budget",
                    1,
                    f"{layout}/{profile} contract has {line_count} lines and {byte_count} UTF-8 bytes; "
                    f"review the {line_budget}-line/{byte_budget}-byte budget or add a reasoned waiver.",
                )
            )

    nested = layout == "monorepo" and path.parent != root
    for concept in _ordered_requirements(profile, layout, nested):
        present = document_has_concept(document, concept, language)
        if present is True:
            continue
        if present is None:
            findings.append(
                Finding(
                    str(path),
                    "warning",
                    "language.semantic-unverified",
                    1,
                    f"Cannot verify the '{concept}' contract for language 'other'; add "
                    f"<!-- agents-md: contract {concept} -->.",
                )
            )
            continue
        findings.append(
            Finding(
                str(path),
                "error",
                f"profile.missing-{concept}",
                1,
                f"The {layout}/{profile} contract requires an explicit {concept.replace('-', ' ')} contract.",
            )
        )

    for line_number, line in document.visible_lines:
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
                GENERIC_ADVICE,
                "warning",
                "content.generic-advice",
                "Replace generic advice with a project-specific boundary or remove it.",
            ),
        )
        for pattern, severity, code, message in checks:
            match = pattern.search(line)
            if match:
                findings.append(Finding(str(path), severity, code, line_number, message))

        if KEYWORD_APPROVAL.search(line) and not is_negated_keyword_rule(line):
            findings.append(
                Finding(
                    str(path),
                    "error",
                    "safety.keyword-approval",
                    line_number,
                    "Human approval must not be determined by keyword matching.",
                )
            )
        if POSITIVE_CI_GUARANTEE.search(line) and not is_negated_ci_rule(line):
            findings.append(
                Finding(
                    str(path),
                    "error",
                    "evidence.false-ci-guarantee",
                    line_number,
                    "Local validation must not be described as a guarantee of hosted CI.",
                )
            )

    for line_number, target in iter_references(document.visible_lines):
        resolved, issue = resolve_reference(path, root, target)
        if resolved is None:
            continue
        if issue == "outside":
            findings.append(
                Finding(
                    str(path),
                    "error",
                    "links.outside-repository",
                    line_number,
                    f"Reference escapes the repository boundary: {target}",
                )
            )
        elif issue == "symlink":
            findings.append(
                Finding(
                    str(path),
                    "error",
                    "links.symlink",
                    line_number,
                    f"Reference contains a symlink: {target}",
                )
            )
        elif issue == "unreadable":
            findings.append(
                Finding(
                    str(path),
                    "error",
                    "links.unreadable",
                    line_number,
                    f"Reference could not be inspected safely: {target}",
                )
            )
        else:
            try:
                exists = resolved.exists()
                regular = resolved.is_file() if exists else False
            except (OSError, RuntimeError):
                findings.append(
                    Finding(
                        str(path),
                        "error",
                        "links.unreadable",
                        line_number,
                        f"Reference could not be inspected safely: {target}",
                    )
                )
                continue
            if not exists:
                findings.append(
                    Finding(
                        str(path),
                        "error",
                        "links.missing",
                        line_number,
                        f"Referenced path does not exist: {target}",
                    )
                )
            elif not regular:
                findings.append(
                    Finding(
                        str(path),
                        "error",
                        "links.not-file",
                        line_number,
                        f"Reference must resolve to a regular file: {target}",
                    )
                )

    return findings


def _ancestor_chain(
    document: ParsedDocument,
    documents: Sequence[ParsedDocument],
) -> tuple[ParsedDocument, ...]:
    """Return inherited instruction documents from root to nearest parent."""
    return tuple(
        sorted(
            (
                other
                for other in documents
                if other.path != document.path and other.path.parent in document.path.parents
            ),
            key=lambda item: len(item.path.parent.parts),
        )
    )


def _nearest_parent(
    document: ParsedDocument,
    documents: Sequence[ParsedDocument],
    root: Path,
) -> ParsedDocument | None:
    ancestors = _ancestor_chain(document, documents)
    if ancestors:
        return ancestors[-1]
    root_document = next((other for other in documents if other.path == root / "AGENTS.md"), None)
    return root_document if root_document and root_document.path != document.path else None


def _validate_tree(documents: Sequence[ParsedDocument], root: Path) -> list[Finding]:
    findings: list[Finding] = []
    root_document = next((document for document in documents if document.path == root / "AGENTS.md"), None)
    if root_document is None:
        findings.append(
            Finding(str(root), "error", "tree.missing-root", 1, "Monorepo validation requires a root AGENTS.md.")
        )
        return findings

    for child in documents:
        if child.path == root_document.path:
            continue
        ancestors = _ancestor_chain(child, documents)
        parent = ancestors[-1] if ancestors else root_document

        inherited: dict[str, tuple[ParsedDocument, Directive]] = {}
        for ancestor in ancestors:
            for item in ancestor.directives:
                inherited[item.category] = (ancestor, item)
        for directive in child.directives:
            inherited_entry = inherited.get(directive.category)
            if inherited_entry is None:
                continue
            inherited_source, inherited_directive = inherited_entry
            if inherited_directive.polarity == directive.polarity:
                continue
            if directive.explicit_override:
                findings.append(
                    Finding(
                        str(child.path),
                        "warning",
                        "tree.explicit-override",
                        directive.line,
                        (
                            f"Explicit override of inherited {directive.category} rule "
                            "requires platform and safety review."
                        ),
                    )
                )
            else:
                findings.append(
                    Finding(
                        str(child.path),
                        "error",
                        "tree.conflicting-rule",
                        directive.line,
                        f"Rule conflicts with inherited {directive.category} directive "
                        f"at {inherited_source.relative_path}:{inherited_directive.line}.",
                    )
                )

        inherited_commands: dict[str, tuple[ParsedDocument, CommandRule]] = {}
        for ancestor in ancestors:
            for command_rule in ancestor.commands:
                inherited_commands[command_rule.key] = (ancestor, command_rule)
        for command in child.commands:
            inherited_command_entry = inherited_commands.get(command.key)
            if inherited_command_entry is None:
                continue
            inherited_source, inherited_command = inherited_command_entry
            if inherited_command.command != command.command and not command.explicit_local:
                findings.append(
                    Finding(
                        str(child.path),
                        "error",
                        "tree.conflicting-command",
                        command.line,
                        (
                            "Command conflicts with inherited command at "
                            f"{inherited_source.relative_path}:{inherited_command.line}."
                        ),
                    )
                )

        inherited_ownership: dict[str, tuple[ParsedDocument, OwnershipRule]] = {}
        for ancestor in ancestors:
            for ownership_rule in ancestor.ownership:
                inherited_ownership[ownership_rule.key] = (ancestor, ownership_rule)
        for owner in child.ownership:
            inherited_owner_entry = inherited_ownership.get(owner.key)
            if inherited_owner_entry is None:
                continue
            inherited_source, inherited_owner = inherited_owner_entry
            if inherited_owner.target != owner.target and not owner.explicit_local:
                findings.append(
                    Finding(
                        str(child.path),
                        "error",
                        "tree.conflicting-owner",
                        owner.line,
                        (f"Canonical owner conflicts with {inherited_source.relative_path}:{inherited_owner.line}."),
                    )
                )

        for heading, body in child.sections.items():
            inherited_body = parent.sections.get(heading)
            if body and inherited_body == body and len(body) >= 40:
                findings.append(
                    Finding(
                        str(child.path),
                        "warning",
                        "tree.duplicated-section",
                        1,
                        f"Section '{heading}' duplicates the inherited section from {parent.relative_path}.",
                    )
                )

        unique_lines = child.meaningful_lines - parent.meaningful_lines
        if not unique_lines:
            findings.append(
                Finding(
                    str(child.path),
                    "warning",
                    "tree.no-local-difference",
                    1,
                    "Nested AGENTS.md adds no material local instruction.",
                )
            )
    return findings


def _validate_topology(
    documents: Sequence[ParsedDocument],
    root: Path,
    layout: LayoutName,
) -> list[Finding]:
    root_document = next((document for document in documents if document.path == root / "AGENTS.md"), None)
    if root_document is None:
        return [
            Finding(
                str(root),
                "error",
                "tree.missing-root",
                1,
                f"The {layout} layout requires a root AGENTS.md.",
            )
        ]
    if layout == "single":
        return [
            Finding(
                str(document.path),
                "error",
                "tree.unexpected-nested",
                1,
                "The single layout permits only the root AGENTS.md.",
            )
            for document in documents
            if document.path != root_document.path
        ]
    return _validate_tree(documents, root)


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
            Finding(str(trusted), "error", result.code or "input.read-error", 1, result.message or "Read failed."),
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
    return sorted(findings, key=lambda item: (item.path, item.line, item.severity, item.code, item.message))


def validate_many_with_documents(
    paths: Iterable[Path],
    profile: str = "application",
    repository_root: Path | None = None,
    layout: LayoutName | None = None,
    language: LanguageName = "en",
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
                    (
                        f"Instruction tree contains {len(unique_paths)} files; "
                        f"maximum supported count is {MAX_INSTRUCTION_FILES}."
                    ),
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
    ordered = sorted(findings, key=lambda item: (item.path, item.line, item.severity, item.code, item.message))
    return ordered, documents


def validate_many(
    paths: Iterable[Path],
    profile: str = "application",
    repository_root: Path | None = None,
    layout: LayoutName | None = None,
    language: LanguageName = "en",
) -> list[Finding]:
    """Validate files together using the shared bounded instruction-tree load."""
    findings, _ = validate_many_with_documents(paths, profile, repository_root, layout, language)
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
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    parser.add_argument("--format", choices=("text", "json"), default="text", dest="output_format")
    return parser


def _render_text(findings: Sequence[Finding]) -> str:
    return "\n".join(f"{item.path}:{item.line}: {item.severity}: {item.code}: {item.message}" for item in findings)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line validator and return a process exit code."""
    args = _parser().parse_args(argv)
    findings = validate_many(args.paths, args.profile, args.repository_root, args.layout, args.language)
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
