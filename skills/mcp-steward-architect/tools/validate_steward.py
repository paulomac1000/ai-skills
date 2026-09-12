#!/usr/bin/env python3
"""Validate MCP Steward contracts and publication/completion context."""

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
_TIMESTAMP_FIELDS = {
    "job": (
        "createdAt",
        "updatedAt",
        "heartbeatAt",
        "progressAt",
        "deadlineAt",
        "finalizationStartsAt",
    ),
    "receipt": ("createdAt", "observedAt", "nextRetryAt", "nextReconcileAt"),
    "evidence": ("observedAt", "expiresAt"),
    "handoff": ("sealedAt",),
    "lineage": ("updatedAt",),
    "completion": ("evaluatedAt",),
}


def _load(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if path.suffix.casefold() == ".json":
        return json.loads(text)
    return yaml.safe_load(text)


def _schema(kind: str) -> dict[str, Any]:
    value = json.loads((CONTRACTS / _SCHEMA_FILES[kind]).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(value)
    return value


def _schema_findings(kind: str, value: Any) -> list[str]:
    errors = sorted(
        Draft202012Validator(
            _schema(kind),
            format_checker=FormatChecker(),
        ).iter_errors(value),
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
    return findings


def compute_handoff_digest(value: dict[str, Any]) -> str:
    unsigned = {key: item for key, item in value.items() if key != "digest"}
    canonical = json.dumps(
        unsigned,
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
    required = set(value["subject_identity"]["required_dimensions"])
    freshness = set(value["subject_identity"]["freshness_dimensions"])
    unknown = sorted(freshness - required)
    if unknown:
        findings.append(
            "subject_identity: freshness dimensions must also be required dimensions: " + ", ".join(unknown)
        )
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
    if value["status"] == "superseded" and value.get("domainOutcome") not in {
        None,
        "superseded",
    }:
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
    if value.get("digest") != expected:
        return [f"handoff: digest mismatch; expected {expected}"]
    return []


def _upstream_findings(value: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    if value["interaction"] == "stateful":
        recoverable = value["recovery"] in {
            "replay-safe",
            "status-by-handle",
            "resume-by-handle",
        }
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
    if value["currentJobId"] in value["supersededJobIds"]:
        return ["lineage: current job cannot also be superseded"]
    return []


def _completion_findings(value: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    obligations = value["obligations"]
    obligation_ids = [item["id"] for item in obligations]
    duplicates = sorted(item for item in set(obligation_ids) if obligation_ids.count(item) > 1)
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
    unresolved = any(item["state"] == "unsatisfied" for item in obligations)
    if value["disposition"] == "eligible" and unresolved:
        findings.append("completion: eligible disposition has unsatisfied obligations")
    if value["disposition"] == "eligible" and value["ambiguousOperationRefs"]:
        findings.append("completion: eligible disposition has ambiguous operations")
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
    if kind == "profile":
        findings.extend(_profile_findings(value))
    elif kind == "job":
        findings.extend(_job_findings(value))
    elif kind == "receipt":
        findings.extend(_receipt_findings(value))
    elif kind == "handoff":
        findings.extend(_handoff_semantic_findings(value))
        findings.extend(_handoff_digest_findings(value))
    elif kind == "upstream":
        findings.extend(_upstream_findings(value))
    elif kind == "lineage":
        findings.extend(_lineage_findings(value))
    elif kind == "completion":
        findings.extend(_completion_findings(value))
    return findings


def validate_handoff_current(
    value: dict[str, Any],
    *,
    current_job_id: str,
    current_generation: int,
    current_subject: dict[str, Any],
) -> list[str]:
    findings = _schema_findings("handoff", value)
    findings.extend(_timestamp_findings("handoff", value))
    if findings:
        return findings
    findings.extend(_handoff_semantic_findings(value))
    if findings:
        return findings
    if value["actionable"] and (value["jobId"] != current_job_id or value["generation"] != current_generation):
        return ["handoff: stale job/generation cannot be actionable"]
    if value["actionable"] and value["subject"] != current_subject:
        return ["handoff: stale subject identity cannot be actionable"]
    if value["status"] == "superseded" and value["actionable"]:
        return ["handoff: superseded handoff cannot be actionable"]
    return _handoff_digest_findings(value)


def _proof_criteria(proof_recipe: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item["criterion_id"]): item
        for item in proof_recipe.get("criteria", [])
        if isinstance(item, dict) and item.get("criterion_id")
    }


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
    if findings:
        return findings
    profile_findings = validate_document("profile", profile)
    if profile_findings:
        return [f"profile: {finding}" for finding in profile_findings]
    if value["jobId"] != current_job_id or value["generation"] != current_generation:
        findings.append("completion: stale job/generation cannot authorize publication")
    if value["subject"] != current_subject:
        findings.append("completion: stale subject identity cannot authorize publication")

    criteria = _proof_criteria(proof_recipe)
    recipe_id = f"{proof_recipe.get('recipe_id')}@{proof_recipe.get('revision')}"
    requirements = {str(item["id"]): item for item in profile["completion"]["obligations"] if isinstance(item, dict)}
    completion_obligations = {str(item["id"]): item for item in value["obligations"] if isinstance(item, dict)}
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
            resolved_evidence = evidence_by_id.get(str(evidence_ref))
            if resolved_evidence is None:
                findings.append(f"completion: obligation {obligation_id} references missing evidence {evidence_ref}")
                continue
            reasons: list[str] = []
            if resolved_evidence["jobId"] != current_job_id or resolved_evidence["generation"] != current_generation:
                reasons.append("stale job/generation")
            if resolved_evidence["lineageId"] != value["lineageId"] or resolved_evidence["subject"] != current_subject:
                reasons.append("subject/lineage mismatch")
            if resolved_evidence["criterionId"] != obligation_id:
                reasons.append("criterion mismatch")
            if resolved_evidence["evidenceClass"] != requirement["evidence_class"]:
                reasons.append("evidence class mismatch")
            if resolved_evidence["proofRecipeId"] != recipe_id:
                reasons.append("proof recipe mismatch")
            approved = set(criterion.get("approved_producers", []))
            if approved and resolved_evidence["producerId"] not in approved:
                reasons.append("producer not approved")
            required_rank = _AUTHORITY_RANK.get(str(criterion["required_authority"]), 99)
            if _AUTHORITY_RANK.get(str(resolved_evidence["authorityClass"]), -1) < required_rank:
                reasons.append("insufficient authority")
            observed = _parse_timestamp(str(resolved_evidence["observedAt"]))
            if observed > selected_now:
                reasons.append("observation is from the future")
            elif (selected_now - observed).total_seconds() > int(criterion["freshness_seconds"]):
                reasons.append("evidence is stale")
            expires = resolved_evidence.get("expiresAt")
            if expires is not None and _parse_timestamp(str(expires)) < selected_now:
                reasons.append("evidence is expired")
            if reasons:
                findings.append(f"completion: evidence {evidence_ref} for {obligation_id}: " + ", ".join(reasons))
            else:
                valid_evidence = True
        if not valid_evidence:
            resolved_required = False

    if value["disposition"] == "eligible" and (not resolved_required or bool(value["ambiguousOperationRefs"])):
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
    parser.add_argument("--now")
    return parser


def _context_complete(args: argparse.Namespace) -> bool:
    return args.current_job_id is not None and args.current_generation is not None and args.current_subject is not None


def main() -> int:
    args = build_parser().parse_args()
    value = _load(args.path)
    if not isinstance(value, dict):
        findings = validate_document(args.kind, value)
    elif args.kind == "handoff" and value.get("actionable") is True:
        if not _context_complete(args):
            findings = validate_document("handoff", value)
            findings.append("handoff: actionable validation requires current job, generation, and subject context")
        else:
            current_subject = _load(args.current_subject)
            if not isinstance(current_subject, dict):
                findings = ["handoff: current subject must be an object"]
            else:
                findings = validate_handoff_current(
                    value,
                    current_job_id=str(args.current_job_id),
                    current_generation=int(args.current_generation),
                    current_subject=current_subject,
                )
    elif args.kind == "completion" and value.get("disposition") == "eligible":
        missing = not _context_complete(args) or args.profile is None or args.proof_recipe is None
        if missing:
            findings = validate_document("completion", value)
            findings.append(
                "completion: eligible validation requires current lineage, profile, proof recipe, and evidence context"
            )
        else:
            current_subject = _load(args.current_subject)
            profile = _load(args.profile)
            proof_recipe = _load(args.proof_recipe)
            evidence_documents = [_load(path) for path in args.evidence]
            if not all(
                isinstance(item, dict)
                for item in [
                    current_subject,
                    profile,
                    proof_recipe,
                    *evidence_documents,
                ]
            ):
                findings = ["completion: contextual documents must be objects"]
            else:
                selected_now = _parse_timestamp(args.now) if args.now else None
                findings = validate_completion_context(
                    value,
                    profile=profile,
                    proof_recipe=proof_recipe,
                    evidence_documents=evidence_documents,
                    current_job_id=str(args.current_job_id),
                    current_generation=int(args.current_generation),
                    current_subject=current_subject,
                    now=selected_now,
                )
    else:
        findings = validate_document(args.kind, value)
    for finding in findings:
        print(finding)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
