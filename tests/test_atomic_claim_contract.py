"""Executable contract tests for atomic CI/CD and MCP child controls."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from contracts.validate_atomic_claims import validate_catalog, validate_report
from contracts.validate_capability_manifest import validate_manifest

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "contracts/atomic-claim-catalog.yaml"


def _controls() -> dict[str, dict[str, object]]:
    document = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    return {str(control["id"]): control for control in document["controls"]}


def test_atomic_claim_catalog_is_confined_and_executable() -> None:
    assert validate_catalog(repository_root=ROOT) == []


def test_cicd_mcp_claims_are_independent() -> None:
    controls = _controls()
    protocol = controls["cicd.mcp.protocol-conformance"]
    artifact = controls["cicd.mcp.artifact-smoke"]
    assert protocol["parent_rule_id"] == artifact["parent_rule_id"] == "cicd.quality.language"
    assert protocol["required_evidence"] == ["official-client", "integration"]
    assert artifact["required_evidence"] == ["artifact", "official-client"]
    assert protocol["id"] != artifact["id"]


def test_runtime_and_protocol_claims_are_separate() -> None:
    controls = _controls()
    assert controls["mcp.runtime.isolation"]["parent_rule_id"] == "mcp.architecture.boundaries"
    assert controls["mcp.protocol.current-revision"]["parent_rule_id"] == "mcp.sdk.compatibility-isolation"

    manifest = yaml.safe_load(
        (ROOT / "skills/mcp-server-architect/manifest.yaml").read_text(encoding="utf-8")
    )
    profiles = manifest["protocol"]["sdk_profiles"]
    python = profiles["python-official-mcp"]
    fastmcp = profiles["python-fastmcp-package"]
    dotnet = profiles["dotnet-official-mcp"]

    assert "2026-07-28" in python["upstream_supported_revisions"]
    assert python["repository_tested_revisions"] == []
    assert python["current_revision_support"] == "not-claimed"
    assert fastmcp["repository_tested_revisions"] == []
    assert fastmcp["current_revision_support"] == "not-claimed"
    assert dotnet["verified_baseline_versions"] == ["1.4.1"]
    assert dotnet["upstream_stable_candidate_versions"] == ["2.1.0"]
    assert dotnet["repository_tested_revisions"] == []
    assert dotnet["current_revision_support"] == "not-claimed"


def test_local_and_remote_principal_claims_are_distinct() -> None:
    controls = _controls()
    local = controls["mcp.identity.local-principal"]
    remote = controls["mcp.identity.remote-principal"]
    assert local["applies_when"]["profiles_any"] == ["local-stdio"]
    assert remote["applies_when"]["profiles_any"] == ["remote-http"]
    assert local["required_evidence"] != remote["required_evidence"]

    reference = (
        ROOT / "skills/mcp-server-architect/references/principal-and-shell-boundaries.md"
    ).read_text(encoding="utf-8")
    assert "operating-system process boundary" in reference
    assert "Every remote HTTP request MUST authenticate before target resolution" in reference


def test_write_flags_and_confirmation_are_fail_closed(tmp_path: Path) -> None:
    schema = json.loads(
        (ROOT / "contracts/capability-manifest.schema.json").read_text(encoding="utf-8")
    )
    required = set(schema["required"])
    assert {"retryable", "idempotent", "reversible", "requires_confirmation"} <= required

    manifest = {
        "schema_version": 1,
        "id": "device.delete",
        "name": "Delete device",
        "description": "Deletes one device.",
        "operation_kind": "destructive",
        "risk": "critical",
        "determinism": "environment-dependent",
        "latency": "interactive",
        "impact": "external",
        "active_state": "write",
        "retryable": True,
        "idempotent": True,
        "reversible": True,
        "requires_confirmation": True,
        "idempotency_key_required": True,
        "authorization_scopes": ["device:delete"],
        "concurrency": {"scope": "principal-target", "limit": 1},
        "max_response_bytes": 65536,
    }
    path = tmp_path / "capability.yaml"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    findings = validate_manifest(path)
    assert any("retryable_rationale" in finding for finding in findings)
    assert any("idempotent_rationale" in finding for finding in findings)
    assert any("reversible_rationale" in finding for finding in findings)
    assert any("approval" in finding for finding in findings)


def test_shell_boundary_adversarial_matrix_is_normative() -> None:
    reference = (
        ROOT / "skills/mcp-server-architect/references/principal-and-shell-boundaries.md"
    ).read_text(encoding="utf-8")
    for token in (
        ";",
        "&&",
        "$()",
        "`backticks`",
        "newline and carriage return",
        "option injection",
        "Unicode whitespace",
        "oversized input",
    ):
        assert token in reference
    assert "absence of process creation or network dispatch" in reference


def test_response_child_controls_are_independent() -> None:
    controls = _controls()
    expected = {
        "mcp.response.protocol-error",
        "mcp.response.output-bound",
        "mcp.response.provenance",
        "mcp.response.confidentiality",
        "mcp.response.partial-state",
    }
    observed = {
        control_id
        for control_id, control in controls.items()
        if control["parent_rule_id"] == "mcp.response.structured"
    }
    assert observed == expected
    assert len({str(controls[control_id]["description"]) for control_id in expected}) == len(expected)


def test_backend_browser_and_lifecycle_claims_are_separate() -> None:
    controls = _controls()
    assert controls["mcp.backends.confined"]["parent_rule_id"] == "mcp.backends.identity"
    assert controls["mcp.browser.boundaries"]["parent_rule_id"] == "mcp.browser.profile-isolation"
    assert controls["mcp.lifecycle.readiness"]["parent_rule_id"] == "mcp.health.readiness"
    assert controls["mcp.backends.confined"]["applies_when"]["profiles_any"] == [
        "multi-backend",
        "gateway",
    ]


def test_multiarch_identity_is_an_immutable_graph() -> None:
    reference = (
        ROOT / "skills/mcp-server-architect/references/multiarch-artifact-promotion.md"
    ).read_text(encoding="utf-8")
    assert "The release identity is the OCI index digest" in reference
    assert "Each declared platform digest is an independently testable child identity" in reference
    assert "without rebuilding a platform image" in reference
    assert "destination resolves to the same index digest" in reference


def test_atomic_report_cannot_pass_by_omitting_child_controls(tmp_path: Path) -> None:
    report = {
        "schema_version": 1,
        "report_id": "missing-controls",
        "repository": {"name": "example/server", "revision": "1" * 40},
        "skill": "mcp-server-architect",
        "context": {
            "target_level": "L1",
            "profiles": ["local-stdio"],
            "capabilities": [],
        },
        "checks": [],
        "residual_risks": [],
    }
    path = tmp_path / "atomic-report.yaml"
    path.write_text(yaml.safe_dump(report), encoding="utf-8")
    findings = validate_report(path, repository_root=ROOT)
    assert any("missing applicable child controls" in finding for finding in findings)
