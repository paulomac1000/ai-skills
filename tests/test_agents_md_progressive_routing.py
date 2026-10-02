"""Trigger-safe progressive routing regressions for the AGENTS.md repository audit."""

from __future__ import annotations

import json
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
