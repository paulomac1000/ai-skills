"""Execution Evidence Contract v1 (issue #91).

Provider-neutral, bounded, immutable correlation envelopes and a deterministic
evidence-graph evaluator for one autonomous delivery lineage. This module owns
cross-system correlation only: product runtimes keep their own durable state
and project bounded receipts into this contract.

Composition boundary (canonical owners are not redefined here):

- layered outcome axes stay in ``action-outcome.schema.json`` (#59) and are
  referenced, not duplicated;
- review semantics stay in ``review-receipt.schema.json`` (#93); a ``review``
  receipt references the composed #93 receipt by ref + digest;
- integration authority stays in the IntegrationLease profile (#92); an
  ``integration`` receipt records the resulting lineage and consumed authority;
- runtime acceptance stays in ``runtime-acceptance-receipt.schema.json``
  (#97) and is referenced by ``runtime_acceptance`` receipts;
- obligation/criterion semantics stay in ``change-acceptance.schema.json``
  (#113) and are bound by ref + digest only;
- conflict/amendment adjudication stays with its canonical owner (#127);
  this contract carries bounded lineage refs only.

Missing evidence is never green. ``PASS`` is the only green disposition and
``NOT_REQUIRED`` is green only when a trusted policy declares the gate
not-required for the exact work kind. Producer authority floors are enforced
mechanically: worker/model attestations can never satisfy deterministic
validation, independent verification, deployment or runtime gates.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

SCHEMA_VERSION = 1

_MAX_ID = 256
_MAX_REF = 512
_MAX_REASONS = 8
_MAX_EVIDENCE_REFS = 32
_MAX_ARTIFACT_REFS = 16
_MAX_DEPENDENCIES = 32
_MAX_INPUT_REFS = 64
_MAX_GRAPH_NODES = 512
_MAX_GRAPH_DEPTH = 64


def _sha256_hex(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def canonical_json_bytes(document: Mapping[str, object]) -> bytes:
    """Return the deterministic canonical serialization used for digests."""
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def payload_digest(document: Mapping[str, object]) -> str:
    """Digest the envelope content excluding the ``payload_digest`` field itself."""
    body = {key: value for key, value in document.items() if key != "payload_digest"}
    return _sha256_hex(canonical_json_bytes(body))


def evidence_set_digest(receipt_ids: Sequence[str]) -> str:
    """Digest the immutable ordered set of referenced receipt identities."""
    return _sha256_hex(canonical_json_bytes({"receipt_ids": list(receipt_ids)}))


def _require_bounded(value: object, name: str, max_length: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > max_length:
        raise ValueError(f"{name} must be a non-empty string of at most {max_length} characters")
    return value


def _optional_bounded(value: object, name: str, max_length: int) -> str | None:
    if value is None:
        return None
    return _require_bounded(value, name, max_length)


def _require_digest(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:") or len(value) != 71:
        raise ValueError(f"{name} must be a sha256 digest")
    hex_part = value.removeprefix("sha256:")
    if any(character not in "0123456789abcdef" for character in hex_part):
        raise ValueError(f"{name} must be a lowercase sha256 digest")
    return value


def _optional_digest(value: object, name: str) -> str | None:
    if value is None:
        return None
    return _require_digest(value, name)


def _require_sha(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 40
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a full 40-character git SHA")
    return value


def _optional_sha(value: object, name: str) -> str | None:
    if value is None:
        return None
    return _require_sha(value, name)


def _parse_utc(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an ISO-8601 UTC timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must carry an explicit timezone")
    return parsed.astimezone(UTC)


class ReceiptKind(StrEnum):
    CAPABILITY_ADMISSION = "capability_admission"
    IMPLEMENTATION = "implementation"
    VALIDATION = "validation"
    COMMAND_EXECUTION = "command_execution"
    PLAN_CHALLENGE = "plan_challenge"
    REVIEW = "review"
    WORK_COMPLETION = "work_completion"
    INDEPENDENT_VERIFICATION = "independent_verification"
    INTEGRATION_CANDIDATE = "integration_candidate"
    INTEGRATION = "integration"
    BUILD = "build"
    ARTIFACT_PUBLICATION = "artifact_publication"
    PUBLICATION = "publication"
    DEPLOYMENT = "deployment"
    RUNTIME_ACCEPTANCE = "runtime_acceptance"
    ROLLBACK = "rollback"


class AuthorityClass(StrEnum):
    DETERMINISTIC_TOOL = "deterministic_tool"
    TRUSTED_VALIDATOR = "trusted_validator"
    INDEPENDENT_VERIFIER = "independent_verifier"
    REVIEW_PROVIDER = "review_provider"
    WORKER_REPORT = "worker_report"
    AGENT_ATTESTATION = "agent_attestation"
    OPERATOR = "operator"
    EXTERNAL_PROVIDER_OBSERVATION = "external_provider_observation"


class SubjectKind(StrEnum):
    WORK_SPEC = "work_spec"
    PLANNING_BASE = "planning_base"
    EXECUTION_BASE = "execution_base"
    CANDIDATE_REVISION = "candidate_revision"
    REVIEWED_REVISION = "reviewed_revision"
    VERIFIED_REVISION = "verified_revision"
    INTEGRATION_CANDIDATE = "integration_candidate"
    INTEGRATED_REVISION = "integrated_revision"
    ARTIFACT = "artifact"
    PUBLICATION = "publication"
    DEPLOYMENT_TARGET = "deployment_target"
    OBSERVED_RUNTIME = "observed_runtime"
    TERMINAL_EVIDENCE = "terminal_evidence"
    CRITERION = "criterion"
    GATE = "gate"
    REPOSITORY = "repository"


class Disposition(StrEnum):
    PASS = "PASS"
    FAILED = "FAILED"
    NOT_REQUIRED = "NOT_REQUIRED"
    NOT_OBSERVED = "NOT_OBSERVED"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"
    INCONCLUSIVE = "INCONCLUSIVE"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class ExitProvenance(StrEnum):
    EXIT_PROVEN = "EXIT_PROVEN"
    EXIT_UNPROVEN = "EXIT_UNPROVEN"
    WRAPPER_EXIT_ONLY = "WRAPPER_EXIT_ONLY"


class DependencyKind(StrEnum):
    CANDIDATE_SOURCE = "candidate_source"
    BASE_TOPOLOGY = "base_topology"
    SOURCE_BLOB = "source_blob"
    REVIEW_INPUT = "review_input"
    REVIEW_PROVIDER = "review_provider"
    POLICY_REVISION = "policy_revision"
    WORK_CONTRACT = "work_contract"
    VERIFICATION_CORPUS = "verification_corpus"
    ARTIFACT_DIGEST = "artifact_digest"
    DEPLOYMENT_IDENTITY = "deployment_identity"
    RUNTIME_GENERATION = "runtime_generation"
    EVIDENCE_SET = "evidence_set"
    PLANNING_BASE = "planning_base"
    EXECUTION_ENVIRONMENT = "execution_environment"
    RUBRIC = "rubric"
    INTEGRATED_SOURCE = "integrated_source"


# Sentinel a caller sets on a ``CurrentIdentities`` field to declare that the
# current identity is *known to be unknown* (as opposed to ``None``, which
# means the axis is simply not tracked in this evaluation). Declared axes
# whose current identity equals this sentinel classify as non-green UNKNOWN.
UNKNOWN_IDENTITY = "?"


class Currentness(StrEnum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"
    SUPERSEDED = "SUPERSEDED"


class MergeStrategy(StrEnum):
    SQUASH = "squash"
    MERGE = "merge"
    REBASE = "rebase"
    FAST_FORWARD = "fast_forward"
    OTHER = "other"


class GateState(StrEnum):
    SATISFIED = "SATISFIED"
    PENDING = "PENDING"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class AdmissionOutcome(StrEnum):
    ADMITTED = "ADMITTED"
    REJECTED = "REJECTED"


class IndependenceState(StrEnum):
    INDEPENDENT = "INDEPENDENT"
    SAME_PRINCIPAL = "SAME_PRINCIPAL"
    PROVENANCE_UNKNOWN = "PROVENANCE_UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


# Producer authority floors per receipt kind. A floor is the minimum authority
# class that may truthfully claim a green disposition for that kind. The ladder
# is ordered from weakest to strongest; worker/model reports never clear
# deterministic-validation, independent-verification, integration, deployment
# or runtime floors.
_AUTHORITY_LADDER: tuple[AuthorityClass, ...] = (
    AuthorityClass.AGENT_ATTESTATION,
    AuthorityClass.WORKER_REPORT,
    AuthorityClass.REVIEW_PROVIDER,
    AuthorityClass.DETERMINISTIC_TOOL,
    AuthorityClass.TRUSTED_VALIDATOR,
    AuthorityClass.EXTERNAL_PROVIDER_OBSERVATION,
    AuthorityClass.INDEPENDENT_VERIFIER,
    AuthorityClass.OPERATOR,
)

_AUTHORITY_RANK = {authority: index for index, authority in enumerate(_AUTHORITY_LADDER)}

AUTHORITY_FLOOR_FOR_KIND: Mapping[ReceiptKind, AuthorityClass] = {
    ReceiptKind.CAPABILITY_ADMISSION: AuthorityClass.OPERATOR,
    ReceiptKind.IMPLEMENTATION: AuthorityClass.AGENT_ATTESTATION,
    ReceiptKind.VALIDATION: AuthorityClass.DETERMINISTIC_TOOL,
    ReceiptKind.COMMAND_EXECUTION: AuthorityClass.DETERMINISTIC_TOOL,
    ReceiptKind.PLAN_CHALLENGE: AuthorityClass.REVIEW_PROVIDER,
    ReceiptKind.REVIEW: AuthorityClass.REVIEW_PROVIDER,
    ReceiptKind.WORK_COMPLETION: AuthorityClass.AGENT_ATTESTATION,
    ReceiptKind.INDEPENDENT_VERIFICATION: AuthorityClass.INDEPENDENT_VERIFIER,
    ReceiptKind.INTEGRATION_CANDIDATE: AuthorityClass.DETERMINISTIC_TOOL,
    ReceiptKind.INTEGRATION: AuthorityClass.EXTERNAL_PROVIDER_OBSERVATION,
    ReceiptKind.BUILD: AuthorityClass.DETERMINISTIC_TOOL,
    ReceiptKind.ARTIFACT_PUBLICATION: AuthorityClass.EXTERNAL_PROVIDER_OBSERVATION,
    ReceiptKind.PUBLICATION: AuthorityClass.EXTERNAL_PROVIDER_OBSERVATION,
    ReceiptKind.DEPLOYMENT: AuthorityClass.EXTERNAL_PROVIDER_OBSERVATION,
    ReceiptKind.RUNTIME_ACCEPTANCE: AuthorityClass.INDEPENDENT_VERIFIER,
    ReceiptKind.ROLLBACK: AuthorityClass.EXTERNAL_PROVIDER_OBSERVATION,
}


def authority_satisfies(observed: AuthorityClass, floor: AuthorityClass) -> bool:
    return _AUTHORITY_RANK[observed] >= _AUTHORITY_RANK[floor]


def _envelope(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _string_list(value: object, name: str, max_items: int, max_length: int) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array")
    if len(value) > max_items:
        raise ValueError(f"{name} exceeds the bound of {max_items} items")
    return tuple(_require_bounded(item, f"{name}[{index}]", max_length) for index, item in enumerate(value))


@dataclass(frozen=True)
class TypedRef:
    ref_type: str
    namespace: str
    id: str
    digest: str | None

    @staticmethod
    def parse(value: object, name: str) -> TypedRef:
        document = _envelope(value, name)
        return TypedRef(
            ref_type=_require_bounded(document.get("ref_type"), f"{name}.ref_type", 32),
            namespace=_require_bounded(document.get("namespace"), f"{name}.namespace", 128),
            id=_require_bounded(document.get("id"), f"{name}.id", _MAX_REF),
            digest=_optional_digest(document.get("digest"), f"{name}.digest"),
        )


@dataclass(frozen=True)
class CommandEvidence:
    argv_digest: str
    exit_provenance: ExitProvenance
    exit_code: int | None
    report_digest: str | None
    working_directory: str | None
    runner_identity: str | None
    selected_test_ids: tuple[str, ...]

    @staticmethod
    def parse(value: object, name: str) -> CommandEvidence:
        document = _envelope(value, name)
        exit_code = document.get("exit_code")
        if isinstance(exit_code, bool) or (exit_code is not None and not isinstance(exit_code, int)):
            raise ValueError(f"{name}.exit_code must be an integer or null")
        return CommandEvidence(
            argv_digest=_require_digest(document.get("argv_digest"), f"{name}.argv_digest"),
            exit_provenance=ExitProvenance(
                _require_bounded(document.get("exit_provenance"), f"{name}.exit_provenance", 32)
            ),
            exit_code=exit_code,
            report_digest=_optional_digest(document.get("report_digest"), f"{name}.report_digest"),
            working_directory=_optional_bounded(
                document.get("working_directory"), f"{name}.working_directory", _MAX_REF
            ),
            runner_identity=_optional_bounded(document.get("runner_identity"), f"{name}.runner_identity", _MAX_ID),
            selected_test_ids=_string_list(
                document.get("selected_test_ids"), f"{name}.selected_test_ids", 256, _MAX_ID
            ),
        )

    def proven_pass(self) -> bool:
        """A green command result requires proven child exit plus report identity.

        A wrapper exiting zero around a piped child, a tail/tee exit, or a
        printed PASS marker is never authoritative test evidence.
        """
        return (
            self.exit_provenance is ExitProvenance.EXIT_PROVEN
            and self.exit_code == 0
            and self.report_digest is not None
        )


@dataclass(frozen=True)
class IntegrationLineage:
    strategy: MergeStrategy
    candidate_sha: str
    target_ref: str
    target_before_sha: str
    integrated_sha: str
    integrated_tree_sha: str | None
    lineage_proof_ref: str
    lease_ref: str | None
    operation_ref: str | None

    @staticmethod
    def parse(value: object, name: str) -> IntegrationLineage:
        document = _envelope(value, name)
        return IntegrationLineage(
            strategy=MergeStrategy(_require_bounded(document.get("strategy"), f"{name}.strategy", 32)),
            candidate_sha=_require_sha(document.get("candidate_sha"), f"{name}.candidate_sha"),
            target_ref=_require_bounded(document.get("target_ref"), f"{name}.target_ref", _MAX_ID),
            target_before_sha=_require_sha(document.get("target_before_sha"), f"{name}.target_before_sha"),
            integrated_sha=_require_sha(document.get("integrated_sha"), f"{name}.integrated_sha"),
            integrated_tree_sha=_optional_sha(document.get("integrated_tree_sha"), f"{name}.integrated_tree_sha"),
            lineage_proof_ref=_require_bounded(
                document.get("lineage_proof_ref"), f"{name}.lineage_proof_ref", _MAX_REF
            ),
            lease_ref=_optional_bounded(document.get("lease_ref"), f"{name}.lease_ref", _MAX_REF),
            operation_ref=_optional_bounded(document.get("operation_ref"), f"{name}.operation_ref", _MAX_REF),
        )

    def identity_transform(self) -> bool:
        """Whether the strategy produces a revision distinct from the candidate."""
        return self.strategy in (MergeStrategy.SQUASH, MergeStrategy.MERGE, MergeStrategy.REBASE)

    def lineage_defects(self) -> tuple[str, ...]:
        defects: list[str] = []
        if self.target_before_sha == self.integrated_sha:
            defects.append("INTEGRATION_TARGET_NOT_ADVANCED")
        if self.identity_transform() and self.candidate_sha == self.integrated_sha:
            defects.append("INTEGRATION_IDENTITY_COLLAPSE")
        if self.identity_transform() and self.integrated_tree_sha is None:
            defects.append("INTEGRATED_TREE_IDENTITY_MISSING")
        if self.strategy is MergeStrategy.OTHER and self.operation_ref is None:
            defects.append("INTEGRATION_OPERATION_REF_MISSING")
        return tuple(defects)


@dataclass(frozen=True)
class ReceiptEnvelope:
    receipt_id: str
    receipt_kind: ReceiptKind
    producer_system: str
    producer_principal: str | None
    producer_runtime_identity: str | None
    producer_generation: str | None
    authority_class: AuthorityClass
    subject_kind: SubjectKind
    subject_identity: str
    subject_repository: str | None
    subject_source_sha: str | None
    subject_tree_sha: str | None
    subject_candidate_sha: str | None
    subject_integrated_sha: str | None
    subject_planning_base_sha: str | None
    subject_execution_base_sha: str | None
    subject_artifact_digest: str | None
    subject_deployment_ref: str | None
    subject_runtime_generation: str | None
    correlation: Mapping[str, str | None]
    governing_contract: Mapping[str, str] | None
    admitted_work: Mapping[str, str] | None
    execution_environment: Mapping[str, str] | None
    policy_ref: str
    policy_revision: str | None
    policy_digest: str | None
    disposition: Disposition
    reason_codes: tuple[str, ...]
    layered_outcome_ref: str | None
    evidence_refs: tuple[TypedRef, ...]
    artifact_refs: tuple[TypedRef, ...]
    depends_on: tuple[tuple[str, DependencyKind], ...]
    command_evidence: CommandEvidence | None
    lineage: IntegrationLineage | None
    implementation_provenance_state: str | None
    implementation_principal_ref: str | None
    implementation_execution_ref: str | None
    implementation_agent_leg_ref: str | None
    implementation_producer_ref: str | None
    input_receipt_refs: tuple[str, ...]
    input_evidence_set_digest: str | None
    input_policy_revision: str | None
    mutation_authority: Mapping[str, str] | None
    conflict_refs: tuple[str, ...]
    supersedes_receipt_ref: str | None
    effective_evidence_revision: str | None
    observed_at: datetime
    expires_at: datetime | None
    payload_digest: str


def _parse_envelope(document: Mapping[str, object]) -> ReceiptEnvelope:
    kind = ReceiptKind(_require_bounded(document.get("receipt_kind"), "receipt_kind", 64))
    producer = _envelope(document.get("producer"), "producer")
    subject = _envelope(document.get("subject"), "subject")
    correlation = _envelope(document.get("correlation"), "correlation")
    policy = _envelope(document.get("policy"), "policy")
    outcome = _envelope(document.get("outcome"), "outcome")

    evidence_refs = tuple(
        TypedRef.parse(item, f"evidence_refs[{index}]")
        for index, item in enumerate(_as_list(document.get("evidence_refs"), "evidence_refs", _MAX_EVIDENCE_REFS))
    )
    artifact_refs = tuple(
        TypedRef.parse(item, f"artifact_refs[{index}]")
        for index, item in enumerate(_as_list(document.get("artifact_refs"), "artifact_refs", _MAX_ARTIFACT_REFS))
    )
    for artifact in artifact_refs:
        _require_digest(artifact.digest, "artifact_refs.digest")

    depends: list[tuple[str, DependencyKind]] = []
    for index, item in enumerate(_as_list(document.get("depends_on"), "depends_on", _MAX_DEPENDENCIES)):
        entry = _envelope(item, f"depends_on[{index}]")
        depends.append(
            (
                _require_bounded(entry.get("receipt_id"), f"depends_on[{index}].receipt_id", _MAX_ID),
                DependencyKind(
                    _require_bounded(entry.get("dependency_kind"), f"depends_on[{index}].dependency_kind", 64)
                ),
            )
        )

    command = document.get("command_evidence")
    lineage_document = document.get("lineage")

    implementation = document.get("implementation_provenance")
    inputs = document.get("inputs")
    mutation = document.get("mutation_authority")
    governing = document.get("governing_contract")
    admitted = document.get("admitted_work")
    environment = document.get("execution_environment")

    governing_contract: Mapping[str, str] | None = None
    if governing is not None:
        parsed = _envelope(governing, "governing_contract")
        governing_contract = {
            "contract_ref": _require_bounded(parsed.get("contract_ref"), "governing_contract.contract_ref", _MAX_REF),
            "contract_digest": _require_digest(parsed.get("contract_digest"), "governing_contract.contract_digest"),
        }

    admitted_work: Mapping[str, str] | None = None
    if admitted is not None:
        parsed = _envelope(admitted, "admitted_work")
        admitted_work = {
            "contract_ref": _require_bounded(parsed.get("contract_ref"), "admitted_work.contract_ref", _MAX_REF),
            "contract_digest": _require_digest(parsed.get("contract_digest"), "admitted_work.contract_digest"),
        }

    execution_environment: Mapping[str, str] | None = None
    if environment is not None:
        parsed = _envelope(environment, "execution_environment")
        execution_environment = {
            "environment_ref": _require_bounded(
                parsed.get("environment_ref"), "execution_environment.environment_ref", _MAX_REF
            ),
        }

    mutation_authority: Mapping[str, str] | None = None
    if mutation is not None:
        parsed = _envelope(mutation, "mutation_authority")
        mutation_authority = {
            "authority_kind": _require_bounded(parsed.get("authority_kind"), "mutation_authority.authority_kind", 64),
            "authority_ref": _require_bounded(
                parsed.get("authority_ref"), "mutation_authority.authority_ref", _MAX_REF
            ),
        }

    input_refs: tuple[str, ...] = ()
    input_digest: str | None = None
    input_policy_revision: str | None = None
    if inputs is not None:
        parsed = _envelope(inputs, "inputs")
        input_refs = _string_list(parsed.get("receipt_refs"), "inputs.receipt_refs", _MAX_INPUT_REFS, _MAX_ID)
        input_digest = _require_digest(parsed.get("evidence_set_digest"), "inputs.evidence_set_digest")
        input_policy_revision = _optional_bounded(parsed.get("policy_revision"), "inputs.policy_revision", 128)

    expires_at = document.get("expires_at")
    supersedes = document.get("supersedes_receipt_ref")

    return ReceiptEnvelope(
        receipt_id=_require_bounded(document.get("receipt_id"), "receipt_id", _MAX_ID),
        receipt_kind=kind,
        producer_system=_require_bounded(producer.get("system"), "producer.system", _MAX_ID),
        producer_principal=_optional_bounded(producer.get("principal"), "producer.principal", _MAX_ID),
        producer_runtime_identity=_optional_bounded(
            producer.get("runtime_identity"), "producer.runtime_identity", _MAX_ID
        ),
        producer_generation=_optional_bounded(producer.get("producer_generation"), "producer.producer_generation", 128),
        authority_class=AuthorityClass(
            _require_bounded(producer.get("authority_class"), "producer.authority_class", 64)
        ),
        subject_kind=SubjectKind(_require_bounded(subject.get("kind"), "subject.kind", 64)),
        subject_identity=_require_bounded(subject.get("identity"), "subject.identity", _MAX_REF),
        subject_repository=_optional_bounded(subject.get("repository"), "subject.repository", _MAX_REF),
        subject_source_sha=_optional_sha(subject.get("source_sha"), "subject.source_sha"),
        subject_tree_sha=_optional_sha(subject.get("tree_sha"), "subject.tree_sha"),
        subject_candidate_sha=_optional_sha(subject.get("candidate_sha"), "subject.candidate_sha"),
        subject_integrated_sha=_optional_sha(subject.get("integrated_sha"), "subject.integrated_sha"),
        subject_planning_base_sha=_optional_sha(subject.get("planning_base_sha"), "subject.planning_base_sha"),
        subject_execution_base_sha=_optional_sha(subject.get("execution_base_sha"), "subject.execution_base_sha"),
        subject_artifact_digest=_optional_digest(subject.get("artifact_digest"), "subject.artifact_digest"),
        subject_deployment_ref=_optional_bounded(subject.get("deployment_ref"), "subject.deployment_ref", _MAX_ID),
        subject_runtime_generation=_optional_bounded(
            subject.get("runtime_generation"), "subject.runtime_generation", 128
        ),
        correlation={
            key: _optional_bounded(value, f"correlation.{key}", _MAX_ID) for key, value in correlation.items()
        },
        governing_contract=governing_contract,
        admitted_work=admitted_work,
        execution_environment=execution_environment,
        policy_ref=_require_bounded(policy.get("policy_ref"), "policy.policy_ref", _MAX_REF),
        policy_revision=_optional_bounded(policy.get("policy_revision"), "policy.policy_revision", 128),
        policy_digest=_optional_digest(policy.get("policy_digest"), "policy.policy_digest"),
        disposition=Disposition(_require_bounded(outcome.get("disposition"), "outcome.disposition", 64)),
        reason_codes=_string_list(outcome.get("reason_codes"), "outcome.reason_codes", _MAX_REASONS, 128),
        layered_outcome_ref=_optional_bounded(
            outcome.get("layered_outcome_ref"), "outcome.layered_outcome_ref", _MAX_REF
        ),
        evidence_refs=evidence_refs,
        artifact_refs=artifact_refs,
        depends_on=tuple(depends),
        command_evidence=CommandEvidence.parse(command, "command_evidence") if command is not None else None,
        lineage=IntegrationLineage.parse(lineage_document, "lineage") if lineage_document is not None else None,
        implementation_provenance_state=(
            _require_bounded(
                _envelope(implementation, "implementation_provenance").get("provenance_state"),
                "implementation_provenance.provenance_state",
                16,
            )
            if implementation is not None
            else None
        ),
        implementation_principal_ref=(
            _optional_bounded(
                _envelope(implementation, "implementation_provenance").get("principal_ref"),
                "implementation_provenance.principal_ref",
                _MAX_ID,
            )
            if implementation is not None
            else None
        ),
        implementation_execution_ref=(
            _optional_bounded(
                _envelope(implementation, "implementation_provenance").get("execution_ref"),
                "implementation_provenance.execution_ref",
                _MAX_REF,
            )
            if implementation is not None
            else None
        ),
        implementation_agent_leg_ref=(
            _optional_bounded(
                _envelope(implementation, "implementation_provenance").get("agent_leg_ref"),
                "implementation_provenance.agent_leg_ref",
                _MAX_ID,
            )
            if implementation is not None
            else None
        ),
        implementation_producer_ref=(
            _optional_bounded(
                _envelope(implementation, "implementation_provenance").get("producer_ref"),
                "implementation_provenance.producer_ref",
                _MAX_REF,
            )
            if implementation is not None
            else None
        ),
        input_receipt_refs=input_refs,
        input_evidence_set_digest=input_digest,
        input_policy_revision=input_policy_revision,
        mutation_authority=mutation_authority,
        conflict_refs=_string_list(document.get("conflict_refs"), "conflict_refs", 8, _MAX_REF),
        supersedes_receipt_ref=_optional_bounded(supersedes, "supersedes_receipt_ref", _MAX_ID),
        effective_evidence_revision=_optional_bounded(
            document.get("effective_evidence_revision"), "effective_evidence_revision", 128
        ),
        observed_at=_parse_utc(document.get("observed_at"), "observed_at"),
        expires_at=_parse_utc(expires_at, "expires_at") if expires_at is not None else None,
        payload_digest=_require_digest(document.get("payload_digest"), "payload_digest"),
    )


def _as_list(value: object, name: str, max_items: int) -> list[object]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array")
    if len(value) > max_items:
        raise ValueError(f"{name} exceeds the bound of {max_items} items")
    return value


@dataclass(frozen=True)
class AdmissionDecision:
    outcome: AdmissionOutcome
    receipt: ReceiptEnvelope | None
    reasons: tuple[str, ...]


def admit_receipt(document: Mapping[str, object]) -> AdmissionDecision:
    """Admit one receipt envelope fail-closed.

    Structural integrity (payload digest), authority floors, kind-specific
    required sections, and exact-revision identity invariants are enforced
    here. A rejected receipt never enters an evidence graph.
    """
    reasons: list[str] = []
    envelope: ReceiptEnvelope | None = None
    try:
        envelope = _parse_envelope(document)
    except ValueError as error:
        return AdmissionDecision(AdmissionOutcome.REJECTED, None, (str(error),))

    assert envelope is not None
    if payload_digest(dict(document)) != envelope.payload_digest:
        reasons.append("PAYLOAD_DIGEST_MISMATCH")

    floor = AUTHORITY_FLOOR_FOR_KIND[envelope.receipt_kind]
    if envelope.disposition is Disposition.PASS and not authority_satisfies(envelope.authority_class, floor):
        reasons.append(f"AUTHORITY_FLOOR_UNMET:{envelope.receipt_kind.value}:{floor.value}")

    if envelope.receipt_kind is ReceiptKind.COMMAND_EXECUTION:
        command = envelope.command_evidence
        if command is None:
            reasons.append("COMMAND_EVIDENCE_REQUIRED")
        elif envelope.disposition is Disposition.PASS and not command.proven_pass():
            reasons.append("COMMAND_EXIT_NOT_PROVEN")

    if envelope.receipt_kind is ReceiptKind.INTEGRATION:
        lineage = envelope.lineage
        if lineage is None:
            reasons.append("INTEGRATION_LINEAGE_REQUIRED")
        else:
            reasons.extend(lineage.lineage_defects())
        if envelope.mutation_authority is None:
            reasons.append("MUTATION_AUTHORITY_REF_REQUIRED")

    if envelope.receipt_kind is ReceiptKind.INDEPENDENT_VERIFICATION:
        if envelope.implementation_provenance_state is None:
            reasons.append("IMPLEMENTATION_PROVENANCE_REQUIRED")
        if envelope.input_evidence_set_digest is None or not envelope.input_receipt_refs:
            reasons.append("INPUT_EVIDENCE_SET_REQUIRED")

    if envelope.expires_at is not None and envelope.expires_at < envelope.observed_at:
        reasons.append("EXPIRES_BEFORE_OBSERVED")

    if (
        envelope.disposition is Disposition.NOT_REQUIRED
        and envelope.policy_revision is None
        and envelope.policy_digest is None
    ):
        reasons.append("NOT_REQUIRED_REQUIRES_TRUSTED_POLICY")

    if reasons:
        return AdmissionDecision(AdmissionOutcome.REJECTED, None, tuple(reasons))
    return AdmissionDecision(AdmissionOutcome.ADMITTED, envelope, ())


@dataclass(frozen=True)
class EvidenceGraph:
    receipts: Mapping[str, ReceiptEnvelope]
    documents: Mapping[str, Mapping[str, object]]
    order: tuple[str, ...]


def build_graph(documents: Sequence[Mapping[str, object]]) -> EvidenceGraph:
    """Admit and link a bounded set of receipts into an immutable evidence graph."""
    if len(documents) > _MAX_GRAPH_NODES:
        raise ValueError(f"evidence graph exceeds the bound of {_MAX_GRAPH_NODES} receipts")
    receipts: dict[str, ReceiptEnvelope] = {}
    stored: dict[str, Mapping[str, object]] = {}
    order: list[str] = []
    for document in documents:
        decision = admit_receipt(document)
        if decision.outcome is not AdmissionOutcome.ADMITTED or decision.receipt is None:
            raise ValueError(f"receipt rejected: {', '.join(decision.reasons)}")
        receipt = decision.receipt
        if receipt.receipt_id in receipts:
            raise ValueError(f"duplicate receipt id {receipt.receipt_id}")
        receipts[receipt.receipt_id] = receipt
        stored[receipt.receipt_id] = dict(document)
        order.append(receipt.receipt_id)

    graph = EvidenceGraph(receipts=receipts, documents=stored, order=tuple(order))
    _assert_dependencies_resolve(graph)
    _assert_dependency_acyclic(graph)
    return graph


def _assert_dependencies_resolve(graph: EvidenceGraph) -> None:
    for receipt in graph.receipts.values():
        # ``depends_on`` entries are typed identity axes and may reference
        # receipts stored in another producer's store; staleness propagation
        # applies only when the upstream receipt is part of this graph.
        for input_ref in receipt.input_receipt_refs:
            if input_ref not in graph.receipts:
                raise ValueError(f"receipt {receipt.receipt_id} references unknown input receipt {input_ref}")


def _assert_dependency_acyclic(graph: EvidenceGraph) -> None:
    state: dict[str, int] = {}

    def visit(receipt_id: str, depth: int) -> None:
        if depth > _MAX_GRAPH_DEPTH:
            raise ValueError("evidence graph dependency depth exceeds the bound")
        marker = state.get(receipt_id, 0)
        if marker == 1:
            raise ValueError(f"dependency cycle through {receipt_id}")
        if marker == 2:
            return
        state[receipt_id] = 1
        for dependency_id, _kind in graph.receipts[receipt_id].depends_on:
            if dependency_id in graph.receipts:
                visit(dependency_id, depth + 1)
        state[receipt_id] = 2

    for receipt_id in graph.order:
        visit(receipt_id, 0)


@dataclass(frozen=True)
class CurrentIdentities:
    """Trusted current identity values used to derive evidence currentness.

    A ``None`` value means the current counterpart is unknown; declared
    dependencies with unknown current identity classify as ``UNKNOWN`` and are
    non-green for gates that require proven currentness.
    """

    candidate_sha: str | None = None
    planning_base_sha: str | None = None
    execution_base_sha: str | None = None
    integrated_sha: str | None = None
    source_blob_digest: str | None = None
    review_input_manifest_digest: str | None = None
    rubric_digest: str | None = None
    review_provider_generation: str | None = None
    policy_digest: str | None = None
    work_contract_digest: str | None = None
    verification_corpus_digest: str | None = None
    artifact_digest: str | None = None
    deployment_identity: str | None = None
    runtime_generation: str | None = None
    environment_generation: str | None = None

    def value_for(self, dependency: DependencyKind) -> str | None:
        return {
            DependencyKind.CANDIDATE_SOURCE: self.candidate_sha,
            DependencyKind.PLANNING_BASE: self.planning_base_sha,
            DependencyKind.BASE_TOPOLOGY: self.execution_base_sha,
            DependencyKind.INTEGRATED_SOURCE: self.integrated_sha,
            DependencyKind.SOURCE_BLOB: self.source_blob_digest,
            DependencyKind.REVIEW_INPUT: self.review_input_manifest_digest,
            DependencyKind.RUBRIC: self.rubric_digest,
            DependencyKind.REVIEW_PROVIDER: self.review_provider_generation,
            DependencyKind.POLICY_REVISION: self.policy_digest,
            DependencyKind.WORK_CONTRACT: self.work_contract_digest,
            DependencyKind.VERIFICATION_CORPUS: self.verification_corpus_digest,
            DependencyKind.ARTIFACT_DIGEST: self.artifact_digest,
            DependencyKind.DEPLOYMENT_IDENTITY: self.deployment_identity,
            DependencyKind.RUNTIME_GENERATION: self.runtime_generation,
            DependencyKind.EXECUTION_ENVIRONMENT: self.environment_generation,
            DependencyKind.EVIDENCE_SET: None,
        }[dependency]


@dataclass(frozen=True)
class ReceiptCurrentness:
    receipt_id: str
    status: Currentness
    invalidated_by: tuple[str, ...]
    reusable_for: tuple[str, ...]
    stale_dependencies: tuple[DependencyKind, ...]
    unknown_dependencies: tuple[DependencyKind, ...]


@dataclass(frozen=True)
class CurrentnessReport:
    receipts: Mapping[str, ReceiptCurrentness]
    minimum_revalidation: tuple[str, ...]
    current: CurrentIdentities = field(default_factory=lambda: CurrentIdentities())


def _implicit_dependency_axes(receipt: ReceiptEnvelope) -> Mapping[DependencyKind, str]:
    """Identity axes the receipt declares through its own subject bindings.

    Policy revision stays attribution-only: receipts bind the policy that
    governed them, but re-evaluation after a policy change is an explicit
    consumer decision (declared via ``depends_on``), not a universal
    invalidation rule.
    """
    axes: dict[DependencyKind, str] = {}
    if receipt.subject_candidate_sha is not None:
        axes[DependencyKind.CANDIDATE_SOURCE] = receipt.subject_candidate_sha
    if receipt.subject_planning_base_sha is not None:
        axes[DependencyKind.PLANNING_BASE] = receipt.subject_planning_base_sha
    if receipt.subject_execution_base_sha is not None:
        axes[DependencyKind.BASE_TOPOLOGY] = receipt.subject_execution_base_sha
    if receipt.subject_integrated_sha is not None:
        axes[DependencyKind.INTEGRATED_SOURCE] = receipt.subject_integrated_sha
    if receipt.subject_artifact_digest is not None:
        axes[DependencyKind.ARTIFACT_DIGEST] = receipt.subject_artifact_digest
    if receipt.subject_runtime_generation is not None:
        axes[DependencyKind.RUNTIME_GENERATION] = receipt.subject_runtime_generation
    if receipt.admitted_work is not None:
        axes[DependencyKind.WORK_CONTRACT] = receipt.admitted_work["contract_digest"]
    elif receipt.governing_contract is not None:
        axes[DependencyKind.WORK_CONTRACT] = receipt.governing_contract["contract_digest"]
    return axes


def derive_currentness(graph: EvidenceGraph, current: CurrentIdentities) -> CurrentnessReport:
    """Classify every receipt and derive the minimum revalidation set.

    Only receipts whose declared load-bearing dependencies changed become
    stale; unrelated exact-subject evidence stays ``CURRENT`` and must not be
    recomputed. A declared axis with unknown current identity classifies as
    ``UNKNOWN`` (non-green for proven-currentness gates). Supersession chains
    mark historical receipts ``SUPERSEDED`` while preserving their content.

    Receipts are classified in topological order over in-graph dependencies,
    so staleness propagation is independent of graph insertion order.
    """
    reports: dict[str, ReceiptCurrentness] = {}

    def superseded_by_any(receipt_id: str) -> bool:
        return any(other.supersedes_receipt_ref == receipt_id for other in graph.receipts.values())

    # Topological order over in-graph dependencies: upstream receipts are
    # classified before their dependents so staleness propagation is order
    # independent. The graph is acyclic by construction (build_graph).
    visited: set[str] = set()
    ordered: list[str] = []

    def visit(receipt_id: str, depth: int) -> None:
        if depth > _MAX_GRAPH_DEPTH:
            raise ValueError("evidence graph dependency depth exceeds the bound")
        if receipt_id in visited:
            return
        visited.add(receipt_id)
        for dependency_id, _kind in graph.receipts[receipt_id].depends_on:
            if dependency_id in graph.receipts:
                visit(dependency_id, depth + 1)
        ordered.append(receipt_id)

    for receipt_id in graph.order:
        visit(receipt_id, 0)

    for receipt_id in ordered:
        receipt = graph.receipts[receipt_id]
        stale: list[DependencyKind] = []
        unknown: list[DependencyKind] = []
        invalidated_by: list[str] = []
        reusable_for: list[str] = []

        for dependency_id, dependency_kind in receipt.depends_on:
            upstream = graph.receipts.get(dependency_id)
            if upstream is None:
                continue
            upstream_report = reports.get(dependency_id)
            if upstream_report is not None and upstream_report.status is not Currentness.CURRENT:
                invalidated_by.append(dependency_id)
                if upstream_report.status is Currentness.STALE:
                    stale.append(dependency_kind)
                else:
                    unknown.append(dependency_kind)

        implicit_axes = _implicit_dependency_axes(receipt)
        explicit_kinds = {kind for _dep_id, kind in receipt.depends_on}
        for axis in sorted(set(implicit_axes) | explicit_kinds, key=lambda kind: kind.value):
            bound = implicit_axes.get(axis)
            current_value = current.value_for(axis)
            if current_value == UNKNOWN_IDENTITY:
                # The caller established that this axis's current identity is
                # unknown: a declared load-bearing axis is never assumed green.
                unknown.append(axis)
            elif bound is not None and current_value is not None:
                if bound != current_value:
                    stale.append(axis)
                    invalidated_by.append(f"{axis.value}:{bound}")
            elif bound is None and current_value is not None:
                # The receipt omitted a binding whose current counterpart is
                # known: it cannot prove currentness on that axis.
                unknown.append(axis)
            # bound set + current None (untracked) -> no claim; bound None +
            # current untracked -> no claim. Untracked axes never demote.

        if superseded_by_any(receipt_id):
            status = Currentness.SUPERSEDED
        elif stale:
            status = Currentness.STALE
        elif unknown:
            status = Currentness.UNKNOWN
        else:
            status = Currentness.CURRENT
            reusable_for.append("declared_subject")

        reports[receipt_id] = ReceiptCurrentness(
            receipt_id=receipt_id,
            status=status,
            invalidated_by=tuple(dict.fromkeys(invalidated_by)),
            reusable_for=tuple(reusable_for),
            stale_dependencies=tuple(dict.fromkeys(stale)),
            unknown_dependencies=tuple(dict.fromkeys(unknown)),
        )

    minimum_revalidation = tuple(
        receipt_id
        for receipt_id in graph.order
        if reports[receipt_id].status in (Currentness.STALE, Currentness.UNKNOWN)
    )
    return CurrentnessReport(receipts=reports, minimum_revalidation=minimum_revalidation, current=current)


@dataclass(frozen=True)
class GateRequirement:
    gate_id: str
    required_kind: ReceiptKind
    subject_kind: SubjectKind | None = None
    subject_identity: str | None = None
    authority_floor: AuthorityClass | None = None
    require_current: bool = True
    distinct_producers: int = 1
    independence_required: bool = False
    # A receipt may only satisfy the gate through NOT_REQUIRED when the
    # evaluator itself derived the exemption from the trusted policy for this
    # exact work item; a receipt's own policy metadata is never that
    # authorization.
    allow_trusted_not_required: bool = False
    # Identity axes every qualifying receipt must bind (for example a final
    # exact-head review must carry the candidate source axis). Missing axis
    # bindings are non-green even when the axis is untracked.
    required_identity_axes: tuple[DependencyKind, ...] = ()


@dataclass(frozen=True)
class GateDecision:
    gate_id: str
    state: GateState
    qualifying_receipt_ids: tuple[str, ...]
    reasons: tuple[str, ...]

    @property
    def is_green(self) -> bool:
        return self.state is GateState.SATISFIED


def evaluate_gate(
    graph: EvidenceGraph,
    requirement: GateRequirement,
    currentness: CurrentnessReport | None = None,
) -> GateDecision:
    """Compose a policy gate from admitted receipts.

    ``PASS`` (or a trusted-policy ``NOT_REQUIRED``) with satisfied authority,
    proven currentness, and — when required — proven implementation/verifier
    separation is the only qualifying evidence. Missing, stale, unknown,
    weaker-authority or worker-reported evidence never satisfies the gate.
    """
    report = currentness if currentness is not None else derive_currentness(graph, CurrentIdentities())
    implicit_axes_of = _implicit_dependency_axes
    reasons: list[str] = []
    qualifying: list[str] = []
    failed: list[str] = []
    not_required_seen = False

    candidates = [receipt for receipt in graph.receipts.values() if receipt.receipt_kind is requirement.required_kind]
    if requirement.subject_kind is not None:
        candidates = [receipt for receipt in candidates if receipt.subject_kind is requirement.subject_kind]
    if requirement.subject_identity is not None:
        candidates = [receipt for receipt in candidates if receipt.subject_identity == requirement.subject_identity]

    if not candidates:
        return GateDecision(requirement.gate_id, GateState.PENDING, (), ("NO_RECEIPT_FOR_GATE",))

    seen_principals: set[str] = set()
    for receipt in candidates:
        axes = implicit_axes_of(receipt)
        missing_axes = [axis for axis in requirement.required_identity_axes if axis not in axes]
        if missing_axes:
            # A required identity axis is not bound by this receipt at all:
            # it cannot prove exact-subject currentness for the gate.
            reasons.append(f"MISSING_IDENTITY_AXIS:{receipt.receipt_id}:{','.join(a.value for a in missing_axes)}")
            continue
        axis_untracked = [axis for axis in requirement.required_identity_axes if report.current.value_for(axis) is None]
        if axis_untracked:
            reasons.append(
                f"AXIS_CURRENT_IDENTITY_UNTRACKED:{receipt.receipt_id}:{','.join(a.value for a in axis_untracked)}"
            )
            continue
        receipt_status = report.receipts[receipt.receipt_id].status
        if receipt_status is not Currentness.CURRENT and requirement.require_current:
            reasons.append(f"NOT_CURRENT:{receipt.receipt_id}:{receipt_status.value}")
            continue
        if receipt.disposition is Disposition.FAILED:
            # A failing receipt on the evaluated subject (for example a
            # required reviewer finding a defect after another reviewer
            # approved, or conflicting evidence) blocks the gate; a second
            # PASS receipt never compensates for it.
            failed.append(receipt.receipt_id)
            reasons.append(f"RECEIPT_FAILED:{receipt.receipt_id}")
            continue
        if receipt.disposition is Disposition.NOT_REQUIRED:
            if not requirement.allow_trusted_not_required:
                not_required_seen = True
                reasons.append(f"NOT_REQUIRED_UNAUTHORIZED:{receipt.receipt_id}")
                continue
            qualifying.append(receipt.receipt_id)
            continue
        if receipt.disposition is not Disposition.PASS:
            reasons.append(f"NOT_PASS:{receipt.receipt_id}:{receipt.disposition.value}")
            continue
        floor = requirement.authority_floor or AUTHORITY_FLOOR_FOR_KIND[receipt.receipt_kind]
        if not authority_satisfies(receipt.authority_class, floor):
            reasons.append(f"AUTHORITY_BELOW_FLOOR:{receipt.receipt_id}:{receipt.authority_class.value}")
            continue
        if requirement.required_kind is ReceiptKind.INDEPENDENT_VERIFICATION:
            independence = evaluate_independence(receipt)
            if independence is not IndependenceState.INDEPENDENT:
                reasons.append(f"INDEPENDENCE_UNPROVEN:{receipt.receipt_id}:{independence.value}")
                continue
        if requirement.distinct_producers > 1:
            principal = receipt.producer_principal or receipt.producer_system
            if principal in seen_principals:
                reasons.append(f"DUPLICATE_PRODUCER:{receipt.receipt_id}:{principal}")
                continue
            seen_principals.add(principal)
        qualifying.append(receipt.receipt_id)

    if failed:
        return GateDecision(requirement.gate_id, GateState.BLOCKED, tuple(qualifying), tuple(reasons))
    if not_required_seen and not qualifying:
        return GateDecision(requirement.gate_id, GateState.BLOCKED, (), tuple(reasons))
    if len(qualifying) >= requirement.distinct_producers:
        return GateDecision(requirement.gate_id, GateState.SATISFIED, tuple(qualifying), ())
    if qualifying:
        reasons.append("INSUFFICIENT_QUALIFIED_EVIDENCE")
        return GateDecision(requirement.gate_id, GateState.BLOCKED, tuple(qualifying), tuple(reasons))
    return GateDecision(requirement.gate_id, GateState.UNKNOWN, (), tuple(reasons) or ("NO_QUALIFYING_EVIDENCE",))


def evaluate_independence(receipt: ReceiptEnvelope) -> IndependenceState:
    """Derive verification independence from implementation/verifier provenance.

    Unknown implementation provenance is never interpreted as separation; the
    verifier cannot self-mint independence through receipt fields.
    """
    if receipt.receipt_kind is not ReceiptKind.INDEPENDENT_VERIFICATION:
        return IndependenceState.NOT_APPLICABLE
    if receipt.implementation_provenance_state == "unknown":
        return IndependenceState.PROVENANCE_UNKNOWN
    implementation_principal = receipt.implementation_principal_ref
    verifier_principal = receipt.producer_principal
    if implementation_principal is None or verifier_principal is None:
        return IndependenceState.PROVENANCE_UNKNOWN
    if implementation_principal == verifier_principal:
        return IndependenceState.SAME_PRINCIPAL
    return IndependenceState.INDEPENDENT


@dataclass(frozen=True)
class LineageStep:
    gate_id: str
    requirement: GateRequirement


def evaluate_lineage_chain(
    graph: EvidenceGraph,
    steps: Sequence[LineageStep],
    currentness: CurrentnessReport | None = None,
) -> tuple[GateDecision, ...]:
    """Evaluate an ordered delivery chain.

    A successful earlier stage never compensates for a missing or non-green
    later required stage: every declared step is evaluated and returned.
    """
    return tuple(evaluate_gate(graph, step.requirement, currentness) for step in steps)


def verify_document(document: Mapping[str, object]) -> AdmissionDecision:
    """Validate one envelope document end-to-end (digest + semantic admission)."""
    decision = admit_receipt(document)
    if decision.outcome is AdmissionOutcome.ADMITTED and decision.receipt is not None:
        expected = payload_digest(dict(document))
        if expected != decision.receipt.payload_digest:
            return AdmissionDecision(AdmissionOutcome.REJECTED, None, ("PAYLOAD_DIGEST_MISMATCH",))
    return decision


def _schema_error(document: object, schema: Mapping[str, object]) -> str | None:
    """Validate against the published schema; returns None when unavailable or valid."""
    try:
        import jsonschema
    except ModuleNotFoundError:  # pragma: no cover - schema validation is optional at runtime
        return None
    try:
        jsonschema.validate(document, schema)
    except jsonschema.ValidationError as error:
        return str(error.message)
    return None


def _run(argv: Sequence[str]) -> int:
    if len(argv) != 1:
        print("usage: python contracts/execution_evidence.py <receipts.json>", file=sys.stderr)
        return 2
    path = Path(argv[0])
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        print("input must be a JSON array of receipt envelopes", file=sys.stderr)
        return 2
    schema_path = Path(__file__).with_name("execution-evidence.schema.json")
    schema: Mapping[str, object] = json.loads(schema_path.read_text(encoding="utf-8"))
    failures = 0
    for index, document in enumerate(raw):
        error = _schema_error(document, schema)
        if error is not None:
            print(f"receipt[{index}] schema: {error}")
            failures += 1
            continue
        decision = verify_document(document)
        if decision.outcome is not AdmissionOutcome.ADMITTED:
            print(f"receipt[{index}] rejected: {', '.join(decision.reasons)}")
            failures += 1
        else:
            print(f"receipt[{index}] admitted")
    return 1 if failures else 0


def main(argv: Sequence[str] | None = None) -> int:
    return _run(list(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
