"""Patch full-ancestor directive inheritance."""

from __future__ import annotations

from textwrap import dedent, indent

from .common import read, replace_between, replace_once


def stage() -> str:
    path = "skills/agents-md-architect/tools/validate_agents_md.py"
    text = read(path)
    text = replace_once(
        text,
        "    DomainProfileName,\n    Finding,\n",
        "    Directive,\n    DomainProfileName,\n    Finding,\n",
        label=f"{path} Directive import",
    )
    text = replace_between(
        text,
        "def _nearest_parent(\n",
        "def _validate_tree(documents: Sequence[ParsedDocument], root: Path) -> list[Finding]:\n",
        dedent(
            '''\
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


            '''
        ),
        label=f"{path} ancestor helpers",
    )
    old = indent(
        dedent(
            '''\
            parent = _nearest_parent(child, documents, root) or root_document

            inherited = {item.category: item for item in parent.directives}
            for directive in child.directives:
                inherited_directive = inherited.get(directive.category)
                if inherited_directive is None or inherited_directive.polarity == directive.polarity:
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
                            f"at {parent.relative_path}:{inherited_directive.line}.",
                        )
                    )

            '''
        ),
        "        ",
    )
    new = indent(
        dedent(
            '''\
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

            '''
        ),
        "        ",
    )
    text = replace_once(text, old, new, label=f"{path} full ancestor directives")
    return text
