"""Compose a local disposable MCP candidate acceptance lane and clean only owned state."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

OWNER_MARKER = ".mcp-acceptance-owner"
_REQUIRED_PASS_FIELDS = (
    "build_verdict",
    "migration_preflight_verdict",
    "launch_verdict",
    "exact_candidate_verdict",
    "transport_dogfood_verdict",
    "release_verifier_verdict",
    "durable_polling_verdict",
    "migration_invariants_verdict",
)


@dataclass(frozen=True)
class TrustedCandidateScopeEvidence:
    """Policy/admission-owned candidate scope; implementer evidence cannot mint this authority."""

    scope_ref: object
    candidate_revision: object
    acceptance_contract_digest: object
    acceptance_contract: object


@dataclass(frozen=True)
class LocalCandidateEvidence:
    clean_candidate: bool
    disposable_state: bool
    config_isolated: bool
    ports: tuple[int, ...]
    occupied_ports: frozenset[int]
    build_verdict: str
    migration_preflight_verdict: str
    launch_verdict: str
    exact_candidate_verdict: str
    transport_dogfood_verdict: str
    release_verifier_verdict: str
    durable_polling_verdict: str
    migration_invariants_verdict: str
    artifact_digest: str = ""
    probe_client_receipt: dict[str, object] | None = None
    candidate_revision: str = ""
    migration_acceptance_payload: object = None


def compose_local_lane_receipt(
    evidence: LocalCandidateEvidence,
    *,
    trusted_candidate_scope: TrustedCandidateScopeEvidence | None = None,
) -> dict[str, object]:
    """Return a deterministic fail-closed local candidate lane receipt.

    A passing lane requires a canonical probe client receipt: the candidate
    must have been launched through the pinned official MCP client, not
    evaluated from caller-asserted phase verdicts alone.
    """
    failures: list[str] = []
    if not evidence.clean_candidate:
        failures.append("candidate_not_clean")
    if not evidence.disposable_state or not evidence.config_isolated:
        failures.append("state_or_config_not_disposable")
    if not evidence.ports or any(port <= 0 or port > 65535 for port in evidence.ports):
        failures.append("invalid_ports")
    if len(set(evidence.ports)) != len(evidence.ports):
        failures.append("duplicate_ports")
    conflicts = sorted(set(evidence.ports).intersection(evidence.occupied_ports))
    if conflicts:
        failures.append("port_conflict:" + ",".join(str(port) for port in conflicts))
    for field in _REQUIRED_PASS_FIELDS:
        if getattr(evidence, field) != "pass":
            failures.append(field)
    receipt: dict[str, object] = {
        "schema_version": 1,
        "verdict": "pass" if not failures else "fail",
        "ports": list(evidence.ports),
        "failures": failures,
    }
    probe_receipt = evidence.probe_client_receipt
    if probe_receipt is None:
        if not failures:
            failures.append("probe_client_receipt_missing")
        receipt["verdict"] = "fail"
        receipt["failures"] = failures
        return receipt
    artifact_digest = evidence.artifact_digest
    if not artifact_digest:
        failures.append("artifact_digest_missing")
        receipt["verdict"] = "fail"
        receipt["failures"] = failures
        return receipt
    if probe_receipt.get("artifact_digest") != artifact_digest:
        failures.append("probe_client_receipt_digest_mismatch")
        receipt["verdict"] = "fail"
        receipt["failures"] = failures
        return receipt
    import importlib.util
    import sys
    from pathlib import Path

    probe_path = Path(__file__).resolve().parents[2] / "mcp-server-architect" / "tools" / "mcp_exact_candidate_probe.py"
    spec = importlib.util.spec_from_file_location("local_lane_probe", probe_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    try:
        module.validate_client_provenance(probe_receipt, artifact_digest)
    except module.ExactCandidateAcceptanceError as exc:
        failures.append(f"probe_client_receipt_rejected:{exc}")

    migration_required = False
    scope_valid = False
    if not isinstance(evidence.candidate_revision, str) or not evidence.candidate_revision.strip():
        failures.append("candidate_revision_missing_for_scope")
    if not isinstance(trusted_candidate_scope, TrustedCandidateScopeEvidence):
        failures.append("candidate_scope_missing_or_untrusted")
    else:
        scope = trusted_candidate_scope
        if not isinstance(scope.scope_ref, str) or not scope.scope_ref.strip():
            failures.append("candidate_scope_ref_invalid")
        if not isinstance(scope.candidate_revision, str) or not scope.candidate_revision.strip():
            failures.append("candidate_scope_revision_invalid")
        elif scope.candidate_revision != evidence.candidate_revision:
            failures.append("candidate_scope_candidate_mismatch")
        if not isinstance(scope.acceptance_contract_digest, str) or not scope.acceptance_contract_digest.strip():
            failures.append("candidate_scope_contract_digest_invalid")

        scope_path = Path(__file__).resolve().parents[2] / "qa-change-verifier" / "tools" / "plan_verification.py"
        scope_spec = importlib.util.spec_from_file_location("local_lane_candidate_scope", scope_path)
        assert scope_spec is not None and scope_spec.loader is not None
        scope_module = importlib.util.module_from_spec(scope_spec)
        sys.modules[scope_spec.name] = scope_module
        scope_spec.loader.exec_module(scope_module)
        contract_findings = scope_module.validate_change_acceptance_contract(scope.acceptance_contract)
        if contract_findings:
            failures.extend(f"candidate_scope_contract_rejected:{item}" for item in contract_findings)
        elif scope.acceptance_contract.get("digest") != scope.acceptance_contract_digest:
            failures.append("candidate_scope_contract_digest_mismatch")
        elif (
            isinstance(scope.scope_ref, str)
            and scope.scope_ref.strip()
            and scope.candidate_revision == evidence.candidate_revision
            and isinstance(scope.acceptance_contract_digest, str)
            and scope.acceptance_contract_digest.strip()
        ):
            obligations = scope.acceptance_contract.get("obligations")
            assert isinstance(obligations, list)
            migration_required = any(
                isinstance(item, dict)
                and item.get("required") is True
                and item.get("kind") == "migration"
                for item in obligations
            )
            scope_valid = True
            receipt["candidate_scope"] = {
                "scope_ref": scope.scope_ref,
                "candidate_revision": scope.candidate_revision,
                "acceptance_contract_digest": scope.acceptance_contract_digest,
                "migration_required": migration_required,
            }

    migration_payload = evidence.migration_acceptance_payload
    if scope_valid and migration_required:
        if migration_payload is None:
            failures.append("migration_acceptance_payload_missing")
        else:
            migration_path = (
                Path(__file__).resolve().parents[2] / "qa-change-verifier" / "tools" / "migration_acceptance.py"
            )
            migration_spec = importlib.util.spec_from_file_location("local_lane_migration_acceptance", migration_path)
            assert migration_spec is not None and migration_spec.loader is not None
            migration_module = importlib.util.module_from_spec(migration_spec)
            sys.modules[migration_spec.name] = migration_module
            migration_spec.loader.exec_module(migration_module)
            migration_assessment = migration_module.evaluate_migration_acceptance_payload(migration_payload)
            migration_receipt = migration_assessment.receipt()
            migration_findings = migration_module.validate_migration_acceptance_receipt(migration_receipt)
            if migration_findings:
                failures.extend(f"migration_acceptance_internal_receipt_invalid:{item}" for item in migration_findings)
            elif migration_receipt.get("candidate_revision") != evidence.candidate_revision:
                failures.append("migration_acceptance_receipt_candidate_mismatch")
            elif migration_assessment.status != "pass":
                failures.extend(f"migration_acceptance_failed:{item}" for item in migration_assessment.findings)
            else:
                receipt["migration_acceptance"] = {
                    "verdict": "pass",
                    "candidate_revision": migration_receipt["candidate_revision"],
                    "current_schema": migration_receipt["current_schema"],
                    "exercised_inputs": migration_receipt["exercised_inputs"],
                }
    elif scope_valid and migration_payload is not None:
        failures.append("migration_acceptance_payload_out_of_scope")

    receipt["verdict"] = "pass" if not failures else "fail"
    receipt["failures"] = failures
    return receipt


def cleanup_owned_resources(
    *,
    sandbox_root: Path,
    owner_token: str,
    resources: tuple[Path, ...],
) -> tuple[Path, ...]:
    """Remove only marked resources that resolve strictly below sandbox_root."""
    if not owner_token:
        raise ValueError("owner_token is required")
    root = sandbox_root.resolve(strict=True)
    removed: list[Path] = []
    for resource in resources:
        resolved = resource.resolve(strict=False)
        if resolved == root or not resolved.is_relative_to(root) or not resolved.is_dir():
            continue
        marker = resolved / OWNER_MARKER
        try:
            marker_value = marker.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if marker_value != owner_token:
            continue
        shutil.rmtree(resolved)
        removed.append(resolved)
    return tuple(removed)
