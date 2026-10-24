"""Issue #168 regressions: trusted release-verifier evidence and admission authority.

The diagnostic composer may return a syntactically valid aggregate for
caller-supplied phase results, but release authority must never return a
trusted PASS without independently verified provider-backed provenance for
every accepted phase, and the local candidate lane must derive migration
scope from a verified admission authority rather than a caller-constructed
binding object.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "skills/mcp-gateway-release-verifier/tools/compose_release_verdict.py"
LANE = ROOT / "skills/mcp-gateway-release-verifier/tools/local_candidate_lane.py"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _probe_receipt(artifact_digest: str) -> dict[str, object]:
    payload = {
        "protocolVersion": "2025-06-18",
        "serverInfo": {"name": "candidate", "version": "1.0.0"},
    }
    canonical = json.dumps(
        {
            "artifact_digest": artifact_digest,
            "client_version": "2.0.0",
            "initialize": payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return {
        "package": "mcp",
        "version": "2.0.0",
        "protocol_revision": "2025-06-18",
        "transport": "stdio",
        "initialize_payload": payload,
        "session_receipt": hashlib.sha256(canonical.encode()).hexdigest(),
        "artifact_digest": artifact_digest,
    }


def _phases(module: ModuleType, **status_overrides: str) -> tuple[object, ...]:
    return tuple(
        module.PhaseResult(
            name=name,
            status=status_overrides.get(name, "pass"),
            contract_ref=module.COMPOSED_CONTRACTS[name],
            evidence_ref=f"evidence://{name}",
            summary=f"{name} verified",
        )
        for name in module.REQUIRED_PHASES
    )


def _execution_reference(run_id: int = 9001, job_id: int = 9002) -> dict[str, object]:
    return {
        "repository": "paulomac1000/candidate-server",
        "run_id": run_id,
        "job_id": job_id,
        "check_run_id": 9003,
        "workflow_id": 9004,
        "workflow_path": ".github/workflows/ci.yml",
        "workflow_name": "CI",
        "event": "pull_request",
        "job_name": "release-evidence",
    }


def _binding(
    module: ModuleType,
    phase: str,
    *,
    source_sha: str = "a" * 40,
    artifact_digest: str = "sha256:" + "b" * 64,
    policy_revision: str = "release-profile-v1",
    evidence_ref: str | None = None,
    producer: str = "github-actions",
    receipt_kind: str = "github-actions-run",
    authority_class: str = "provider-backed",
    run_id: int = 9001,
) -> object:
    return module.PhaseEvidenceBinding(
        phase=phase,
        receipt_kind=receipt_kind,
        producer=producer,
        authority_class=authority_class,
        source_sha=source_sha,
        artifact_digest=artifact_digest,
        policy_revision=policy_revision,
        evidence_ref=evidence_ref if evidence_ref is not None else f"evidence://{phase}",
        evidence_digest="sha256:" + hashlib.sha256(f"evidence-{phase}".encode()).hexdigest(),
        execution_reference=_execution_reference(run_id=run_id, job_id=run_id + 1),
    )


def _bindings(module: ModuleType, phases: tuple[object, ...], **overrides: object) -> dict[str, object]:
    return {
        phase.name: _binding(module, phase.name, **overrides)  # type: ignore[attr-defined]
        for phase in phases
    }


class _RecordingAuthority:
    """Isolated test trust root simulating provider-backed verification."""

    def __init__(self, *, violations: list[str] | None = None, fail_unresolved: bool = False) -> None:
        self.violations = violations or []
        self.fail_unresolved = fail_unresolved
        self.calls: list[tuple[object, str]] = []

    def verify_action(self, reference: object, expected_revision: str) -> list[str]:
        self.calls.append((reference, expected_revision))
        if self.fail_unresolved:
            return ["provider record for the referenced run could not be resolved"]
        return list(self.violations)


class _AdmissionAuthority:
    """Isolated test trust root simulating verified admission records."""

    def __init__(self, *, violations: list[str] | None = None) -> None:
        self.violations = violations or []
        self.calls: list[dict[str, str]] = []

    def resolve_admission(
        self, source: str, *, candidate_revision: str, acceptance_contract_digest: str, policy_revision: str
    ) -> list[str]:
        self.calls.append(
            {
                "source": source,
                "candidate_revision": candidate_revision,
                "acceptance_contract_digest": acceptance_contract_digest,
                "policy_revision": policy_revision,
            }
        )
        return list(self.violations)


# ---------------------------------------------------------------------------
# RED-01: fabricated complete release must not yield trusted release PASS
# ---------------------------------------------------------------------------


def test_diagnostic_composer_marks_receipt_as_diagnostic_not_release_authority() -> None:
    module = _load("evidence_authority_diagnostic_marker", VERIFIER)
    digest = "sha256:" + "b" * 64
    receipt = module.compose_release_receipt(
        source_revision="a" * 40,
        artifact_digest=digest,
        phases=_phases(module),
        probe_client_receipt=_probe_receipt(digest),
    )
    assert receipt["verdict"] == "pass"
    assert receipt["authority"] == "diagnostic"


def test_fabricated_complete_release_cannot_return_trusted_release_pass() -> None:
    module = _load("evidence_authority_red01", VERIFIER)
    digest = "sha256:" + "b" * 64
    phases = _phases(module)
    authority = _RecordingAuthority()
    receipt = module.compose_release_acceptance(
        source_revision="a" * 40,
        artifact_digest=digest,
        phases=phases,
        probe_client_receipt=_probe_receipt(digest),
        evidence_bindings={},
        evidence_authority=authority,
        policy_revision="release-profile-v1",
    )
    assert receipt["verdict"] == "fail"
    assert receipt["authority"] == "trusted"
    assert any("evidence_binding" in failure for failure in receipt["authority_failures"])
    assert authority.calls == []


def test_authoritative_pass_requires_verified_bindings_for_every_accepted_phase() -> None:
    module = _load("evidence_authority_green01", VERIFIER)
    digest = "sha256:" + "b" * 64
    phases = _phases(module)
    authority = _RecordingAuthority()
    receipt = module.compose_release_acceptance(
        source_revision="a" * 40,
        artifact_digest=digest,
        phases=phases,
        probe_client_receipt=_probe_receipt(digest),
        evidence_bindings=_bindings(module, phases),
        evidence_authority=authority,
        policy_revision="release-profile-v1",
    )
    assert receipt["verdict"] == "pass"
    assert receipt["authority"] == "trusted"
    assert receipt["policy_revision"] == "release-profile-v1"
    assert len(authority.calls) == len(module.REQUIRED_PHASES)
    for _reference, expected_revision in authority.calls:
        assert expected_revision == "a" * 40


# ---------------------------------------------------------------------------
# RED-02: synthetic official-client provenance without trusted execution
# ---------------------------------------------------------------------------


def test_probe_receipt_without_trusted_execution_binding_is_non_green() -> None:
    module = _load("evidence_authority_red02", VERIFIER)
    digest = "sha256:" + "b" * 64
    phases = _phases(module)
    authority = _RecordingAuthority()
    bindings = _bindings(module, phases)
    del bindings["schema"]
    receipt = module.compose_release_acceptance(
        source_revision="a" * 40,
        artifact_digest=digest,
        phases=phases,
        probe_client_receipt=_probe_receipt(digest),
        evidence_bindings=bindings,
        evidence_authority=authority,
        policy_revision="release-profile-v1",
    )
    assert receipt["verdict"] == "fail"
    assert any("schema" in failure for failure in receipt["authority_failures"])


def test_authority_violations_fail_the_release_closed() -> None:
    module = _load("evidence_authority_red02b", VERIFIER)
    digest = "sha256:" + "b" * 64
    phases = _phases(module)
    authority = _RecordingAuthority(violations=["workflow run head_sha does not match the assessed revision"])
    receipt = module.compose_release_acceptance(
        source_revision="a" * 40,
        artifact_digest=digest,
        phases=phases,
        probe_client_receipt=_probe_receipt(digest),
        evidence_bindings=_bindings(module, phases),
        evidence_authority=authority,
        policy_revision="release-profile-v1",
    )
    assert receipt["verdict"] == "fail"
    assert any("head_sha" in failure for failure in receipt["authority_failures"])


def test_unresolvable_provider_record_is_not_a_pass() -> None:
    module = _load("evidence_authority_red02c", VERIFIER)
    digest = "sha256:" + "b" * 64
    phases = _phases(module)
    authority = _RecordingAuthority(fail_unresolved=True)
    receipt = module.compose_release_acceptance(
        source_revision="a" * 40,
        artifact_digest=digest,
        phases=phases,
        probe_client_receipt=_probe_receipt(digest),
        evidence_bindings=_bindings(module, phases),
        evidence_authority=authority,
        policy_revision="release-profile-v1",
    )
    assert receipt["verdict"] == "fail"
    assert any("could not be resolved" in failure for failure in receipt["authority_failures"])


# ---------------------------------------------------------------------------
# RED-04/RED-05: cross-candidate replay and stale identity bindings
# ---------------------------------------------------------------------------


def test_cross_candidate_binding_replay_is_rejected() -> None:
    module = _load("evidence_authority_red04", VERIFIER)
    digest = "sha256:" + "b" * 64
    phases = _phases(module)
    authority = _RecordingAuthority()
    stale_bindings = _bindings(module, phases, source_sha="c" * 40)
    receipt = module.compose_release_acceptance(
        source_revision="a" * 40,
        artifact_digest=digest,
        phases=phases,
        probe_client_receipt=_probe_receipt(digest),
        evidence_bindings=stale_bindings,
        evidence_authority=authority,
        policy_revision="release-profile-v1",
    )
    assert receipt["verdict"] == "fail"
    assert any("source_sha" in failure for failure in receipt["authority_failures"])
    assert authority.calls == []


def test_stale_artifact_or_policy_binding_is_rejected() -> None:
    module = _load("evidence_authority_red05", VERIFIER)
    digest = "sha256:" + "b" * 64
    phases = _phases(module)
    authority = _RecordingAuthority()
    stale_artifact = _bindings(module, phases, artifact_digest="sha256:" + "d" * 64)
    receipt = module.compose_release_acceptance(
        source_revision="a" * 40,
        artifact_digest=digest,
        phases=phases,
        probe_client_receipt=_probe_receipt(digest),
        evidence_bindings=stale_artifact,
        evidence_authority=authority,
        policy_revision="release-profile-v1",
    )
    assert receipt["verdict"] == "fail"
    assert any("artifact_digest" in failure for failure in receipt["authority_failures"])

    stale_policy = _bindings(module, phases, policy_revision="release-profile-v0")
    receipt = module.compose_release_acceptance(
        source_revision="a" * 40,
        artifact_digest=digest,
        phases=phases,
        probe_client_receipt=_probe_receipt(digest),
        evidence_bindings=stale_policy,
        evidence_authority=authority,
        policy_revision="release-profile-v1",
    )
    assert receipt["verdict"] == "fail"
    assert any("policy_revision" in failure for failure in receipt["authority_failures"])


def test_unknown_receipt_kind_or_authority_class_is_rejected() -> None:
    module = _load("evidence_authority_red06", VERIFIER)
    digest = "sha256:" + "b" * 64
    phases = _phases(module)
    authority = _RecordingAuthority()
    unknown_kind = _bindings(module, phases, receipt_kind="caller-note")
    receipt = module.compose_release_acceptance(
        source_revision="a" * 40,
        artifact_digest=digest,
        phases=phases,
        probe_client_receipt=_probe_receipt(digest),
        evidence_bindings=unknown_kind,
        evidence_authority=authority,
        policy_revision="release-profile-v1",
    )
    assert receipt["verdict"] == "fail"
    assert any("receipt_kind" in failure for failure in receipt["authority_failures"])

    unknown_class = _bindings(module, phases, authority_class="self-declared")
    receipt = module.compose_release_acceptance(
        source_revision="a" * 40,
        artifact_digest=digest,
        phases=phases,
        probe_client_receipt=_probe_receipt(digest),
        evidence_bindings=unknown_class,
        evidence_authority=authority,
        policy_revision="release-profile-v1",
    )
    assert receipt["verdict"] == "fail"
    assert any("authority_class" in failure for failure in receipt["authority_failures"])


def test_not_run_required_phase_cannot_be_masked_by_extension_phase() -> None:
    module = _load("evidence_authority_red06b", VERIFIER)
    digest = "sha256:" + "b" * 64
    phases = tuple(phase for phase in _phases(module) if phase.name != "cleanup")  # type: ignore[attr-defined]
    extension = module.PhaseResult(
        name="extension-extra",
        status="pass",
        contract_ref="project/extension",
        evidence_ref="evidence://extension-extra",
    )
    authority = _RecordingAuthority()
    receipt = module.compose_release_acceptance(
        source_revision="a" * 40,
        artifact_digest=digest,
        phases=phases + (extension,),
        probe_client_receipt=_probe_receipt(digest),
        evidence_bindings=_bindings(module, phases + (extension,)),
        evidence_authority=authority,
        policy_revision="release-profile-v1",
    )
    assert receipt["verdict"] == "fail"
    assert next(phase for phase in receipt["phases"] if phase["name"] == "cleanup")["status"] == "not_run"


# ---------------------------------------------------------------------------
# RED-03: caller-constructed scope binding cannot mint admission authority
# ---------------------------------------------------------------------------


def _change_acceptance_contract(*, migration: bool) -> dict[str, object]:
    obligation_kind = "migration" if migration else "functional"
    obligation_id = "migration-scope" if migration else "non-migration-scope"
    contract: dict[str, object] = {
        "schema_version": 1,
        "change_id": "candidate-scope",
        "revision": "scope-v1",
        "obligations": [
            {
                "id": obligation_id,
                "kind": obligation_kind,
                "statement": "Declare whether persistent migration acceptance is required.",
                "source_ref": "policy:candidate-scope",
                "required": True,
            }
        ],
        "criteria": [
            {
                "id": "scope-proof",
                "obligation_refs": [obligation_id],
                "expected_outcome": "Candidate scope is admitted before local acceptance.",
                "rejection_condition": "Candidate scope is missing, stale, or invalid.",
                "required": True,
            }
        ],
    }
    encoded = json.dumps(contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    contract["digest"] = "sha256:" + hashlib.sha256(encoded).hexdigest()
    return contract


def _candidate_scope(
    module: ModuleType,
    *,
    migration: bool = False,
    candidate_revision: str = "candidate-1",
    policy_revision: str = "admission-policy-v1",
) -> object:
    contract = _change_acceptance_contract(migration=migration)
    source_digest = hashlib.sha256(b"candidate-scope-policy-v1").hexdigest()
    identity = module.CandidateScopeIdentity(
        candidate_revision=candidate_revision,
        acceptance_contract_digest=contract["digest"],
    )
    binding = module.TrustedCandidateScopeBinding(
        identity=identity,
        source=f"admission:sha256:{source_digest}",
        policy_revision=policy_revision,
    )
    return module.TrustedCandidateScopeEvidence(acceptance_contract=contract, binding=binding)


def _lane_evidence(module: ModuleType, **changes: object) -> object:
    values: dict[str, object] = {
        "clean_candidate": True,
        "disposable_state": True,
        "config_isolated": True,
        "ports": (43101, 43102),
        "occupied_ports": frozenset(),
        "build_verdict": "pass",
        "migration_preflight_verdict": "pass",
        "launch_verdict": "pass",
        "exact_candidate_verdict": "pass",
        "transport_dogfood_verdict": "pass",
        "release_verifier_verdict": "pass",
        "durable_polling_verdict": "pass",
        "migration_invariants_verdict": "pass",
        "artifact_digest": "sha256:" + "d" * 64,
        "probe_client_receipt": _probe_receipt("sha256:" + "d" * 64),
        "candidate_revision": "candidate-1",
    }
    values.update(changes)
    return module.LocalCandidateEvidence(**values)


def test_caller_constructed_scope_without_admission_authority_cannot_waive_migration() -> None:
    module = _load("evidence_authority_red03", LANE)
    receipt = module.compose_local_lane_receipt(
        _lane_evidence(module),
        trusted_candidate_scope=_candidate_scope(module, migration=False),
        admission_authority=None,
        policy_revision="admission-policy-v1",
    )
    assert receipt["verdict"] == "fail"
    assert "candidate_scope_admission_unresolved" in receipt["failures"]


def test_admission_authority_violations_fail_the_lane_closed() -> None:
    module = _load("evidence_authority_red03b", LANE)
    authority = _AdmissionAuthority(violations=["admission record is not bound to the candidate revision"])
    receipt = module.compose_local_lane_receipt(
        _lane_evidence(module),
        trusted_candidate_scope=_candidate_scope(module, migration=False),
        admission_authority=authority,
        policy_revision="admission-policy-v1",
    )
    assert receipt["verdict"] == "fail"
    assert any("admission" in failure for failure in receipt["failures"])
    assert authority.calls[0]["candidate_revision"] == "candidate-1"


def test_verified_admission_without_migration_passes_lane() -> None:
    module = _load("evidence_authority_green03", LANE)
    authority = _AdmissionAuthority()
    receipt = module.compose_local_lane_receipt(
        _lane_evidence(module),
        trusted_candidate_scope=_candidate_scope(module, migration=False),
        admission_authority=authority,
        policy_revision="admission-policy-v1",
    )
    assert receipt["verdict"] == "pass"
    scope = receipt["candidate_scope"]
    assert scope["admission_verified"] is True
    assert scope["policy_revision"] == "admission-policy-v1"
    assert scope["migration_required"] is False


def test_verified_admission_requiring_migration_evaluates_through_canonical_evaluator() -> None:
    module = _load("evidence_authority_green03b", LANE)
    authority = _AdmissionAuthority()
    missing = module.compose_local_lane_receipt(
        _lane_evidence(module),
        trusted_candidate_scope=_candidate_scope(module, migration=True),
        admission_authority=authority,
        policy_revision="admission-policy-v1",
    )
    assert missing["verdict"] == "fail"
    assert "migration_acceptance_payload_missing" in missing["failures"]


def test_policy_revision_mismatch_between_lane_and_binding_is_rejected() -> None:
    module = _load("evidence_authority_red05b", LANE)
    authority = _AdmissionAuthority()
    receipt = module.compose_local_lane_receipt(
        _lane_evidence(module),
        trusted_candidate_scope=_candidate_scope(module, policy_revision="admission-policy-v0"),
        admission_authority=authority,
        policy_revision="admission-policy-v1",
    )
    assert receipt["verdict"] == "fail"
    assert "candidate_scope_policy_revision_mismatch" in receipt["failures"]


def test_missing_policy_revision_fails_closed() -> None:
    module = _load("evidence_authority_red05c", LANE)
    authority = _AdmissionAuthority()
    receipt = module.compose_local_lane_receipt(
        _lane_evidence(module),
        trusted_candidate_scope=_candidate_scope(module),
        admission_authority=authority,
        policy_revision="",
    )
    assert receipt["verdict"] == "fail"
    assert "candidate_scope_policy_revision_missing" in receipt["failures"]


# ---------------------------------------------------------------------------
# Compatibility: diagnostic composer behavior is preserved
# ---------------------------------------------------------------------------


def test_diagnostic_composer_still_rejects_missing_probe_receipt() -> None:
    module = _load("evidence_authority_compat", VERIFIER)
    with pytest.raises(module.ReleaseCompositionError, match="probe client receipt"):
        module.compose_release_receipt(
            source_revision="a" * 40,
            artifact_digest="sha256:" + "b" * 64,
            phases=_phases(module),
        )


def test_authoritative_path_rejects_unbounded_policy_revision() -> None:
    module = _load("evidence_authority_bounds", VERIFIER)
    digest = "sha256:" + "b" * 64
    phases = _phases(module)
    with pytest.raises(module.ReleaseCompositionError, match="policy_revision"):
        module.compose_release_acceptance(
            source_revision="a" * 40,
            artifact_digest=digest,
            phases=phases,
            probe_client_receipt=_probe_receipt(digest),
            evidence_bindings=_bindings(module, phases),
            evidence_authority=_RecordingAuthority(),
            policy_revision="x" * 200,
        )
