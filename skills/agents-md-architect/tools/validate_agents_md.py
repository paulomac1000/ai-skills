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

try:
    from .agents_md_parse import (
        _has_concept,
        _is_negated_ci_rule,
        _is_negated_keyword_rule,
        _iter_references,
        _parse_document,
        _resolve_reference,
        _trusted_input,
        _trusted_root,
    )
    from .agents_md_types import (
        ABSOLUTE_HOST_PATH,
        BARE_REFERENCE,
        CHANGELOG_HEADING,
        CONTEXT_WAIVER,
        GENERIC_ADVICE,
        HEADING,
        KEYWORD_APPROVAL,
        NESTED_MONOREPO_REQUIREMENTS,
        PLACEHOLDER,
        POSITIVE_CI_GUARANTEE,
        PROFILE_BUDGETS,
        PROFILE_REQUIREMENTS,
        VERSIONED_NAME,
        VOLATILE_COUNT,
        Finding,
        ParsedDocument,
        ProfileName,
        Severity,
        _normalize_heading,
    )
except ImportError:  # pragma: no cover - direct script execution
    from agents_md_parse import (
        _has_concept,
        _is_negated_ci_rule,
        _is_negated_keyword_rule,
        _iter_references,
        _parse_document,
        _resolve_reference,
        _trusted_input,
        _trusted_root,
    )
    from agents_md_types import (
        ABSOLUTE_HOST_PATH,
        BARE_REFERENCE,
        CHANGELOG_HEADING,
        CONTEXT_WAIVER,
        GENERIC_ADVICE,
        HEADING,
        KEYWORD_APPROVAL,
        NESTED_MONOREPO_REQUIREMENTS,
        PLACEHOLDER,
        POSITIVE_CI_GUARANTEE,
        PROFILE_BUDGETS,
        PROFILE_REQUIREMENTS,
        VERSIONED_NAME,
        VOLATILE_COUNT,
        Finding,
        ParsedDocument,
        ProfileName,
        Severity,
        _normalize_heading,
    )


def _validate_document(
    document: ParsedDocument,
    profile: ProfileName,
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
        line_budget, byte_budget = PROFILE_BUDGETS[profile]
        line_count = len(text.splitlines())
        byte_count = len(text.encode("utf-8"))
        if line_count > line_budget or byte_count > byte_budget:
            findings.append(
                Finding(
                    str(path),
                    "warning",
                    "context.review-budget",
                    1,
                    f"{profile} profile has {line_count} lines and {byte_count} UTF-8 bytes; "
                    f"review the {line_budget}-line/{byte_budget}-byte budget or add a reasoned waiver.",
                )
            )

    visible_text = "\n".join(line for _, line in document.visible_lines)
    is_nested_monorepo = profile == "monorepo" and path.parent != root
    requirements = NESTED_MONOREPO_REQUIREMENTS if is_nested_monorepo else PROFILE_REQUIREMENTS[profile]
    for concept in requirements:
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
                "Replace generic advice with a repository-specific command, invariant, or boundary.",
            ),
        )
        for pattern, severity, code, message in checks:
            if pattern.search(line):
                findings.append(Finding(str(path), severity, code, line_number, message))
        if KEYWORD_APPROVAL.search(line) and not _is_negated_keyword_rule(line):
            findings.append(
                Finding(
                    str(path),
                    "error",
                    "safety.keyword-approval",
                    line_number,
                    "Keyword matching is not a trusted human-approval mechanism.",
                )
            )
        if POSITIVE_CI_GUARANTEE.search(line) and not _is_negated_ci_rule(line):
            findings.append(
                Finding(
                    str(path),
                    "error",
                    "evidence.false-ci-guarantee",
                    line_number,
                    "Local validation must not be described as a guarantee of hosted CI.",
                )
            )

    for line_number, target in _iter_references(document.visible_lines):
        resolved, issue = _resolve_reference(path, root, target)
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
        elif not resolved.exists():
            findings.append(
                Finding(
                    str(path),
                    "error",
                    "links.missing",
                    line_number,
                    f"Referenced path does not exist: {target}",
                )
            )

    return findings


def _nearest_parent(
    document: ParsedDocument,
    documents: Sequence[ParsedDocument],
    root: Path,
) -> ParsedDocument | None:
    candidates = [
        other
        for other in documents
        if other.path != document.path
        and other.path.parent in document.path.parents
        and other.path.parent != document.path.parent
    ]
    if not candidates:
        root_document = next((other for other in documents if other.path == root / "AGENTS.md"), None)
        return root_document if root_document and root_document.path != document.path else None
    return max(candidates, key=lambda item: len(item.path.parent.parts))


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
        parent = _nearest_parent(child, documents, root)
        if parent is None:
            findings.append(
                Finding(str(child.path), "error", "tree.orphan", 1, "Nested AGENTS.md has no instruction ancestor.")
            )
            continue

        parent_directives = {item.category: item for item in parent.directives}
        for directive in child.directives:
            inherited = parent_directives.get(directive.category)
            if inherited is None or inherited.polarity == directive.polarity:
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
                        (
                            f"Rule conflicts with inherited {directive.category} directive "
                            f"at {parent.relative_path}:{inherited.line}."
                        ),
                    )
                )

        parent_commands = {item.key: item for item in parent.commands}
        for command in child.commands:
            inherited = parent_commands.get(command.key)
            if inherited and inherited.command != command.command and not command.explicit_local:
                findings.append(
                    Finding(
                        str(child.path),
                        "error",
                        "tree.conflicting-command",
                        command.line,
                        f"Command conflicts with inherited command at {parent.relative_path}:{inherited.line}.",
                    )
                )

        parent_ownership = {item.key: item for item in parent.ownership}
        for owner in child.ownership:
            inherited = parent_ownership.get(owner.key)
            if inherited and inherited.target != owner.target and not owner.explicit_local:
                findings.append(
                    Finding(
                        str(child.path),
                        "error",
                        "tree.conflicting-owner",
                        owner.line,
                        f"Canonical owner conflicts with {parent.relative_path}:{inherited.line}.",
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


def validate_path(path: Path, profile: ProfileName, repository_root: Path | None = None) -> list[Finding]:
    """Validate one AGENTS.md file inside a trusted repository boundary."""
    root, root_finding = _trusted_root(repository_root)
    if root_finding is not None or root is None:
        return [root_finding] if root_finding is not None else []
    trusted, input_finding = _trusted_input(path, root)
    if input_finding is not None or trusted is None:
        return [input_finding] if input_finding is not None else []
    text = trusted.read_text(encoding="utf-8")
    document, unclosed_fence = _parse_document(trusted, root, text)
    findings = _validate_document(document, profile, root, unclosed_fence)
    return sorted(findings, key=lambda item: (item.path, item.line, item.severity, item.code, item.message))


def validate_many(paths: Iterable[Path], profile: ProfileName, repository_root: Path | None = None) -> list[Finding]:
    """Validate files together and, for monorepos, evaluate inheritance and duplication."""
    root, root_finding = _trusted_root(repository_root)
    if root_finding is not None or root is None:
        return [root_finding] if root_finding is not None else []

    findings: list[Finding] = []
    documents: list[ParsedDocument] = []
    for path in sorted(paths):
        trusted, input_finding = _trusted_input(path, root)
        if input_finding is not None or trusted is None:
            if input_finding is not None:
                findings.append(input_finding)
            continue
        text = trusted.read_text(encoding="utf-8")
        document, unclosed_fence = _parse_document(trusted, root, text)
        documents.append(document)
        findings.extend(_validate_document(document, profile, root, unclosed_fence))

    if profile == "monorepo" and documents:
        findings.extend(_validate_tree(documents, root))
    return sorted(findings, key=lambda item: (item.path, item.line, item.severity, item.code, item.message))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="AGENTS.md files to validate")
    parser.add_argument(
        "--profile",
        choices=tuple(PROFILE_REQUIREMENTS),
        default="application",
        help="instruction profile applied to all selected files",
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
    return "\n".join(
        f"{item.path}:{item.line}: {item.severity}: {item.code}: {item.message}" for item in findings
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line validator and return a process exit code."""
    args = _parser().parse_args(argv)
    profile = cast(ProfileName, args.profile)
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
