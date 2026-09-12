#!/usr/bin/env python3
"""Validate MCP Steward profiles, evidence, completion gates and durable records."""

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
}
_AUTHORITY_RANK = {"advisory": 0, "observed": 1, "verified": 2, "independent": 3}


def _load(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    return json.loads(text) if path.suffix.casefold() == ".json" else yaml.safe_load(text)


def _schema(kind: str) -> dict[str, Any]:
    value = json.loads((CONTRACTS / _SCHEMA_FILES[kind]).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(value)
    return value


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_handoff_digest(value: dict[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "digest"}
    return "sha256:" + hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def validate_document(kind: str, value: Any) -> list[str]:
    if kind not in _SCHEMA_FILES:
        raise ValueError(f"unknown document kind: {kind}")
    errors = sorted(
        Draft202012Validator(_schema(kind), format_checker=FormatChecker()).iter_errors(value),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    )
    findings = [
        f"schema:{'.'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
        for error in errors
    ]
    if errors or not isinstance(value, dict):
        return findings
    findings.extend(_timestamp_findings(kind, value))
    if findings:
        return findings
    handlers = {
        "profile": _profile_findings,
        "job": _job_findings,
        "receipt": _receipt_findings,
        "evidence": _evidence_findings,
        "handoff": _handoff_findings,
        "upstream": _upstream_findings,
        "lineage": _lineage_findings,
        "completion": _completion_findings,
    }
    findings.extend(handlers[kind](value))
    return findings


_TIMESTAMP_FIELDS = {
    "job": ("createdAt", "updatedAt", "heartbeatAt", "progressAt", "deadlineAt", "finalizationStartsAt"),
    "receipt": ("createdAt", "observedAt", "nextRetryAt", "nextReconcileAt"),
    "evidence": ("observedAt", "expiresAt"),
    "handoff": ("sealedAt",),
    "lineage": ("updatedAt",),
    "completion": ("evaluatedAt",),
}


def _timestamp_findings(kind: str, value: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    for field in _TIMESTAMP_FIELDS.get(kind, ()):
        timestamp = value.get(field)
        if timestamp is None:
            continue
        try:
            parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        except ValueError:
            findings.append(f"schema:{field}: value is not a valid date-time")
            continue
        if parsed.tzinfo is None:
            findings.append(f"schema:{field}: date-time must include a timezone")
    return findings


def _profile_findings(value: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    authority = value["authority"]
    overlap = sorted(set(authority["owns"]) & set(authority["never_claims"]))
    if overlap:
        findings.append("authority: owns and never_claims overlap: " + ", ".join(overlap))
    durability = value["durability"]
    if durability["profile"] != "constrained-file" and not durability["transactional_store_required"]:
        findings.append("durability: durable profiles require a transactional store")
    required = set(value["subject_identity"]["required_dimensions"])
    freshness = set(value["subject_identity"]["freshness_dimensions"])
    unknown = sorted(freshness - required)
    if unknown:
        findings.append("subject_identity: freshness dimensions must also be required dimensions: " + ", ".join(unknown))
    obligation_ids = [item["id"] for item in value["completion"]["obligations"]]
    duplicates = sorted(item for item in set(obligation_ids) if obligation_ids.count(item) > 1)
    if duplicates:
        findings.append("completion: duplicate obligation ids: " + ", ".join(duplicates))
    fallback = value["credentials"]["fallback"]
    if fallback["enabled"] and (not fallback["preserve_principal_scope"] or not fallback["preserve_target"]):
        findings.append("credentials: fallback must preserve principal/scope and target")
    return findings


def _job_findings(value: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    terminal = {"completed", "completed-with-gaps", "failed", "cancelled", "superseded"}
    if value["status"] in terminal and value.get("lease") is not None:
        findings.append("job: terminal state must not retain an active lease")
    if value["status"] == "superseded" and value.get("domainOutcome") not in {None, "superseded"}:
        findings.append("job: superseded work cannot carry an actionable domain outcome")
    return findings


def _receipt_findings(value: dict[str, Any]) -> list[str]:
    findings: list[str] = []
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
    return findings


def _evidence_findings(value: dict[str, Any]) -> list[str]:
    expires = value.get("expiresAt")
    if expires is not None and _parse_timestamp(str(expires)) < _parse_timestamp(str(value["observedAt"])):
        return ["evidence: expiresAt cannot precede observedAt"]
    return []


def _handoff_findings(value: dict[str, Any]) -> list[str]:
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
    expected = compute_handoff_digest(value)
    if value["digest"] != expected:
        findings.append(f"handoff: digest mismatch; expected {expected}")
    return findings


def _upstream_findings(value: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    if value["interaction"] == "stateful":
        recoverable = value["recovery"] in {"replay-safe", "status-by-handle", "resume-by-handle"}
        reconcilable = value["reconciliation"]["ambiguous_delivery"] != "unsupported"
        if not recoverable or not reconcilable:
            findings.append("upstream: stateful capability requires recovery and ambiguous-delivery reconciliation")
    if value["delivery"] == "durable-async":
        if value["recovery"] not in {"status-by-handle", "resume-by-handle"}:
            findings.append("upstream: durable-async capability requires status/resume by handle")
        if value["progress"] == "none":
            findings.append("upstream: durable-async capability requires progress semantics")
    return findings


def _lineage_findings(value: dict[str, Any]) -> list[str]:
    return ["lineage: current job cannot also be superseded"] if value["currentJobId"] in value["supersededJobIds"] else []


def _completion_findings(value: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    obligations = value["obligations"]
    ids = [item["id"] for item in obligations]
    duplicates = sorted(item for item in set(ids) if ids.count(item) > 1)
    if duplicates:
        findings.append("completion: duplicate obligation ids: " + ", ".join(duplicates))
    for obligation in obligations:
        location = f"completion: obligation {obligation['id']}"
        state = obligation["state"]
        if state == "satisfied" and not obligation["evidenceRefs"]:
            findings.append(f"{location} satisfied without evidence")
        if state == "not-applicable" and not obligation.get("rationale"):
            findings.append(f"{location} not-applicable without rationale")
        if state == "waived" and not obligation.get("authorityRef"):
            findings.append(f"{location} waived without authority")
    if value["disposition"] == "eligible" and any(item["state"] == "unsatisfied" for item in obligations):
        findings.append("completion: eligible disposition has unsatisfied obligations")
    if value["disposition"] == "eligible" and value["ambiguousOperationRefs"]:
        findings.append("completion: eligible disposition has ambiguous operations")
    return findings


def validate_handoff_current(
    value: dict[str, Any],
    *,
    current_job_id: str,
    current_generation: int,
    current_subject: dict[str, Any],
) -> list[str]:
    findings = validate_document("handoff", value)
    if findings:
        return findings
    if value["actionable"] and (value["jobId"] != current_job_id or value["generation"] != current_generation):
        findings.append("handoff: stale job/generation cannot be actionable")
    if value["actionable"] and value["subject"] != current_subject:
        findings.append("handoff: stale subject identity cannot be actionable")
    return findings


def validate_completion_context(
    value: dict[str, Any],
    *,
    profile: dict[str, Any],
    proof_recipe: dict[str, Any],
    evidence_documents: list[dict[str, Any]],
    current_job_id: str,
    current_generation: int,
    current_subject: dict[str, Any],
    now: datetime | None = None,
) -> list[str]:
    findings = validate_document("completion", value)
    findings.extend(f"profile: {item}" for item in validate_document("profile", profile))
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for evidence in evidence_documents:
        evidence_findings = validate_document("evidence", evidence)
        if evidence_findings:
            findings.extend(f"evidence {evidence.get('evidenceId', '<unknown>')}: {item}" for item in evidence_findings)
        else:
            evidence_by_id[str(evidence["evidenceId"])] = evidence
    if findings:
        return findings

    if value["jobId"] != current_job_id or value["generation"] != current_generation:
        findings.append("completion: stale job/generation cannot be eligible")
    if value["subject"] != current_subject:
        findings.append("completion: stale subject identity cannot be eligible")
    if value["decisionIdentity"].get("generation") not in {None, current_generation}:
        findings.append("completion: decisionIdentity generation does not match current generation")

    criteria = {str(item["criterion_id"]): item for item in proof_recipe.get("criteria", [])}
    recipe_id = f"{proof_recipe.get('recipe_id')}@{proof_recipe.get('revision')}"
    profile_obligations = {str(item["id"]): item for item in profile["completion"]["obligations"]}
    actual_obligations = {str(item["id"]): item for item in value["obligations"]}
    selected_now = (now or _parse_timestamp(str(value["evaluatedAt"]))).astimezone(UTC)

    for obligation_id, requirement in profile_obligations.items():
        actual = actual_obligations.get(obligation_id)
        if actual is None:
            if requirement["required"]:
                findings.append(f"completion: required profile obligation {obligation_id} is missing")
            continue
        if not requirement["required"] and actual["state"] != "satisfied":
            continue
        if actual["state"] != "satisfied":
            findings.append(f"completion: required obligation {obligation_id} is not satisfied")
            continue
        criterion = criteria.get(obligation_id)
        if criterion is None:
            findings.append(f"completion: obligation {obligation_id} has no proof-recipe criterion")
            continue
        valid_ref = False
        for evidence_ref in actual["evidenceRefs"]:
            evidence = evidence_by_id.get(str(evidence_ref))
            if evidence is None:
                findings.append(f"completion: obligation {obligation_id} references missing evidence {evidence_ref}")
                continue
            reasons: list[str] = []
            if evidence["jobId"] != current_job_id or evidence["generation"] != current_generation:
                reasons.append("stale job/generation")
            if evidence["lineageId"] != value["lineageId"] or evidence["subject"] != current_subject:
                reasons.append("subject/lineage mismatch")
            if evidence["criterionId"] != obligation_id:
                reasons.append("criterion mismatch")
            if evidence["evidenceClass"] != requirement["evidence_class"]:
                reasons.append("evidence class mismatch")
            if evidence["proofRecipeId"] != recipe_id:
                reasons.append("proof recipe mismatch")
            approved = set(criterion.get("approved_producers", []))
            if approved and evidence["producerId"] not in approved:
                reasons.append("producer not approved")
            required_rank = _AUTHORITY_RANK.get(str(criterion["required_authority"]), 99)
            if _AUTHORITY_RANK.get(str(evidence["authorityClass"]), -1) < required_rank:
                reasons.append("insufficient authority")
            observed = _parse_timestamp(str(evidence["observedAt"]))
            if observed > selected_now:
                reasons.append("observation is from the future")
            elif (selected_now - observed).total_seconds() > int(criterion["freshness_seconds"]):
                reasons.append("evidence is stale")
            expires = evidence.get("expiresAt")
            if expires is not None and _parse_timestamp(str(expires)) < selected_now:
                reasons.append("evidence is expired")
            if reasons:
                findings.append(
                    f"completion: evidence {evidence_ref} cannot satisfy {obligation_id}: " + ", ".join(reasons)
                )
            else:
                valid_ref = True
        if not valid_ref:
            findings.append(f"completion: obligation {obligation_id} has no valid resolved evidence")

    if value["disposition"] == "eligible" and findings:
        findings.append("completion: eligible disposition is not supported by current resolved evidence")
    return findings


def validate_path(kind: str, path: Path) -> list[str]:
    return validate_document(kind, _load(path))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=sorted(_SCHEMA_FILES))
    parser.add_argument("path", type=Path)
    parser.add_argument("--current-job-id")
    parser.add_argument("--current-generation", type=int)
    parser.add_argument("--current-subject", type=Path)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--proof-recipe", type=Path)
    parser.add_argument("--evidence", type=Path, action="append", default=[])
    parser.add_argument("--now", help="UTC/RFC3339 evaluation time for evidence freshness")
    return parser


def _require_current_context(args: argparse.Namespace) -> list[str]:
    missing = [
        name
        for name, value in (
            ("--current-job-id", args.current_job_id),
            ("--current-generation", args.current_generation),
            ("--current-subject", args.current_subject),
        )
        if value is None
    ]
    return ["context: actionable validation requires " + ", ".join(missing)] if missing else []


def main() -> int:
    args = build_parser().parse_args()
    value = _load(args.path)
    findings = validate_document(args.kind, value)
    if findings or not isinstance(value, dict):
        for finding in findings:
            print(finding)
        return 1 if findings else 0

    if args.kind == "handoff" and value.get("actionable") is True:
        findings.extend(_require_current_context(args))
        if not findings:
            findings = validate_handoff_current(
                value,
                current_job_id=args.current_job_id,
                current_generation=args.current_generation,
                current_subject=_load(args.current_subject),
            )
    elif args.kind == "completion" and value.get("disposition") == "eligible":
        findings.extend(_require_current_context(args))
        if args.profile is None:
            findings.append("context: eligible completion validation requires --profile")
        if args.proof_recipe is None:
            findings.append("context: eligible completion validation requires --proof-recipe")
        if not args.evidence:
            findings.append("context: eligible completion validation requires at least one --evidence")
        if not findings:
            selected_now = _parse_timestamp(args.now) if args.now else None
            findings = validate_completion_context(
                value,
                profile=_load(args.profile),
                proof_recipe=_load(args.proof_recipe),
                evidence_documents=[_load(path) for path in args.evidence],
                current_job_id=args.current_job_id,
                current_generation=args.current_generation,
                current_subject=_load(args.current_subject),
                now=selected_now,
            )
    for finding in findings:
        print(finding)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
