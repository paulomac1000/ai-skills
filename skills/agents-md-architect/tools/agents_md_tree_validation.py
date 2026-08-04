"""Instruction-tree inheritance and topology validation."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from agents_md_types import CommandRule, Directive, Finding, LayoutName, OwnershipRule, ParsedDocument


def _ancestor_chain(document: ParsedDocument, documents: Sequence[ParsedDocument]) -> tuple[ParsedDocument, ...]:
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


def _validate_tree(documents: Sequence[ParsedDocument], root: Path) -> list[Finding]:
    findings: list[Finding] = []
    root_document = next((document for document in documents if document.path == root / "AGENTS.md"), None)
    if root_document is None:
        findings.append(
            Finding(
                str(root),
                "error",
                "tree.missing-root",
                1,
                "Monorepo validation requires a root AGENTS.md.",
            )
        )
        return findings

    for child in documents:
        if child.path == root_document.path:
            continue
        ancestors = _ancestor_chain(child, documents) or (root_document,)

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
                        f"Explicit override of inherited {directive.category} rule requires platform and safety review.",
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
                        f"Command conflicts with inherited command at "
                        f"{inherited_source.relative_path}:{inherited_command.line}.",
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
                        f"Canonical owner conflicts with {inherited_source.relative_path}:{inherited_owner.line}.",
                    )
                )

        effective_sections: dict[str, tuple[ParsedDocument, str]] = {}
        inherited_lines: set[str] = set()
        for ancestor in ancestors:
            inherited_lines.update(ancestor.meaningful_lines)
            for heading, body in ancestor.sections.items():
                effective_sections[heading] = (ancestor, body)

        for heading, body in child.sections.items():
            inherited_section = effective_sections.get(heading)
            if inherited_section is None:
                continue
            source, inherited_body = inherited_section
            if body and inherited_body == body and len(body) >= 40:
                findings.append(
                    Finding(
                        str(child.path),
                        "warning",
                        "tree.duplicated-section",
                        1,
                        f"Section '{heading}' duplicates the effective inherited section from {source.relative_path}.",
                    )
                )

        if not child.meaningful_lines - inherited_lines:
            findings.append(
                Finding(
                    str(child.path),
                    "warning",
                    "tree.no-local-difference",
                    1,
                    "Nested AGENTS.md adds no material instruction beyond its full inherited chain.",
                )
            )
    return findings


def _validate_topology(documents: Sequence[ParsedDocument], root: Path, layout: LayoutName) -> list[Finding]:
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
