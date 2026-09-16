#!/usr/bin/env python3
"""Validate MCP Steward v3 contracts and cross-contract enforcement context."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "contracts"
_SCHEMA_FILES = {
    "profile": "steward-profile.schema.json",
    "job": "steward-job.schema.json",
    "receipt": "external-operation-receipt.schema.json",
    "evidence": "steward-evidence.schema.json",
    "handoff": "steward-handoff.schema.json",
    "lineage": "steward-lineage.schema.json",
    "completion": "steward-completion.schema.json",
    "upstream": "upstream-capability.schema.json",
    "state-machine": "steward-state-machine.schema.json",
    "mutation-policy": "steward-mutation-policy.schema.json",
    "proof": "steward-proof-recipe.schema.json",
    "acceptance": "steward-acceptance.schema.json",
}
_AUTHORITY_RANK = {"advisory": 0, "observed": 1, "verified": 2, "independent": 3}
_TERMINAL = {"completed", "completed-with-gaps", "failed", "cancelled", "superseded"}
_PLACEHOLDER_AUTHORITY = {"", "unknown", "head", "latest", "default", "unset", "none"}
_TIMESTAMP_FIELDS = {
    "job": ("createdAt", "updatedAt", "heartbeatAt", "progressAt", "deadlineAt", "finalizationStartsAt"),
    "receipt": ("createdAt", "observedAt", "nextRetryAt", "nextReconcileAt"),
    "evidence": ("observedAt", "expiresAt"),
    "handoff": ("sealedAt",),
    "lineage": ("updatedAt",),
    "completion": ("evaluatedAt",),
}


def _load(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    return json.loads(text) if path.suffix.casefold() == ".json" else yaml.safe_load(text)


def _schema(kind: str) -> dict[str, Any]:
    value = json.loads((CONTRACTS / _SCHEMA_FILES[kind]).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(value)
    return value


def _schema_findings(kind: str, value: Any) -> list[str]:
    errors = sorted(
        Draft202012Validator(_schema(kind), format_checker=FormatChecker()).iter_errors(value),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    )
    return [f"schema:{'.'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}" for error in errors]


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("date-time must include a timezone")
    return parsed.astimezone(UTC)


def _timestamp_findings(kind: str, value: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    for field in _TIMESTAMP_FIELDS.get(kind, ()):
        timestamp = value.get(field)
        if timestamp is None:
            continue
        try:
            _parse_timestamp(str(timestamp))
        except ValueError as exc:
            findings.append(f"schema:{field}: {exc}")
    if kind == "job" and isinstance(value.get("lease"), dict):
        try:
            _parse_timestamp(str(value["lease"].get("expiresAt", "")))
        except ValueError as exc:
            findings.append(f"schema:lease.expiresAt: {exc}")
    return findings


def compute_handoff_digest(value: dict[str, Any]) -> str:
    unsigned = {key: item for key, item in value.items() if key != "digest"}
    canonical = json.dumps(unsigned, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _capability_semantic_projection(value: dict[str, Any]) -> dict[str, Any]:
    projected = json.loads(json.dumps(value))
    contract = projected.get("contract")
    if not isinstance(contract, dict):
        raise ValueError("capability contract is required")
    contract.pop("digest", None)
    return projected


def compute_capability_contract_digest(value: dict[str, Any]) -> str:
    canonical = json.dumps(
        _capability_semantic_projection(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _profile_findings(value: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    authority = value["authority"]
    overlap = sorted(set(authority["owns"]) & set(authority["never_claims"]))
    if overlap:
        findings.append("authority: owns and never_claims overlap: " + ", ".join(overlap))
    durability = value["durability"]
    if durability["profile"] != "constrained-file" and not durability["transactional_store_required"]:
        findings.append("durability: durable profiles require a transactional store")
    topology = durability["topology"]
    if topology["writer_model"] == "single-owner" and topology["server_process_multiplicity"] != "single":
        findings.append("durability: single-owner writer model cannot be paired with multi-process servers")
    if topology["store_ownership"] == "shared" and topology["writer_model"] != "multi-writer":
        findings.append("durability: shared store ownership requires a multi-writer writer model")
    if durability["profile"] == "constrained-file" and (
        topology["writer_model"] == "multi-writer" or topology["shared_state_scope"] != "process"
    ):
        findings.append("durability: constrained-file profile supports only single-owner, process-scoped state")
    if (
        topology["restart_boundary"] == "cluster"
        and "host-power-loss" not in durability["crash_model"]
        and "power-loss" not in durability["crash_model"]
    ):
        findings.append("durability: cluster restart boundary requires a declared host/power-loss crash model")
    required = set(value["subject_identity"]["required_dimensions"])
    freshness = set(value["subject_identity"]["freshness_dimensions"])
    if freshness - required:
        findings.append(
            "subject_identity: freshness dimensions must also be required dimensions: "
            + ", ".join(sorted(freshness - required))
        )
    identity = value["subject_identity"]
    if value["features"]["exact_candidate_binding"] and not identity["candidate_required_for_publication"]:
        findings.append("subject_identity: exact_candidate_binding requires candidate_required_for_publication=true")
    obligation_ids = [item["id"] for item in value["completion"]["obligations"]]
    duplicates = sorted(item for item in set(obligation_ids) if obligation_ids.count(item) > 1)
    if duplicates:
        findings.append("completion: duplicate obligation ids: " + ", ".join(duplicates))
    fallback = value["credentials"]["fallback"]
    if fallback["enabled"] and (not fallback["preserve_principal_scope"] or not fallback["preserve_target"]):
        findings.append("credentials: fallback must preserve principal/scope and target")
    features = value["features"]
    external = value["external_operations"]
    if features["durable_external_async"] and external["worker_wait_policy"] != "external-maintenance":
        findings.append("external_operations: durable_external_async requires worker_wait_policy=external-maintenance")
    if features["external_cancellation"] and not external["cancellation_reconciliation_required"]:
        findings.append("external_operations: external_cancellation requires cancellation reconciliation")
    supervised = authority["parent_completion"] == "explicit-contract-only"
    parent_contract = value.get("parent_contract")
    if supervised and not isinstance(parent_contract, dict):
        findings.append("authority: parent_completion=explicit-contract-only requires a parent_contract snapshot")
    if not supervised and parent_contract is not None:
        findings.append("authority: standalone steward must not declare a parent_contract")
    if isinstance(parent_contract, dict):
        delegated = set(parent_contract["delegated_capabilities"])
        forbidden = set(parent_contract["forbidden_capabilities"])
        overlap = sorted(delegated & forbidden)
        if overlap:
            findings.append("parent_contract: capability is both delegated and forbidden: " + ", ".join(overlap))
        exceeds = sorted(delegated - set(authority["may_mutate"]))
        if exceeds:
            findings.append(
                "parent_contract: delegated capabilities exceed locally configured authority: " + ", ".join(exceeds)
            )
        if (
            parent_contract["parent_completion_authority"] == "explicit_mutation"
            and authority["parent_completion"] != "explicit-contract-only"
        ):
            findings.append("parent_contract: explicit_mutation completion authority requires supervised mode")
    return findings


def _parent_contract_digest(snapshot: dict[str, Any]) -> str:
    projected = json.loads(json.dumps(snapshot))
    projected.pop("digest", None)
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(projected, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()
    )


def _obligation_set_digest(snapshot: dict[str, Any]) -> str:
    projected = {"revision": snapshot["revision"], "obligations": snapshot["obligations"]}
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(projected, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest()
    )


def _job_findings(value: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    if value["status"] in _TERMINAL and value.get("lease") is not None:
        findings.append("job: terminal state must not retain an active lease")
    if value["status"] == "superseded" and value.get("domainOutcome") not in {None, "superseded"}:
        findings.append("job: superseded work cannot carry an actionable domain outcome")
    if value["status"] == "blocked" and not value.get("blockedReason"):
        findings.append("job: blocked state requires blockedReason")
    if value["progressRevision"] < 0:
        findings.append("job: progressRevision must be non-negative")
    parent_contract = value.get("parentContract")
    obligation_set = value.get("obligationSet")
    if isinstance(parent_contract, dict):
        if parent_contract["mode"] != "supervised":
            findings.append("job: admitted parentContract must use supervised mode")
        elif _parent_contract_digest(parent_contract) != parent_contract["digest"]:
            findings.append("job: parentContract digest does not bind the snapshot contents")
    if value["status"] in {"queued", "running", "waiting-external", "finalizing", "completed", "completed-with-gaps"}:
        if not isinstance(obligation_set, dict):
            findings.append("job: admitted work requires an obligationSet snapshot at admission")
        elif _obligation_set_digest(obligation_set) != obligation_set["digest"]:
            findings.append("job: obligationSet digest does not bind the snapshot contents")
    if (
        value["status"] in {"completed", "completed-with-gaps"}
        and parent_contract is None
        and value.get("failure") is None
    ):
        pass  # standalone completion is valid; obligation snapshot already required above
    return findings


def _receipt_findings(value: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    if value["operationKind"] in {"submit", "cancel", "mutation"} and not value.get("mutationDecisionRef"):
        findings.append("receipt: stateful operation requires mutationDecisionRef")
    delivery = value["delivery"]
    retry = value["retryDisposition"]
    if delivery == "delivery-unknown" and retry != "reconcile-first":
        findings.append("receipt: delivery-unknown requires retryDisposition=reconcile-first")
    if delivery == "not-delivered" and value.get("remoteHandle"):
        findings.append("receipt: not-delivered cannot claim a remote handle")
    if value["state"] == "reserved" and delivery != "not-delivered":
        findings.append("receipt: reserved operation cannot claim delivery")
    if value["state"] == "reserved" and retry != "forbidden":
        findings.append("receipt: reserved operation cannot be retry-eligible")
    if delivery == "delivery-unknown" and value.get("nextRetryAt") is not None:
        findings.append("receipt: delivery-unknown cannot schedule retry before reconciliation")
    if value["operationKind"] == "cancel" and delivery == "delivery-unknown" and retry != "reconcile-first":
        findings.append("receipt: ambiguous cancellation must reconcile before replay")
    return findings


def _evidence_findings(value: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    binding = value["binding"]
    required = set(binding["required"])
    satisfied = set(binding["satisfied"])
    if not satisfied <= required:
        findings.append("evidence: binding satisfied dimensions must be declared required dimensions")
    expected_status = "complete" if required <= satisfied else ("partial" if satisfied else "unknown")
    if binding["status"] != expected_status:
        findings.append(f"evidence: binding status must be {expected_status}")
    coverage = value["coverage"]
    if coverage["observed"] > coverage["required"]:
        findings.append("evidence: coverage observed cannot exceed required")
    if coverage["state"] == "complete" and coverage["observed"] < coverage["required"]:
        findings.append("evidence: complete coverage requires all required members observed")
    if binding["status"] != "complete" and value["authorityClass"] in {"verified", "independent"}:
        findings.append("evidence: incomplete binding cannot carry verified/independent authority")
    return findings


def _handoff_semantic_findings(value: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    status = value["status"]
    if status in {"failed", "cancelled", "blocked", "superseded"} and value["actionable"]:
        findings.append(f"handoff: {status} handoff cannot be actionable")
    if status == "completed" and value["gaps"]:
        findings.append("handoff: completed handoff cannot retain unresolved gaps")
    if status == "completed-with-gaps" and not value["gaps"]:
        findings.append("handoff: completed-with-gaps requires at least one gap")
    if status in {"completed", "completed-with-gaps"} and value.get("outcome") is None:
        findings.append("handoff: completed handoff requires a domain outcome")
    return findings


def _handoff_digest_findings(value: dict[str, Any]) -> list[str]:
    expected = compute_handoff_digest(value)
    return [] if value.get("digest") == expected else [f"handoff: digest mismatch; expected {expected}"]


def _upstream_findings(value: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    contract = value["contract"]
    expected_digest = compute_capability_contract_digest(value)
    if contract["digest"] != expected_digest:
        findings.append("upstream: capability contract digest does not bind complete reviewed semantic definition")
    if contract.get("digest_semantics") != "capability-semantic-v1":
        findings.append("upstream: capability contract digest_semantics must be capability-semantic-v1")
    if contract["id"] != value["capability_id"]:
        findings.append("upstream: capability contract id must equal capability_id")
    if value["contract"]["id"].casefold() in _PLACEHOLDER_AUTHORITY:
        findings.append("upstream: capability contract id cannot be a fabricated placeholder")
    if value["interaction"] == "stateful":
        recoverable = value["recovery"] in {"replay-safe", "status-by-handle", "resume-by-handle"}
        reconcilable = value["reconciliation"]["ambiguous_delivery"] != "unsupported"
        if not recoverable or not reconcilable:
            findings.append("upstream: stateful capability requires recovery and ambiguous-delivery reconciliation")
    if value["delivery"] == "durable-async":
        if value["recovery"] not in {"status-by-handle", "resume-by-handle"}:
            findings.append("upstream: durable-async capability requires status/resume by handle")
        progress = value["progress"]
        if progress["kind"] == "none" or not progress["stable_revision"]:
            findings.append("upstream: durable-async capability requires stable semantic progress revision")
        if progress["worker_wait_policy"] != "external-maintenance":
            findings.append("upstream: durable-async waiting must use external-maintenance lane")
    cancellation = value["cancellation"]
    if cancellation["mode"] == "none":
        if cancellation["delivery_model"] != "none":
            findings.append("upstream: cancellation mode none requires delivery_model=none")
    elif cancellation["delivery_model"] == "stateful":
        if cancellation["reconciliation"] == "unsupported":
            findings.append("upstream: stateful cancellation requires reconciliation")
        if not cancellation["local_terminal_requires_remote_resolution"]:
            findings.append("upstream: stateful cancellation must not equate local terminal state with remote stop")
    return findings


def _lineage_findings(value: dict[str, Any]) -> list[str]:
    return (
        ["lineage: current job cannot also be superseded"] if value["currentJobId"] in value["supersededJobIds"] else []
    )


def _completion_findings(value: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    obligations = value["obligations"]
    ids = [item["id"] for item in obligations]
    duplicates = sorted(item for item in set(ids) if ids.count(item) > 1)
    if duplicates:
        findings.append("completion: duplicate obligation ids: " + ", ".join(duplicates))
    for obligation in obligations:
        location = f"completion: obligation {obligation['id']}"
        if obligation["state"] == "satisfied" and not obligation["evidenceRefs"]:
            findings.append(f"{location} satisfied without evidence")
        if obligation["state"] == "not-applicable" and not obligation.get("rationale"):
            findings.append(f"{location} not-applicable without rationale")
        if obligation["state"] == "waived" and not obligation.get("authorityRef"):
            findings.append(f"{location} waived without authority")
    unresolved = any(item["state"] == "unsatisfied" for item in obligations)
    if value["disposition"] == "eligible" and unresolved:
        findings.append("completion: eligible disposition has unsatisfied obligations")
    if value["disposition"] == "eligible" and (value["ambiguousOperationRefs"] or value["ambiguousCancellationRefs"]):
        findings.append("completion: eligible disposition has unresolved external effects")
    if value["disposition"] == "eligible" and not value.get("obligationSetDigest"):
        findings.append("completion: eligible disposition must bind the admitted obligationSet digest")
    parent = value.get("parentContract")
    if value["disposition"] == "eligible" and parent is not None and parent["mode"] != "supervised":
        findings.append("completion: eligible supervised completion must reference a supervised parent contract")
    return findings


def _state_machine_findings(value: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    states = {item["id"]: item for item in value["states"]}
    if len(states) != len(value["states"]):
        findings.append("state-machine: duplicate state ids")
    transition_ids = [item["id"] for item in value["transitions"]]
    if len(set(transition_ids)) != len(transition_ids):
        findings.append("state-machine: duplicate transition ids")
    for transition in value["transitions"]:
        if transition["from"] not in states or transition["to"] not in states:
            findings.append(f"state-machine: transition {transition['id']} references unknown state")
        if transition["effect"] in {"external-stateful", "publication"} and not transition["mutation_gate"]:
            findings.append(f"state-machine: transition {transition['id']} requires mutation_gate=true")
    for state in value["states"]:
        if not state["terminal"] and state["owner_lane"] == "none" and state["recovery"] != "blocked":
            findings.append(f"state-machine: nonterminal state {state['id']} has no owner/recovery path")
    return findings


def _mutation_policy_findings(value: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    ids = [item["id"] for item in value["effects"]]
    if len(set(ids)) != len(ids):
        findings.append("mutation-policy: duplicate effect ids")
    for effect in value["effects"]:
        location = f"mutation-policy: effect {effect['id']}"
        if effect["authority_source"].casefold() in _PLACEHOLDER_AUTHORITY:
            findings.append(f"{location} has fabricated/unknown authority source")
        if "Admitted" not in effect["typed_outcomes"]:
            findings.append(f"{location} must include typed outcome Admitted")
        if effect["durable_operation_required"] and not effect["pre_dispatch_commit_required"]:
            findings.append(f"{location} durable operation must commit before dispatch")
        if effect["durable_operation_required"] and effect["ambiguity_disposition"] == "none":
            findings.append(f"{location} stateful effect requires ambiguity disposition")
        if effect["durable_operation_required"] and not effect["budget_reservation_required"]:
            findings.append(f"{location} must reserve budget before start")
        if effect["budget_reservation_required"] and int(effect["finalization_reserve_ms"]) <= 0:
            findings.append(f"{location} must reserve deterministic finalization budget")
        contract = effect["capability_contract"]
        if contract["id"] != effect["capability_ref"]:
            findings.append(f"{location} capability contract id must equal capability_ref")
    return findings


def _proof_findings(value: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    producers = {item["producer_id"]: item for item in value["producers"]}
    if len(producers) != len(value["producers"]):
        findings.append("proof: duplicate producer ids")
    criteria = {item["criterion_id"]: item for item in value["criteria"]}
    if len(criteria) != len(value["criteria"]):
        findings.append("proof: duplicate criterion ids")
    for criterion in value["criteria"]:
        location = f"proof: criterion {criterion['criterion_id']}"
        approved = criterion["approved_producers"]
        missing = sorted(set(approved) - set(producers))
        if missing:
            findings.append(f"{location} references unknown producers: {', '.join(missing)}")
            continue
        for producer_id in approved:
            producer = producers[producer_id]
            if criterion["canonical_claim"] not in producer["claim_classes"]:
                findings.append(f"{location} producer {producer_id} cannot produce canonical claim")
            if not set(criterion["subject_dimensions"]) <= set(producer["subject_dimensions"]):
                findings.append(f"{location} producer {producer_id} cannot observe required subject dimensions")
            if not set(criterion["binding_requirements"]) <= set(producer["binding_requirements"]):
                findings.append(f"{location} producer {producer_id} cannot satisfy binding requirements")
            if _AUTHORITY_RANK[producer["authority_ceiling"]] < _AUTHORITY_RANK[criterion["required_authority"]]:
                findings.append(f"{location} producer {producer_id} authority ceiling is below criterion requirement")
        if criterion["required_authority"] == "independent" and not any(
            producers[item]["independence"] == "independent" for item in approved
        ):
            findings.append(f"{location} requires independent authority but has no independent producer")
    return findings


def _acceptance_findings(value: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    lanes = set(value["required_lanes"])
    baseline = {"implementer", "canonical-full", "fault-restart", "inherited-mcp", "exact-artifact"}
    if not baseline <= lanes:
        findings.append("acceptance: structural conformance requires canonical full/fault/inherited/exact lanes")
    if value["claim_class"] == "production-workflow":
        required = baseline | {"independent-delta", "live-full-path"}
        if not required <= lanes:
            findings.append("acceptance: production-workflow requires independent-delta and live-full-path lanes")
        if not value["independent_required"] or not value["live_full_path_required"]:
            findings.append("acceptance: production-workflow must require independent and live full-path evidence")
        exact = value["exact_artifact"]
        if not all(
            (exact["full_path_required"], exact["runtime_prerequisites_declared"], exact["restart_boundary_required"])
        ):
            findings.append("acceptance: production exact artifact must cover full path, prerequisites, and restart")
    return findings


def validate_document(kind: str, value: Any) -> list[str]:
    if kind not in _SCHEMA_FILES:
        raise ValueError(f"unknown document kind: {kind}")
    findings = _schema_findings(kind, value)
    if findings or not isinstance(value, dict):
        return findings
    findings.extend(_timestamp_findings(kind, value))
    if findings:
        return findings
    semantic = {
        "profile": _profile_findings,
        "job": _job_findings,
        "receipt": _receipt_findings,
        "evidence": _evidence_findings,
        "handoff": lambda item: _handoff_semantic_findings(item) + _handoff_digest_findings(item),
        "upstream": _upstream_findings,
        "lineage": _lineage_findings,
        "completion": _completion_findings,
        "state-machine": _state_machine_findings,
        "mutation-policy": _mutation_policy_findings,
        "proof": _proof_findings,
        "acceptance": _acceptance_findings,
    }.get(kind)
    return findings + ([] if semantic is None else semantic(value))


def validate_handoff_current(
    value: dict[str, Any],
    *,
    current_job_id: str,
    current_generation: int,
    current_lineage_id: str,
    current_subject: dict[str, Any],
    current_candidate: dict[str, Any] | None = None,
) -> list[str]:
    findings = _schema_findings("handoff", value) + _timestamp_findings("handoff", value)
    if findings:
        return findings
    findings.extend(_handoff_semantic_findings(value))
    if findings:
        return findings
    if value["actionable"] and value["lineageId"] != current_lineage_id:
        return ["handoff: stale lineage cannot be actionable"]
    if value["actionable"] and (value["jobId"] != current_job_id or value["generation"] != current_generation):
        return ["handoff: stale job/generation cannot be actionable"]
    if value["actionable"] and value["subject"] != current_subject:
        return ["handoff: stale subject identity cannot be actionable"]
    if value["actionable"] and value.get("candidate") is not None and current_candidate is None:
        return ["handoff: actionable candidate binding requires current candidate context"]
    if value["actionable"] and current_candidate is not None and value.get("candidate") != current_candidate:
        return ["handoff: stale candidate identity cannot be actionable"]
    return _handoff_digest_findings(value)


def _proof_criteria(proof_recipe: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item["criterion_id"]): item for item in proof_recipe.get("criteria", []) if isinstance(item, dict)}


def _coverage_satisfies(criterion: dict[str, Any], evidence: dict[str, Any]) -> bool:
    coverage = evidence["coverage"]
    semantics = criterion["coverage_semantics"]
    if semantics in {"all-required", "complete-negative-coverage"}:
        return coverage["state"] == "complete" and coverage["observed"] >= coverage["required"]
    if semantics == "any-sufficient":
        return coverage["observed"] > 0
    return False


def validate_completion_context(
    value: dict[str, Any],
    *,
    profile: dict[str, Any],
    proof_recipe: dict[str, Any],
    evidence_documents: list[dict[str, Any]],
    current_job_id: str,
    current_generation: int,
    current_lineage_id: str,
    current_subject: dict[str, Any],
    current_candidate: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> list[str]:
    findings = validate_document("completion", value)
    if findings:
        return findings
    profile_findings = validate_document("profile", profile)
    proof_findings = validate_document("proof", proof_recipe)
    if profile_findings:
        findings.extend(f"profile: {item}" for item in profile_findings)
    if proof_findings:
        findings.extend(f"proof: {item}" for item in proof_findings)
    if findings:
        return findings
    if value["lineageId"] != current_lineage_id:
        findings.append("completion: stale lineage cannot authorize publication")
    if value["jobId"] != current_job_id or value["generation"] != current_generation:
        findings.append("completion: stale job/generation cannot authorize publication")
    if value["subject"] != current_subject:
        findings.append("completion: stale subject identity cannot authorize publication")
    if value.get("candidate") is not None and current_candidate is None:
        findings.append("completion: candidate-bound publication requires current candidate context")
    elif current_candidate is not None and value.get("candidate") != current_candidate:
        findings.append("completion: stale candidate identity cannot authorize publication")

    criteria = _proof_criteria(proof_recipe)
    recipe_id = f"{proof_recipe.get('recipe_id')}@{proof_recipe.get('revision')}"
    requirements = {str(item["id"]): item for item in profile["completion"]["obligations"]}
    completion_obligations = {str(item["id"]): item for item in value["obligations"]}
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for evidence_document in evidence_documents:
        evidence_findings = validate_document("evidence", evidence_document)
        if evidence_findings:
            findings.extend(
                f"evidence {evidence_document.get('evidenceId', '<unknown>')}: {item}" for item in evidence_findings
            )
        else:
            evidence_by_id[str(evidence_document["evidenceId"])] = evidence_document

    selected_now = (now or datetime.now(UTC)).astimezone(UTC)
    resolved_required = True
    for obligation_id, requirement in requirements.items():
        if not requirement["required"]:
            continue
        completion_obligation = completion_obligations.get(obligation_id)
        if completion_obligation is None:
            findings.append(f"completion: required obligation {obligation_id} is absent")
            resolved_required = False
            continue
        if completion_obligation["state"] != "satisfied":
            resolved_required = False
            continue
        criterion = criteria.get(obligation_id)
        if criterion is None:
            findings.append(f"completion: proof recipe has no criterion for {obligation_id}")
            resolved_required = False
            continue
        valid_evidence = False
        for evidence_ref in completion_obligation["evidenceRefs"]:
            selected_evidence = evidence_by_id.get(str(evidence_ref))
            if selected_evidence is None:
                findings.append(f"completion: obligation {obligation_id} references missing evidence {evidence_ref}")
                continue
            reasons: list[str] = []
            if selected_evidence["jobId"] != current_job_id or selected_evidence["generation"] != current_generation:
                reasons.append("stale job/generation")
            if selected_evidence["lineageId"] != value["lineageId"] or selected_evidence["subject"] != current_subject:
                reasons.append("subject/lineage mismatch")
            if criterion["candidate_binding_required"] and selected_evidence.get("candidate") != current_candidate:
                reasons.append("candidate mismatch")
            if (
                selected_evidence["criterionId"] != obligation_id
                or selected_evidence["claimId"] != criterion["canonical_claim"]
            ):
                reasons.append("criterion/claim mismatch")
            if selected_evidence["evidenceClass"] != requirement["evidence_class"]:
                reasons.append("evidence class mismatch")
            if selected_evidence["proofRecipeId"] != recipe_id:
                reasons.append("proof recipe mismatch")
            approved = set(criterion["approved_producers"])
            producer_by_id = {str(item["producer_id"]): item for item in proof_recipe["producers"]}
            selected_producer = producer_by_id.get(str(selected_evidence["producerId"]))
            if approved and selected_evidence["producerId"] not in approved:
                reasons.append("producer not approved")
            if selected_producer is None:
                reasons.append("producer contract missing")
            elif (
                _AUTHORITY_RANK.get(selected_evidence["authorityClass"], -1)
                > _AUTHORITY_RANK[selected_producer["authority_ceiling"]]
            ):
                reasons.append("authority exceeds producer ceiling")
            if (
                _AUTHORITY_RANK.get(selected_evidence["authorityClass"], -1)
                < _AUTHORITY_RANK[criterion["required_authority"]]
            ):
                reasons.append("insufficient authority")
            if selected_evidence["binding"]["status"] != "complete":
                reasons.append("incomplete claim binding")
            elif not set(criterion["binding_requirements"]) <= set(selected_evidence["binding"]["satisfied"]):
                reasons.append("incomplete claim binding")
            if not _coverage_satisfies(criterion, selected_evidence):
                reasons.append("insufficient coverage")
            observed = _parse_timestamp(str(selected_evidence["observedAt"]))
            if observed > selected_now:
                reasons.append("observation is from the future")
            elif (selected_now - observed).total_seconds() > int(criterion["freshness_seconds"]):
                reasons.append("evidence is stale")
            expires = selected_evidence.get("expiresAt")
            if expires is not None and _parse_timestamp(str(expires)) < selected_now:
                reasons.append("evidence is expired")
            if reasons:
                findings.append(f"completion: evidence {evidence_ref} for {obligation_id}: " + ", ".join(reasons))
            else:
                valid_evidence = True
        if not valid_evidence:
            resolved_required = False
    if value["disposition"] == "eligible" and (
        not resolved_required or value["ambiguousOperationRefs"] or value["ambiguousCancellationRefs"]
    ):
        findings.append("completion: eligible disposition is not supported by current resolved evidence")
    return findings


def _capability_contract_digest(capability: dict[str, Any]) -> str | None:
    contract = capability.get("contract")
    if not isinstance(contract, dict):
        return None
    try:
        return compute_capability_contract_digest(capability)
    except (TypeError, ValueError):
        return None


def _target_identity(job: dict[str, Any]) -> str:
    subject = job["subject"]
    return f"{subject['type']}:{subject['id']}:{subject.get('revision') or 'none'}"


def evaluate_mutation_admission(
    *,
    effect_id: str,
    mutation_policy: dict[str, Any],
    job: dict[str, Any],
    capability: dict[str, Any],
    current_job_id: str,
    current_generation: int,
    current_attempt_id: str,
    current_version: int,
    current_subject: dict[str, Any],
    effective_authority: dict[str, Any] | None,
    remaining_budget_ms: int,
    expected_request_digest: str | None = None,
    receipt: dict[str, Any] | None = None,
    candidate: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    effects = {item["id"]: item for item in mutation_policy.get("effects", [])}
    effect = effects.get(effect_id)
    if effect is None:
        return {"disposition": "CapabilityUnavailable", "reasons": ["unknown mutation effect"]}
    reasons: list[tuple[str, str]] = []
    if job["jobId"] != current_job_id or job["generation"] != current_generation:
        reasons.append(("LostAuthority", "stale job/generation"))
    if job["attemptId"] != current_attempt_id:
        reasons.append(("LostAuthority", "stale attempt"))
    if int(job["version"]) != int(current_version):
        reasons.append(("LostAuthority", "stale optimistic version"))
    cancellation_dispatch = effect_id == "cancellation-dispatch"
    cancellation_fenced = job["cancellation"] in {"requested", "fenced", "reconciling"}
    if job["status"] in _TERMINAL or (not cancellation_dispatch and cancellation_fenced):
        reasons.append(("LostAuthority", "job is terminal or cancellation-fenced"))
    if cancellation_dispatch and job["cancellation"] not in {"requested", "reconciling"}:
        reasons.append(("LostAuthority", "cancellation dispatch requires an active cancellation request"))
    if job["subject"] != current_subject:
        reasons.append(("LostAuthority", "subject identity differs from current authoritative subject"))

    target_identity = _target_identity(job)
    authority = effective_authority or {}
    source = str(authority.get("source", ""))
    principal = str(authority.get("principal", ""))
    if source != effect["authority_source"]:
        reasons.append(("LostAuthority", "effective authority source does not match mutation policy"))
    if principal.casefold() in _PLACEHOLDER_AUTHORITY:
        reasons.append(("LostAuthority", "effective authority principal is missing/fabricated"))
    if authority.get("scope") != effect_id:
        reasons.append(("LostAuthority", "effective authority scope does not match mutation effect"))
    if authority.get("target") != target_identity:
        reasons.append(("LostAuthority", "effective authority target does not match current subject"))
    if authority.get("attemptId") != current_attempt_id or int(authority.get("jobVersion", -1)) != int(current_version):
        reasons.append(("LostAuthority", "effective authority is fenced to a stale attempt/version"))

    selected_now = (now or datetime.now(UTC)).astimezone(UTC)
    if effect["lease_required"]:
        lease = job.get("lease")
        if not isinstance(lease, dict):
            reasons.append(("LostAuthority", "required lease is missing"))
        else:
            try:
                if _parse_timestamp(str(lease["expiresAt"])) <= selected_now:
                    reasons.append(("LostAuthority", "required lease is expired"))
            except (KeyError, ValueError):
                reasons.append(("LostAuthority", "required lease expiry is invalid"))
            expected_owner = f"{effect['authority_source']}:{current_attempt_id}"
            if (
                principal != expected_owner
                or lease.get("owner") != expected_owner
                or authority.get("leaseOwner") != expected_owner
            ):
                reasons.append(("LostAuthority", "lease owner does not match admitted runtime principal"))
            if (
                lease.get("fencingToken") != current_generation
                or authority.get("leaseFencingToken") != current_generation
            ):
                reasons.append(("LostAuthority", "lease fencing token does not match current generation"))

    if effect["candidate_required"]:
        if candidate is None or not candidate.get("digest"):
            reasons.append(("StaleCandidate", "exact candidate is required"))
        elif job.get("candidate") != candidate:
            reasons.append(("StaleCandidate", "candidate differs from admitted job candidate"))

    expected_contract_digest = _capability_contract_digest(capability)
    raw_contract = capability.get("contract")
    contract: dict[str, Any] = raw_contract if isinstance(raw_contract, dict) else {}
    reviewed_contract = effect["capability_contract"]
    if capability.get("capability_id") != effect["capability_ref"]:
        reasons.append(("CapabilityUnavailable", "capability identity does not match mutation policy"))
    if contract.get("id") != capability.get("capability_id") or expected_contract_digest != contract.get("digest"):
        reasons.append(("CapabilityUnavailable", "capability contract provenance/digest is invalid"))
    if contract != reviewed_contract:
        reasons.append(("CapabilityUnavailable", "capability does not match the exact reviewed mutation contract"))

    required_budget_ms = int(effect["minimum_budget_ms"]) + int(effect["finalization_reserve_ms"])
    if remaining_budget_ms < required_budget_ms:
        reasons.append(
            ("BudgetUnavailable", "remaining budget cannot cover operation plus deterministic finalization reserve")
        )
    if effect["durable_operation_required"]:
        if receipt is None:
            reasons.append(("ReconciliationRequired", "durable operation receipt is missing"))
        else:
            if (
                receipt.get("jobId") != current_job_id
                or receipt.get("lineageId") != job["lineageId"]
                or receipt.get("generation") != current_generation
                or receipt.get("attemptId") != current_attempt_id
                or int(receipt.get("jobVersion", -1)) != int(current_version)
            ):
                reasons.append(
                    ("LostAuthority", "operation receipt belongs to stale job/lineage/generation/attempt/version")
                )
            if receipt.get("operationKind") != effect["operation_kind"]:
                reasons.append(("LostAuthority", "operation receipt kind differs from mutation effect"))
            if expected_request_digest is None or receipt.get("requestDigest") != expected_request_digest:
                reasons.append(
                    ("LostAuthority", "operation receipt request digest differs from exact admitted mutation")
                )
            if receipt.get("targetIdentity") != target_identity:
                reasons.append(("LostAuthority", "operation receipt target differs from current subject"))
            if receipt.get("capabilityIdentity") != capability.get("capability_id") or receipt.get(
                "capabilityContractDigest"
            ) != contract.get("digest"):
                reasons.append(
                    ("CapabilityUnavailable", "operation receipt is not bound to current reviewed capability contract")
                )
            if candidate is not None and receipt.get("candidateDigest") != candidate.get("digest"):
                reasons.append(("StaleCandidate", "operation receipt candidate digest is stale"))
            if receipt.get("delivery") == "delivery-unknown":
                reasons.append(("ReconciliationRequired", "operation delivery is ambiguous"))
            elif receipt.get("state") != "reserved" or receipt.get("delivery") != "not-delivered":
                reasons.append(("ReconciliationRequired", "operation is not in pre-dispatch reserved state"))
    if reasons:
        return {"disposition": reasons[0][0], "reasons": [item[1] for item in reasons]}
    return {"disposition": "Admitted", "reasons": []}


def validate_design_pack(
    *,
    profile: dict[str, Any],
    state_machine: dict[str, Any],
    mutation_policy: dict[str, Any],
    proof_recipe: dict[str, Any],
    acceptance: dict[str, Any],
    upstreams: list[dict[str, Any]],
) -> list[str]:
    findings: list[str] = []
    for kind, value in (
        ("profile", profile),
        ("state-machine", state_machine),
        ("mutation-policy", mutation_policy),
        ("proof", proof_recipe),
        ("acceptance", acceptance),
    ):
        findings.extend(f"{kind}: {item}" for item in validate_document(kind, value))
    for index, upstream in enumerate(upstreams):
        findings.extend(f"upstream[{index}]: {item}" for item in validate_document("upstream", upstream))
    if findings:
        # Preserve cross-contract diagnostics even when an internally valid-looking
        # mutation effect also violates its own exact capability binding. This keeps
        # the caller from having to repair errors serially to discover deterministic
        # admission preconditions.
        upstream_ids = [str(item.get("capability_id", "")) for item in upstreams if isinstance(item, dict)]
        effects = mutation_policy.get("effects", []) if isinstance(mutation_policy, dict) else []
        if isinstance(effects, list):
            for effect in effects:
                if not isinstance(effect, dict) or not effect.get("durable_operation_required"):
                    continue
                ref = str(effect.get("capability_ref", ""))
                if upstream_ids.count(ref) != 1:
                    findings.append(
                        f"design-pack: mutation effect {effect.get('id', '<unknown>')} capability_ref must resolve to exactly one reviewed upstream contract"
                    )
        return findings

    expected_refs = {
        "state_machine": f"{state_machine['machine_id']}@{state_machine['revision']}",
        "mutation_policy": f"{mutation_policy['policy_id']}@{mutation_policy['revision']}",
        "proof_recipe": f"{proof_recipe['recipe_id']}@{proof_recipe['revision']}",
        "acceptance": f"{acceptance['acceptance_id']}@{acceptance['revision']}",
    }
    for key, expected in expected_refs.items():
        if profile["contracts"].get(key) != expected:
            findings.append(f"design-pack: profile contract {key} must reference {expected}")

    transition_ids = {item["id"] for item in state_machine["transitions"]}
    upstream_by_id: dict[str, list[dict[str, Any]]] = {}
    for upstream in upstreams:
        upstream_by_id.setdefault(str(upstream["capability_id"]), []).append(upstream)
    for capability_id, matches in upstream_by_id.items():
        if len(matches) != 1:
            findings.append(
                f"design-pack: capability {capability_id} must resolve to exactly one reviewed upstream contract"
            )
    for effect in mutation_policy["effects"]:
        if effect["transition"] not in transition_ids and effect["transition"] not in {"cancel-start"}:
            findings.append(
                f"design-pack: mutation effect {effect['id']} references unknown transition {effect['transition']}"
            )
        if effect["durable_operation_required"] and len(upstream_by_id.get(str(effect["capability_ref"]), [])) != 1:
            findings.append(
                f"design-pack: mutation effect {effect['id']} capability_ref must resolve to exactly one reviewed upstream contract"
            )
        if effect["durable_operation_required"]:
            matches = upstream_by_id.get(str(effect["capability_ref"]), [])
            if len(matches) == 1 and effect["capability_contract"] != matches[0]["contract"]:
                findings.append(
                    f"design-pack: mutation effect {effect['id']} capability contract must equal the reviewed upstream source/id/revision/digest"
                )

    criteria = {item["criterion_id"] for item in proof_recipe["criteria"]}
    for obligation in profile["completion"]["obligations"]:
        if obligation["id"] not in criteria:
            findings.append(f"design-pack: completion obligation {obligation['id']} has no proof criterion")
    features = profile["features"]
    if features["durable_external_async"] and not any(item["delivery"] == "durable-async" for item in upstreams):
        findings.append("design-pack: durable_external_async has no durable-async upstream contract")
    if features["external_cancellation"] and not any(item["cancellation"]["mode"] != "none" for item in upstreams):
        findings.append("design-pack: external_cancellation has no cancellable upstream contract")
    if features["exact_candidate_binding"]:
        if not any(item["candidate_required"] for item in mutation_policy["effects"]):
            findings.append("design-pack: exact_candidate_binding has no candidate-required mutation")
        if not any(item["candidate_binding_required"] for item in proof_recipe["criteria"]):
            findings.append("design-pack: exact_candidate_binding has no candidate-bound proof criterion")
    return findings


def validate_path(kind: str, path: Path) -> list[str]:
    return validate_document(kind, _load(path))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=sorted(_SCHEMA_FILES))
    parser.add_argument("path", type=Path)
    parser.add_argument("--current-job-id")
    parser.add_argument("--current-generation", type=int)
    parser.add_argument("--current-lineage-id")
    parser.add_argument("--current-subject", type=Path)
    parser.add_argument("--current-candidate", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--proof-recipe", type=Path)
    parser.add_argument("--evidence", type=Path, action="append", default=[])
    parser.add_argument("--now")
    return parser


def _context_complete(args: argparse.Namespace) -> bool:
    return (
        args.current_job_id is not None
        and args.current_generation is not None
        and args.current_lineage_id is not None
        and args.current_subject is not None
    )


def main() -> int:
    args = build_parser().parse_args()
    value = _load(args.path)
    if not isinstance(value, dict):
        findings = validate_document(args.kind, value)
    elif args.kind == "handoff" and value.get("actionable") is True:
        if not _context_complete(args):
            findings = validate_document("handoff", value)
            findings.append(
                "handoff: actionable validation requires current job, lineage, generation, and subject context"
            )
        else:
            subject = _load(args.current_subject)
            candidate = _load(args.current_candidate) if args.current_candidate else None
            findings = validate_handoff_current(
                value,
                current_job_id=str(args.current_job_id),
                current_generation=int(args.current_generation),
                current_lineage_id=str(args.current_lineage_id),
                current_subject=subject,
                current_candidate=candidate,
            )
    elif args.kind == "completion" and value.get("disposition") == "eligible":
        missing = not _context_complete(args) or args.profile is None or args.proof_recipe is None
        if missing:
            findings = validate_document("completion", value)
            findings.append(
                "completion: eligible validation requires current lineage, profile, proof recipe, and evidence context"
            )
        else:
            subject = _load(args.current_subject)
            candidate = _load(args.current_candidate) if args.current_candidate else None
            profile = _load(args.profile)
            proof = _load(args.proof_recipe)
            evidence_documents = [_load(path) for path in args.evidence]
            selected_now = _parse_timestamp(args.now) if args.now else None
            findings = validate_completion_context(
                value,
                profile=profile,
                proof_recipe=proof,
                evidence_documents=evidence_documents,
                current_job_id=str(args.current_job_id),
                current_generation=int(args.current_generation),
                current_lineage_id=str(args.current_lineage_id),
                current_subject=subject,
                current_candidate=candidate,
                now=selected_now,
            )
    else:
        findings = validate_document(args.kind, value)
    for finding in findings:
        print(finding)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
