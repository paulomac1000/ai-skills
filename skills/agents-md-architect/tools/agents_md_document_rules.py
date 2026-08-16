"""Document-level validation for AGENTS.md."""

from __future__ import annotations

import re
from pathlib import Path

from agents_md_parse import (
    is_negated_ci_rule,
    is_negated_keyword_rule,
    iter_references,
    resolve_reference,
)
from agents_md_types import (
    ABSOLUTE_HOST_PATH,
    BARE_REFERENCE,
    CHANGELOG_HEADING,
    CONCEPT_PATTERNS_BY_LANGUAGE,
    CONTEXT_WAIVER,
    CONTRACT_MARKER,
    DOMAIN_NESTED_REQUIREMENTS,
    GENERIC_ADVICE,
    HEADING,
    KEYWORD_APPROVAL,
    LAYOUT_ROOT_REQUIREMENTS,
    NESTED_LAYOUT_REQUIREMENTS,
    PLACEHOLDER,
    POSITIVE_CI_GUARANTEE,
    PROFILE_REQUIREMENTS,
    VERSIONED_NAME,
    VOLATILE_COUNT,
    DomainProfileName,
    Finding,
    LanguageName,
    LayoutName,
    ParsedDocument,
    Severity,
    _normalize_heading,
    effective_budget,
)


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


def _active_context_waivers(document: ParsedDocument) -> tuple[tuple[int, str], ...]:
    """Return context waivers only from active Markdown lines outside fenced examples."""
    waivers: list[tuple[int, str]] = []
    for line_number, line in document.visible_lines:
        for match in CONTEXT_WAIVER.finditer(line):
            waivers.append((line_number, match.group("reason").strip()))
    return tuple(waivers)


def _contract_marker_bindings(
    document: ParsedDocument,
) -> tuple[frozenset[str], tuple[tuple[int, str], ...]]:
    """Bind contract markers to concrete non-empty H2 sections."""
    current_section: str | None = None
    section_content: dict[str, bool] = {}
    markers: list[tuple[int, str, str | None]] = []

    for line_number, line in document.visible_lines:
        heading = HEADING.fullmatch(line)
        if heading is not None:
            current_section = _normalize_heading(heading.group("title")) if len(heading.group("level")) == 2 else None
            if current_section is not None:
                section_content.setdefault(current_section, False)
            continue

        marker = CONTRACT_MARKER.fullmatch(line.strip())
        if marker is not None:
            markers.append((line_number, marker.group("name").casefold(), current_section))
            continue

        if current_section is not None and line.strip() and not line.strip().startswith("<!--"):
            section_content[current_section] = True

    valid: set[str] = set()
    invalid: list[tuple[int, str]] = []
    for line_number, name, section in markers:
        if section is None:
            invalid.append((line_number, f"Contract marker '{name}' must appear inside an H2 section."))
        elif not section_content.get(section, False):
            invalid.append((line_number, f"Contract marker '{name}' is attached to an empty H2 section."))
        else:
            valid.add(name)
    return frozenset(valid), tuple(invalid)


def _semantic_concept_present(document: ParsedDocument, concept: str, language: LanguageName) -> bool | None:
    """Validate prose for EN/PL and use bound markers only for other languages."""
    valid_markers, _invalid = _contract_marker_bindings(document)
    if language == "other":
        return True if concept in valid_markers else None

    patterns = CONCEPT_PATTERNS_BY_LANGUAGE[language]
    if patterns is None:
        return None
    semantic_lines = (line for _, line in document.visible_lines if CONTRACT_MARKER.fullmatch(line.strip()) is None)
    visible_text = "\n".join(semantic_lines)
    return any(pattern.search(visible_text) for pattern in patterns[concept])


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
            Finding(
                str(path),
                "error",
                "structure.unclosed-fence",
                unclosed_fence,
                "Fenced code block is not closed.",
            )
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

    _valid_contracts, invalid_contracts = _contract_marker_bindings(document)
    findings.extend(
        Finding(str(path), "error", "language.invalid-contract-marker", line_number, message)
        for line_number, message in invalid_contracts
    )

    waivers = _active_context_waivers(document)
    valid_waiver = len(waivers) == 1 and len(waivers[0][1]) >= 20
    if waivers and not valid_waiver:
        waiver_line = waivers[0][0]
        if len(waivers) > 1:
            message = "Exactly one active context-budget waiver is permitted per instruction file."
        else:
            message = "Context-budget waiver reason must contain at least 20 characters."
        findings.append(Finding(str(path), "error", "context.invalid-waiver", waiver_line, message))
    if not valid_waiver:
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
        present = _semantic_concept_present(document, concept, language)
        if present is True:
            continue
        if present is None:
            findings.append(
                Finding(
                    str(path),
                    "warning",
                    "language.semantic-unverified",
                    1,
                    f"Cannot verify the '{concept}' contract for language 'other'; add a marker inside "
                    "the matching non-empty H2 section.",
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
            if pattern.search(line):
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
                Finding(str(path), "error", "links.symlink", line_number, f"Reference contains a symlink: {target}")
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
                supported = (resolved.is_file() or resolved.is_dir()) if exists else False
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
            elif not supported:
                findings.append(
                    Finding(
                        str(path),
                        "error",
                        "links.unsupported-type",
                        line_number,
                        f"Reference must resolve to a regular file or directory: {target}",
                    )
                )

    return findings
