"""Compose existing MCP release contracts into one bounded fail-closed receipt.

Two distinct outcomes are produced by this module and must never be confused:

- :func:`compose_release_receipt` performs **diagnostic composition** of
  caller-supplied phase results. Its ``pass`` verdict means the aggregate is
  well formed; it is never release authority.
- :func:`compose_release_acceptance` performs **authoritative release
  acceptance**. Every accepted phase must carry a typed evidence binding that
  an injected provider-backed authority independently resolves against the
  exact candidate revision; missing, unknown, stale, or unresolvable
  provenance is non-green.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

MAX_PHASES = 16
MAX_SUMMARY_CHARS = 240
MAX_EVIDENCE_REF_CHARS = 512
MAX_RECEIPT_BYTES = 8192
MAX_IDENTITY_CHARS = 128
REQUIRED_PHASES = (
    "preflight",
    "bootstrap",
    "exact_artifact_launch",
    "schema",
    "lifecycle",
    "degraded_health",
    "identity",
    "execution_integrity",
    "cleanup",
)
COMPOSED_CONTRACTS = {
    "preflight": "issue-49-exact-artifact-identity",
    "bootstrap": "ci-cd-architect/check_verification_bootstrap",
    "exact_artifact_launch": "issue-49-exact-artifact-identity",
    "schema": "mcp-server-architect/exact_candidate_acceptance",
    "lifecycle": "mcp-server-architect/transport_dogfood",
    "degraded_health": "mcp-server-architect/transport_dogfood",
    "identity": "issue-49-exact-artifact-identity",
    "execution_integrity": "ci-cd-architect/check_execution_integrity",
    "cleanup": "ci-cd-architect/verify_state_isolation",
}
_ALLOWED_STATUS = frozenset({"pass", "fail", "not_run"})
_SUPPORTED_RECEIPT_KINDS = frozenset({"github-actions-run"})
_SUPPORTED_AUTHORITY_CLASSES = frozenset({"provider-backed"})
_DIGEST_PREFIX = "sha256:"

_ACCEPTANCE_TOOL = (
    Path(__file__).resolve().parents[2] / "mcp-server-architect" / "tools" / "exact_candidate_acceptance.py"
)


def _load_canonical_acceptance() -> Any:
    """Load the owning exact-candidate acceptance contract; never fork it."""
    spec = importlib.util.spec_from_file_location("release_verifier_canonical_acceptance", _ACCEPTANCE_TOOL)
    if spec is None or spec.loader is None:
        raise ReleaseCompositionError("canonical exact-candidate acceptance contract is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ReleaseEvidenceAuthority(Protocol):
    """Structural protocol for independently resolving provider-backed evidence.

    Implementations must resolve the referenced execution record from the
    provider's own API — never from caller-supplied status strings — and
    return violations when the record does not bind the expected revision.
    The composer derives ``reference["_expected_claim"]`` from the phase
    binding itself (phase, contract, artifact digest, evidence digest,
    policy revision, producer); implementations must verify that the
    provider-resolved evidence contains exactly that claim, bound to
    verified executions, before accepting the phase. The canonical
    production implementation is the provider-backed GitHub Actions
    verifier family in the repository ``contracts/evidence.py``.
    """

    def verify_action(self, reference: Mapping[str, Any], expected_revision: str) -> Sequence[str]:
        """Return violations for one provider execution record reference."""
        ...


class ReleaseCompositionError(ValueError):
    """Raised when phase evidence is unbounded or claims the wrong owner contract."""


@dataclass(frozen=True)
class PhaseResult:
    name: str
    status: str
    contract_ref: str
    evidence_ref: str
    summary: str = ""


@dataclass(frozen=True)
class PhaseEvidenceBinding:
    """Typed producer binding for one accepted phase's execution evidence.

    ``execution_reference`` is resolved independently by the injected
    :class:`ReleaseEvidenceAuthority`; the composer never trusts its status
    fields. Identity fields must match the composed candidate exactly.
    """

    phase: str
    receipt_kind: str
    producer: str
    authority_class: str
    source_sha: str
    artifact_digest: str
    policy_revision: str
    evidence_ref: str
    evidence_digest: str
    execution_reference: Mapping[str, Any] = field(default_factory=dict)


def _validate_probe_receipt(receipt: Mapping[str, object], artifact_digest: str) -> None:
    """Validate the probe receipt through its owning canonical contract."""
    acceptance = _load_canonical_acceptance()
    try:
        acceptance.validate_client_provenance(receipt, artifact_digest)
    except acceptance.ExactCandidateAcceptanceError as exc:
        raise ReleaseCompositionError(f"probe client receipt rejected by the owning contract: {exc}") from exc


def _validate_identity_field(value: str, label: str) -> None:
    if not isinstance(value, str) or not value or len(value) > MAX_IDENTITY_CHARS:
        raise ReleaseCompositionError(f"{label} is missing or unbounded")


def _validate_digest_field(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.startswith(_DIGEST_PREFIX) or len(value) != len(_DIGEST_PREFIX) + 64:
        raise ReleaseCompositionError(f"{label} must be a sha256 digest")


def _validate_binding_identity(binding: PhaseEvidenceBinding, phase: PhaseResult) -> list[str]:
    """Return typed trust failures for one binding; structural errors raise."""
    failures: list[str] = []
    if binding.phase != phase.name:
        failures.append(f"evidence_binding_phase_mismatch:{phase.name}")
    if binding.receipt_kind not in _SUPPORTED_RECEIPT_KINDS:
        failures.append(
            f"evidence_binding_unsupported_receipt_kind:{phase.name}:{str(binding.receipt_kind)[:MAX_SUMMARY_CHARS]}"
        )
    if binding.authority_class not in _SUPPORTED_AUTHORITY_CLASSES:
        failures.append(
            f"evidence_binding_unsupported_authority_class:{phase.name}:"
            f"{str(binding.authority_class)[:MAX_SUMMARY_CHARS]}"
        )
    if not binding.producer or len(binding.producer) > MAX_IDENTITY_CHARS:
        failures.append(f"evidence_binding_producer_missing_or_unbounded:{phase.name}")
    if not binding.execution_reference:
        failures.append(f"evidence_binding_execution_reference_missing:{phase.name}")
    elif "_expected_claim" in binding.execution_reference:
        failures.append(f"evidence_binding_caller_claim_rejected:{phase.name}")
    if binding.evidence_ref != phase.evidence_ref:
        failures.append(f"evidence_binding_ref_mismatch:{phase.name}")
    return failures


def _expected_phase_claim(
    binding: PhaseEvidenceBinding, phase: PhaseResult, *, artifact_digest: str, policy_revision: str
) -> dict[str, str]:
    """Derive the composer-owned claim the provider evidence must contain."""
    return {
        "kind": "release-phase",
        "phase": phase.name,
        "contract_ref": phase.contract_ref,
        "artifact_digest": artifact_digest,
        "evidence_digest": binding.evidence_digest,
        "policy_revision": policy_revision,
        "producer": binding.producer,
    }


def _validate_phase(phase: PhaseResult) -> None:
    if phase.status not in _ALLOWED_STATUS:
        raise ReleaseCompositionError(f"invalid phase status: {phase.status}")
    if len(phase.summary) > MAX_SUMMARY_CHARS:
        raise ReleaseCompositionError("phase summary exceeds bound")
    if not phase.evidence_ref or len(phase.evidence_ref) > MAX_EVIDENCE_REF_CHARS:
        raise ReleaseCompositionError("phase evidence_ref exceeds bound")
    expected = COMPOSED_CONTRACTS.get(phase.name)
    if expected is not None and phase.contract_ref != expected:
        raise ReleaseCompositionError(f"phase {phase.name} must consume {expected}")


def _compose_phases(
    *,
    source_revision: str,
    artifact_digest: str,
    phases: tuple[PhaseResult, ...],
    probe_client_receipt: Mapping[str, object] | None,
) -> list[PhaseResult]:
    if not source_revision or len(source_revision) > MAX_IDENTITY_CHARS:
        raise ReleaseCompositionError("source_revision is missing or unbounded")
    if not artifact_digest or len(artifact_digest) > MAX_IDENTITY_CHARS:
        raise ReleaseCompositionError("artifact_digest is missing or unbounded")
    if len(phases) > MAX_PHASES:
        raise ReleaseCompositionError("phase count exceeds bound")
    by_name: dict[str, PhaseResult] = {}
    for phase in phases:
        _validate_phase(phase)
        if phase.name in by_name:
            raise ReleaseCompositionError(f"duplicate phase: {phase.name}")
        by_name[phase.name] = phase
    probe_required = any(
        by_name.get(name, PhaseResult(name, "not_run", "", "", "")).status == "pass"
        for name in ("exact_artifact_launch", "schema")
    )
    if probe_required:
        if probe_client_receipt is None:
            raise ReleaseCompositionError(
                "passing exact-artifact/schema phases require a canonical probe "
                "client receipt; evidence without the pinned official client is "
                "rejected"
            )
        _validate_probe_receipt(probe_client_receipt, artifact_digest)

    ordered: list[PhaseResult] = []
    for name in REQUIRED_PHASES:
        if name in by_name:
            phase = by_name.pop(name)
        else:
            phase = PhaseResult(
                name=name,
                status="not_run",
                contract_ref=COMPOSED_CONTRACTS[name],
                evidence_ref="missing",
                summary="required phase missing",
            )
        ordered.append(phase)
    ordered.extend(by_name[name] for name in sorted(by_name))
    return ordered


def compose_release_receipt(
    *,
    source_revision: str,
    artifact_digest: str,
    phases: tuple[PhaseResult, ...],
    probe_client_receipt: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Compose phase results diagnostically; never reinterpret owner semantics.

    The returned receipt is a **diagnostic** aggregate of caller-supplied
    phase results: ``verdict: "pass"`` means the composition is well formed
    and bounded, not that the claimed tests were executed by a trusted
    producer. Authoritative release acceptance must use
    :func:`compose_release_acceptance`.

    The exact-artifact and schema phases are only accepted as ``pass`` when a
    valid canonical probe client receipt is provided; evidence derived without
    the pinned official MCP client cannot satisfy the composition.
    """
    ordered = _compose_phases(
        source_revision=source_revision,
        artifact_digest=artifact_digest,
        phases=phases,
        probe_client_receipt=probe_client_receipt,
    )
    verdict = "pass" if all(phase.status == "pass" for phase in ordered) else "fail"
    receipt: dict[str, object] = {
        "schema_version": 1,
        "authority": "diagnostic",
        "candidate": {
            "source_revision": source_revision,
            "artifact_digest": artifact_digest,
        },
        "phases": [asdict(phase) for phase in ordered],
        "verdict": verdict,
    }
    if len(json.dumps(receipt, sort_keys=True).encode("utf-8")) > MAX_RECEIPT_BYTES:
        raise ReleaseCompositionError("release receipt exceeds byte bound")
    return receipt


def compose_release_acceptance(
    *,
    source_revision: str,
    artifact_digest: str,
    phases: tuple[PhaseResult, ...],
    probe_client_receipt: Mapping[str, object] | None = None,
    evidence_bindings: Mapping[str, object],
    evidence_authority: ReleaseEvidenceAuthority,
    policy_revision: str,
) -> dict[str, object]:
    """Compose an authoritative release acceptance receipt; fail closed.

    Every phase accepted as ``pass`` — required and extension — must carry a
    typed :class:`PhaseEvidenceBinding` whose identity fields match this
    exact candidate and whose execution record the injected provider-backed
    authority independently resolves against ``source_revision``. Missing,
    unknown, stale, cross-candidate, or unresolvable provenance yields a
    non-green receipt with typed failure reasons; it never raises for trust
    failures, so consumers cannot mistake an exception path for a decision.
    """
    _validate_identity_field(policy_revision, "policy_revision")
    ordered = _compose_phases(
        source_revision=source_revision,
        artifact_digest=artifact_digest,
        phases=phases,
        probe_client_receipt=probe_client_receipt,
    )
    authority_failures: list[str] = []
    binding_receipts: dict[str, object] = {}
    for phase in ordered:
        if phase.status != "pass":
            continue
        binding = evidence_bindings.get(phase.name)
        if binding is None:
            authority_failures.append(f"evidence_binding_missing:{phase.name}")
            continue
        if not isinstance(binding, PhaseEvidenceBinding):
            authority_failures.append(f"evidence_binding_untyped:{phase.name}")
            continue
        failures = _validate_binding_identity(binding, phase)
        if binding.source_sha != source_revision:
            failures.append(f"evidence_binding_source_sha_mismatch:{phase.name}")
        if binding.artifact_digest != artifact_digest:
            failures.append(f"evidence_binding_artifact_digest_mismatch:{phase.name}")
        if binding.policy_revision != policy_revision:
            failures.append(f"evidence_binding_policy_revision_mismatch:{phase.name}")
        try:
            _validate_digest_field(binding.evidence_digest, "evidence_digest")
        except ReleaseCompositionError:
            failures.append(f"evidence_binding_evidence_digest_invalid:{phase.name}")
        if not failures:
            reference = dict(binding.execution_reference)
            reference["_expected_claim"] = _expected_phase_claim(
                binding, phase, artifact_digest=artifact_digest, policy_revision=policy_revision
            )
            try:
                violations = list(evidence_authority.verify_action(reference, source_revision))
            except Exception:  # noqa: BLE001 - trust failures are decisions, not crashes
                violations = ["authority could not resolve the referenced provider record"]
            failures.extend(
                f"evidence_authority_rejected:{phase.name}:{str(item)[:MAX_SUMMARY_CHARS]}" for item in violations
            )
        if failures:
            authority_failures.extend(failures)
        else:
            binding_receipts[phase.name] = {
                "receipt_kind": binding.receipt_kind,
                "producer": binding.producer,
                "authority_class": binding.authority_class,
                "evidence_ref": binding.evidence_ref,
                "evidence_digest": binding.evidence_digest,
            }
    verdict = "pass" if not authority_failures and all(phase.status == "pass" for phase in ordered) else "fail"
    receipt: dict[str, object] = {
        "schema_version": 1,
        "authority": "trusted",
        "policy_revision": policy_revision,
        "candidate": {
            "source_revision": source_revision,
            "artifact_digest": artifact_digest,
        },
        "phases": [asdict(phase) for phase in ordered],
        "evidence_bindings": binding_receipts,
        "authority_failures": authority_failures,
        "verdict": verdict,
    }
    encoded = json.dumps(receipt, sort_keys=True).encode("utf-8")
    if len(encoded) > MAX_RECEIPT_BYTES:
        capped = dict(receipt)
        capped["authority_failures"] = [failure[:MAX_SUMMARY_CHARS] for failure in authority_failures[:MAX_PHASES]]
        capped["authority_failures_truncated"] = True
        if len(json.dumps(capped, sort_keys=True).encode("utf-8")) > MAX_RECEIPT_BYTES:
            raise ReleaseCompositionError("release receipt exceeds byte bound")
        return capped
    return receipt
