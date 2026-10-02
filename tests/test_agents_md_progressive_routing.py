"""Trigger-safe progressive routing regressions for the AGENTS.md repository audit."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills/agents-md-architect/tools"
sys.path.insert(0, str(TOOLS))

import audit_agents_md as audit_module  # noqa: E402


def _write_base(repository: Path) -> None:
    (repository / "docs").mkdir(parents=True, exist_ok=True)
    (repository / "scripts").mkdir(parents=True, exist_ok=True)
    (repository / "scripts/ci.py").write_text("print('gate')\n", encoding="utf-8")
    (repository / "Makefile").write_text("migrate:\n\t@echo migrate\n", encoding="utf-8")
    (repository / "AGENTS.md").write_text(
        """# AGENTS.md

These instructions apply to this repository.

## Scope

These instructions apply to the repository.

## Commands and verification

- Full gate: `python scripts/ci.py`

## Architecture boundaries

Generated files must not be edited directly.

## Safety boundaries

Secrets must not be committed. Destructive writes require explicit authorization and rollback.

## Definition of done

Report the exact revision, full gate, skipped checks, and residual risk.
""",
        encoding="utf-8",
    )


def _append(repository: Path, text: str) -> None:
    path = repository / "AGENTS.md"
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


def _codes(findings: list[audit_module.AuditFinding]) -> set[str]:
    return {finding.code for finding in findings}


def _write_conditional_owner(repository: Path, relative: str, body: str = "") -> Path:
    path = repository / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "<!-- agents-md: conditional-owner -->\n\n# Conditional procedure\n\n" + body,
        encoding="utf-8",
    )
    return path


def test_mechanical_route_binds_trigger_owner_and_invocation_owner(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(tmp_path, "docs/migrations.md", "Use the migration workflow.\n")
    _append(
        tmp_path,
        """
## Migration routing

<!-- agents-md: route owner="docs/migrations.md" when="before changing database schema" purpose="rollback and compatibility" invoke-owner="Makefile" -->
- Before changing database schema, read [the migration contract](docs/migrations.md) for rollback and compatibility.
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert not any(finding.code.startswith("routing.") for finding in findings)


def test_conditional_owner_with_only_internal_trigger_is_unreachable(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(
        tmp_path,
        "docs/recovery.md",
        '<!-- agents-md: route owner="docs/recovery.md" when="after failure" purpose="recovery" -->\n',
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "routing.trigger-unreachable" in _codes(findings)


def test_duplicate_trigger_owners_are_rejected(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(tmp_path, "docs/release.md")
    _append(
        tmp_path,
        """
## Release routing

<!-- agents-md: route owner="docs/release.md" when="when candidate is ready" purpose="release gate" -->
- When the candidate is ready, read [release](docs/release.md) for the release gate.
<!-- agents-md: route owner="docs/release.md" when="before publication" purpose="publication gate" -->
- Before publication, read [release](docs/release.md) for the publication gate.
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "routing.trigger-owner-duplicate" in _codes(findings)


def test_stale_route_and_invocation_owners_fail_closed(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _append(
        tmp_path,
        """
## Migration routing

<!-- agents-md: route owner="docs/missing.md" when="before migration" purpose="migration safety" invoke-owner="scripts/missing.py" -->
- Before migration, use the governed migration route.
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert {"routing.route-owner-missing", "routing.invocation-owner-missing"} <= _codes(findings)


def test_route_target_must_opt_in_as_conditional_owner(tmp_path: Path) -> None:
    _write_base(tmp_path)
    (tmp_path / "docs/release.md").write_text("# Release\n", encoding="utf-8")
    _append(
        tmp_path,
        """
## Release routing

<!-- agents-md: route owner="docs/release.md" when="before release" purpose="release checks" -->
- Before release, read [release](docs/release.md) for release checks.
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "routing.conditional-owner-marker-missing" in _codes(findings)


def test_extraction_shrinks_always_loaded_surface_without_duplicate_procedure(tmp_path: Path) -> None:
    _write_base(tmp_path)
    path = tmp_path / "AGENTS.md"
    procedure = (
        "Before every migration, inspect backward and forward compatibility for each affected consumer; "
        "capture the pre-change schema; create and review rollback SQL; stage the candidate schema in an isolated "
        "environment; run migration, compatibility, and rollback tests; verify that application code tolerates the "
        "required rollout order; document irreversible operations and recovery ownership; bind the migration result "
        "to the candidate revision; and record the evidence required by the release gate."
    )
    original = path.read_text(encoding="utf-8") + "\n## Database migration procedure\n\n" + procedure + "\n"
    path.write_text(original, encoding="utf-8")
    _write_conditional_owner(tmp_path, "docs/migrations.md", procedure + "\n")
    compact = path.read_text(encoding="utf-8").replace(
        "\n## Database migration procedure\n\n" + procedure + "\n",
        (
            "\n## Database migration routing\n\n"
            '<!-- agents-md: route owner="docs/migrations.md" when="before changing database schema" '
            'purpose="rollback and compatibility" invoke-owner="Makefile" -->\n'
            "- Before changing database schema, read [the migration contract](docs/migrations.md); "
            "do not mutate schema until that contract is loaded.\n"
        ),
    )
    path.write_text(compact, encoding="utf-8")

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert not any(finding.code.startswith("routing.") for finding in findings)
    assert len(compact.encode("utf-8")) < len(original.encode("utf-8"))
    assert procedure not in compact
    assert procedure in (tmp_path / "docs/migrations.md").read_text(encoding="utf-8")


def test_audit_json_reports_static_routing_proof_boundary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_base(tmp_path)
    result = audit_module.main(
        [
            str(tmp_path),
            "--profile",
            "application",
            "--layout",
            "single",
            "--language",
            "en",
            "--format",
            "json",
        ]
    )
    assert result == 0
    output = json.loads(capsys.readouterr().out)
    assert "semantic trigger timing" in output["proof_boundary"]
    assert "platform loading" in output["proof_boundary"]


def test_route_and_invocation_owner_reject_absolute_paths(tmp_path: Path) -> None:
    _write_base(tmp_path)
    owner = _write_conditional_owner(tmp_path, "docs/migrations.md")
    absolute_owner = owner.resolve().as_posix()
    absolute_invocation = (tmp_path / "Makefile").resolve().as_posix()
    _append(
        tmp_path,
        f"""
## Migration routing

<!-- agents-md: route owner="{absolute_owner}" when="before migration" purpose="migration safety" invoke-owner="{absolute_invocation}" -->
- Before migration, read [{absolute_owner}]({absolute_owner}) for migration safety.
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert {"routing.route-owner-absolute", "routing.invocation-owner-absolute"} <= _codes(findings)


@pytest.mark.parametrize(
    "payload",
    (
        b"\xff\xfe\x00not-utf8",
        ("<!-- agents-md: conditional-owner -->\n" + "x" * (256 * 1024)).encode("utf-8"),
    ),
)
def test_unreadable_conditional_owner_fails_closed_without_false_missing_marker(
    tmp_path: Path,
    payload: bytes,
) -> None:
    _write_base(tmp_path)
    owner = tmp_path / "docs" / "unreadable.md"
    owner.write_bytes(payload)
    _append(
        tmp_path,
        """
## Recovery routing

<!-- agents-md: route owner="docs/unreadable.md" when="after failure" purpose="recovery" -->
- After failure, read [the recovery owner](docs/unreadable.md) before recovery work.
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "routing.conditional-owner-unreadable" in _codes(findings)
    assert "routing.conditional-owner-marker-missing" not in _codes(findings)


def test_route_marker_without_readable_owner_link_is_not_reachable(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(tmp_path, "docs/recovery.md")
    _append(
        tmp_path,
        """
## Recovery routing

<!-- agents-md: route owner="docs/recovery.md" when="after failure" purpose="recovery" -->
- Recovery work requires the governed procedure.
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert {"routing.route-prose-missing", "routing.trigger-unreachable"} <= _codes(findings)


def test_mechanical_conditional_owner_is_markdown_only(tmp_path: Path) -> None:
    _write_base(tmp_path)
    (tmp_path / "docs" / "runbook.rst").write_text(
        "<!-- agents-md: conditional-owner -->\nRunbook\n=======\n",
        encoding="utf-8",
    )
    _append(
        tmp_path,
        """
## Recovery routing

<!-- agents-md: route owner="docs/runbook.rst" when="after failure" purpose="recovery" -->
- After failure, read [the runbook](docs/runbook.rst) before recovery work.
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "routing.route-owner-format" in _codes(findings)


def test_generated_readable_projection_does_not_duplicate_control_marker(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(tmp_path, "docs/release.md")
    _append(
        tmp_path,
        """
## Release routing

<!-- agents-md: route owner="docs/release.md" when="before release" purpose="release safety" -->
- Before release, read [the release owner](docs/release.md) for release safety.
""",
    )
    generated = tmp_path / "generated"
    generated.mkdir()
    (generated / "AGENTS.md").write_text(
        "# Generated route view\n\n"
        "This file is derived. Before release, read [the release owner](../docs/release.md).\n",
        encoding="utf-8",
    )

    _, findings = audit_module.audit(tmp_path, "application", "monorepo", "en")
    assert "routing.trigger-owner-duplicate" not in _codes(findings)


def test_nested_route_metadata_is_root_relative_while_prose_link_is_document_relative(
    tmp_path: Path,
) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(tmp_path, "docs/release.md")
    nested = tmp_path / "packages" / "api"
    nested.mkdir(parents=True)
    (nested / "AGENTS.md").write_text(
        """# API instructions

## Scope

These instructions apply to packages/api.

## Commands and verification

- Full gate: `python ../../scripts/ci.py`

## Architecture boundaries

Generated files must not be edited directly.

## Safety boundaries

Secrets must not be committed. Destructive writes require authorization and rollback.

## Definition of done

Report exact revision, verification, skipped checks, and residual risk.

## Release routing

<!-- agents-md: route owner="docs/release.md" when="before release" purpose="release safety" -->
- Before release, read [the release owner](../../docs/release.md) for release safety.
""",
        encoding="utf-8",
    )

    _, findings = audit_module.audit(tmp_path, "application", "monorepo", "en")
    assert not any(finding.code.startswith("routing.") for finding in findings)


def test_markdown_extension_conditional_owner_is_scanned(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(tmp_path, "docs/recovery.markdown")
    _append(
        tmp_path,
        """
## Recovery routing

<!-- agents-md: route owner="docs/recovery.markdown" when="after failure" purpose="recovery" -->
- After failure, read [the recovery owner](docs/recovery.markdown) before recovery work.
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert not any(finding.code.startswith("routing.") for finding in findings)


def test_wrapped_route_prose_resolves_owner_link_from_same_block(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(tmp_path, "docs/migrations.md")
    _append(
        tmp_path,
        """
## Migration routing

<!-- agents-md: route owner="docs/migrations.md" when="before migration" purpose="migration safety" -->
- Before migration, load the governed owner
  [from the migration contract](docs/migrations.md) before changing schema.
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert not any(finding.code.startswith("routing.") for finding in findings)


def test_reference_style_route_link_uses_document_definitions(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(tmp_path, "docs/migrations.md")
    _append(
        tmp_path,
        """
## Migration routing

<!-- agents-md: route owner="docs/migrations.md" when="before migration" purpose="migration safety" -->
- Before migration, read [the migration owner][migration-owner].

[migration-owner]: docs/migrations.md
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert not any(finding.code.startswith("routing.") for finding in findings)


def test_later_paragraph_owner_link_does_not_satisfy_route_prose(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(tmp_path, "docs/migrations.md")
    _append(
        tmp_path,
        """
## Migration routing

<!-- agents-md: route owner="docs/migrations.md" when="before migration" purpose="migration safety" -->
- Before migration, follow the governed migration procedure.

This later paragraph links [the migration owner](docs/migrations.md).
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert {"routing.route-prose-missing", "routing.trigger-unreachable"} <= _codes(findings)


def test_percent_encoded_absolute_route_owner_is_rejected(tmp_path: Path) -> None:
    _write_base(tmp_path)
    owner = _write_conditional_owner(tmp_path, "docs/migrations.md").resolve().as_posix()
    encoded_owner = owner.replace("/", "%2F")
    _append(
        tmp_path,
        f"""
## Migration routing

<!-- agents-md: route owner="{encoded_owner}" when="before migration" purpose="migration safety" -->
- Before migration, read [the migration owner]({owner}) for migration safety.
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "routing.route-owner-absolute" in _codes(findings)


@pytest.mark.parametrize(
    "payload",
    (
        b"\xff\xfe\x00unrelated-invalid-utf8",
        ("# Unrelated\n\n" + "x" * (256 * 1024)).encode("utf-8"),
    ),
)
def test_unrelated_unreadable_markdown_does_not_block_routing_audit(
    tmp_path: Path,
    payload: bytes,
) -> None:
    _write_base(tmp_path)
    (tmp_path / "docs" / "unrelated.md").write_bytes(payload)

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "routing.conditional-owner-unreadable" not in _codes(findings)


def test_readable_unrouted_conditional_owner_is_still_reported_as_orphan(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(tmp_path, "docs/orphan.md")

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "routing.trigger-unreachable" in _codes(findings)


def test_multiline_html_comment_link_does_not_make_route_reachable(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(tmp_path, "docs/recovery.md")
    _append(
        tmp_path,
        """
## Recovery routing

<!-- agents-md: route owner="docs/recovery.md" when="after failure" purpose="recovery" -->
- After failure, follow the governed recovery procedure.
<!--
[hidden recovery owner](docs/recovery.md)
-->
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert {"routing.route-prose-missing", "routing.trigger-unreachable"} <= _codes(findings)


def test_route_marker_inside_multiline_html_comment_is_not_live(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(tmp_path, "docs/recovery.md")
    _append(
        tmp_path,
        """
## Disabled routing example

<!--
<!-- agents-md: route owner="docs/recovery.md" when="after failure" purpose="recovery" -->
- After failure, read [the recovery owner](docs/recovery.md).
-->
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "routing.trigger-unreachable" in _codes(findings)
    assert "routing.route-prose-missing" not in _codes(findings)


def test_indented_code_route_example_is_not_live(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(tmp_path, "docs/recovery.md")
    _append(
        tmp_path,
        """
## Routing example

    <!-- agents-md: route owner="docs/recovery.md" when="after failure" purpose="recovery" -->
    - After failure, read [the recovery owner](docs/recovery.md).
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "routing.trigger-unreachable" in _codes(findings)
    assert "routing.route-prose-missing" not in _codes(findings)


@pytest.mark.parametrize(
    "owner_body",
    (
        "    <!-- agents-md: conditional-owner -->\n",
        "<!--\n<!-- agents-md: conditional-owner -->\n-->\n",
    ),
)
def test_hidden_conditional_owner_marker_does_not_satisfy_route(
    tmp_path: Path,
    owner_body: str,
) -> None:
    _write_base(tmp_path)
    owner = tmp_path / "docs" / "recovery.md"
    owner.write_text("# Recovery\n\n" + owner_body, encoding="utf-8")
    _append(
        tmp_path,
        """
## Recovery routing

<!-- agents-md: route owner="docs/recovery.md" when="after failure" purpose="recovery" -->
- After failure, read [the recovery owner](docs/recovery.md).
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "routing.conditional-owner-marker-missing" in _codes(findings)


@pytest.mark.parametrize(
    "marker",
    (
        '<!-- agents-md: route owner="docs/recovery.md" when="after failure" purpose="recovery"',
        '<!-- agents-md: route owner="docs/recovery.md" when="after failure" purpose="recovery" --> trailing',
    ),
)
def test_malformed_route_prefix_fails_closed(tmp_path: Path, marker: str) -> None:
    _write_base(tmp_path)
    _append(
        tmp_path,
        f"""
## Recovery routing

{marker}
- After failure, use the governed recovery procedure.
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "routing.route-marker-invalid" in _codes(findings)


def test_indented_unclosed_comment_does_not_hide_later_live_route(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(tmp_path, "docs/recovery.md")
    _append(
        tmp_path,
        """
## Code example

    <!--

## Recovery routing

<!-- agents-md: route owner="docs/recovery.md" when="after failure" purpose="recovery" -->
- After failure, read [the recovery owner](docs/recovery.md).
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert not any(finding.code.startswith("routing.") for finding in findings)


def test_html_comment_cannot_splice_broken_owner_link_into_valid_reference(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(tmp_path, "docs/recovery.md")
    _append(
        tmp_path,
        """
## Recovery routing

<!-- agents-md: route owner="docs/recovery.md" when="after failure" purpose="recovery" -->
- After failure, read [the recovery owner](docs/<!-- note -->recovery.md).
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert {"routing.route-prose-missing", "routing.trigger-unreachable"} <= _codes(findings)


def test_inline_comment_outside_owner_link_preserves_valid_route(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(tmp_path, "docs/recovery.md")
    _append(
        tmp_path,
        """
## Recovery routing

<!-- agents-md: route owner="docs/recovery.md" when="after failure" purpose="recovery" -->
- After failure, <!-- rationale omitted --> read [the recovery owner](docs/recovery.md).
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert not any(finding.code.startswith("routing.") for finding in findings)


def test_inline_code_html_comment_literal_does_not_hide_later_route(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(tmp_path, "docs/recovery.md")
    _append(
        tmp_path,
        """
## Markdown notes

The literal opener is `<!--` and must stay documentation.

## Recovery routing

<!-- agents-md: route owner="docs/recovery.md" when="after failure" purpose="recovery" -->
- After failure, read [the recovery owner](docs/recovery.md).
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert not any(finding.code.startswith("routing.") for finding in findings)


def test_blockquoted_indented_route_example_is_not_live(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(tmp_path, "docs/recovery.md")
    _append(
        tmp_path,
        """
## Quoted code example

>     <!-- agents-md: route owner="docs/recovery.md" when="after failure" purpose="recovery" -->
>     - After failure, read [the recovery owner](docs/recovery.md).
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "routing.trigger-unreachable" in _codes(findings)
    assert "routing.route-marker-invalid" not in _codes(findings)


def test_owner_link_inside_inline_code_is_not_route_evidence(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(tmp_path, "docs/recovery.md")
    _append(
        tmp_path,
        """
## Recovery routing

<!-- agents-md: route owner="docs/recovery.md" when="after failure" purpose="recovery" -->
- Example only: `[the recovery owner](docs/recovery.md)`.
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert {"routing.route-prose-missing", "routing.trigger-unreachable"} <= _codes(findings)


def test_multiline_inline_code_comment_literal_does_not_hide_live_route(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(tmp_path, "docs/recovery.md")
    _append(
        tmp_path,
        """
## Markdown notes

The literal example is `<!--
still inline code` and must not open an HTML comment.

## Recovery routing

<!-- agents-md: route owner="docs/recovery.md" when="after failure" purpose="recovery" -->
- After failure, read [the recovery owner](docs/recovery.md).
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert not any(finding.code.startswith("routing.") for finding in findings)


def test_complete_route_marker_inside_inline_code_is_not_live(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _append(
        tmp_path,
        """
## Marker documentation

Literal example: `<!-- agents-md: route owner="docs/missing.md" when="example" purpose="docs" -->`
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "routing.route-marker-invalid" not in _codes(findings)
    assert "routing.route-owner-missing" not in _codes(findings)


def test_nested_list_owner_link_is_valid_route_prose(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(tmp_path, "docs/recovery.md")
    _append(
        tmp_path,
        """
## Recovery routing

<!-- agents-md: route owner="docs/recovery.md" when="after failure" purpose="recovery" -->
- After failure, use the governed recovery procedure:
    - Read [the recovery owner](docs/recovery.md) before recovery work.
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert not any(finding.code.startswith("routing.") for finding in findings)


def test_backtick_inside_html_comment_cannot_mask_later_live_route(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(tmp_path, "docs/recovery.md")
    _append(
        tmp_path,
        """
## Notes

<!-- an ordinary comment with an unmatched ` backtick -->

<!-- agents-md: route owner="docs/recovery.md" when="after failure" purpose="recovery" -->
- After failure, read [the recovery owner](docs/recovery.md) and treat a lone ` literally.
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert not any(finding.code.startswith("routing.") for finding in findings)


def test_unmatched_backticks_do_not_pair_across_markdown_block_boundaries(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(tmp_path, "docs/recovery.md")
    _append(
        tmp_path,
        """
Paragraph with an unmatched ` opener.

## Recovery routing

<!-- agents-md: route owner="docs/recovery.md" when="after failure" purpose="recovery" -->
- After failure, read [the recovery owner](docs/recovery.md) and leave this unmatched ` literal.
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert not any(finding.code.startswith("routing.") for finding in findings)


@pytest.mark.parametrize("tag", ("pre", "script"))
def test_raw_html_code_block_route_example_is_not_live(tmp_path: Path, tag: str) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(tmp_path, "docs/recovery.md")
    _append(
        tmp_path,
        f"""
## Raw HTML example

<{tag}>
<!-- agents-md: route owner="docs/recovery.md" when="after failure" purpose="recovery" -->
- After failure, read [the recovery owner](docs/recovery.md).
</{tag}>
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "routing.trigger-unreachable" in _codes(findings)
    assert "routing.route-prose-missing" not in _codes(findings)


def test_multiline_inline_code_preserves_line_count_and_does_not_crash(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(tmp_path, "docs/recovery.md")
    _append(
        tmp_path,
        """
## Markdown notes

The literal example is `<!--
still inline code` and must not open an HTML comment.

## Recovery routing

<!-- agents-md: route owner="docs/recovery.md" when="after failure" purpose="recovery" -->
- After failure, read [the recovery owner](docs/recovery.md).
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert not any(finding.code.startswith("routing.") for finding in findings)


@pytest.mark.parametrize("opening", ('<pre class="example">', "<div>", "<details open>"))
def test_raw_html_examples_with_attributes_or_block_tags_are_not_live(
    tmp_path: Path,
    opening: str,
) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(tmp_path, "docs/recovery.md")
    tag = re.match(r"<([A-Za-z0-9]+)", opening)
    assert tag is not None
    _append(
        tmp_path,
        f"""
## Raw HTML example

{opening}
<!-- agents-md: route owner="docs/recovery.md" when="after failure" purpose="recovery" -->
- After failure, read [the recovery owner](docs/recovery.md).
</{tag.group(1)}>

""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "routing.trigger-unreachable" in _codes(findings)
    assert "routing.route-prose-missing" not in _codes(findings)


def test_unclosed_inline_comment_resets_at_blank_line_before_live_route(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(tmp_path, "docs/recovery.md")
    _append(
        tmp_path,
        """
## Notes

Paragraph text <!-- unfinished inline comment

## Recovery routing

<!-- agents-md: route owner="docs/recovery.md" when="after failure" purpose="recovery" -->
- After failure, read [the recovery owner](docs/recovery.md).
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert not any(finding.code.startswith("routing.") for finding in findings)


def test_raw_html_state_resets_when_blockquote_container_ends(tmp_path: Path) -> None:
    _write_base(tmp_path)
    _write_conditional_owner(tmp_path, "docs/recovery.md")
    _append(
        tmp_path,
        """
## Quoted raw HTML example

> <pre class="example">
> example without a closing tag

## Recovery routing

<!-- agents-md: route owner="docs/recovery.md" when="after failure" purpose="recovery" -->
- After failure, read [the recovery owner](docs/recovery.md).
""",
    )

    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert not any(finding.code.startswith("routing.") for finding in findings)
