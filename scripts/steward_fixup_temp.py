#!/usr/bin/env python3
"""One-shot branch fixup for the Steward audit remediation."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "skills/mcp-steward-architect/tools/generate_steward.py"
VALIDATOR = ROOT / "skills/mcp-steward-architect/tools/validate_steward.py"
TESTS = ROOT / "tests/test_mcp_steward_architect.py"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"expected exactly one match in {path}: {old[:80]!r}")
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")


def main() -> None:
    replace_once(
        GENERATOR,
        '''        operation = self.store.operation_for_job(job_id)\n        if operation is None:\n            operation = self.store.reserve_external(job_id)\n            if self.faults.trip("after-reservation"):\n                return True\n        if operation["delivery"] == "not-delivered":\n''',
        '''        operation = self.store.operation_for_job(job_id)\n        if operation is None:\n            self.store.reserve_external(job_id)\n            self.faults.trip("after-reservation")\n            return True\n        if operation["delivery"] == "not-delivered":\n''',
    )
    replace_once(
        VALIDATOR,
        '''    for evidence in evidence_documents:\n        evidence_findings = validate_document("evidence", evidence)\n        if evidence_findings:\n            findings.extend(f"evidence {evidence.get('evidenceId', '<unknown>')}: {item}" for item in evidence_findings)\n        else:\n            evidence_by_id[str(evidence["evidenceId"])] = evidence\n''',
        '''    for evidence_document in evidence_documents:\n        evidence_findings = validate_document("evidence", evidence_document)\n        if evidence_findings:\n            findings.extend(\n                f"evidence {evidence_document.get('evidenceId', '<unknown>')}: {item}"\n                for item in evidence_findings\n            )\n        else:\n            evidence_by_id[str(evidence_document["evidenceId"])] = evidence_document\n''',
    )
    replace_once(
        VALIDATOR,
        '''            evidence = evidence_by_id.get(str(evidence_ref))\n            if evidence is None:\n                findings.append(f"completion: obligation {obligation_id} references missing evidence {evidence_ref}")\n                continue\n            reasons: list[str] = []\n            if evidence["jobId"] != current_job_id or evidence["generation"] != current_generation:\n                reasons.append("stale job/generation")\n            if evidence["lineageId"] != value["lineageId"] or evidence["subject"] != current_subject:\n                reasons.append("subject/lineage mismatch")\n            if evidence["criterionId"] != obligation_id:\n                reasons.append("criterion mismatch")\n            if evidence["evidenceClass"] != requirement["evidence_class"]:\n                reasons.append("evidence class mismatch")\n            if evidence["proofRecipeId"] != recipe_id:\n                reasons.append("proof recipe mismatch")\n            approved = set(criterion.get("approved_producers", []))\n            if approved and evidence["producerId"] not in approved:\n                reasons.append("producer not approved")\n            required_rank = _AUTHORITY_RANK.get(str(criterion["required_authority"]), 99)\n            if _AUTHORITY_RANK.get(str(evidence["authorityClass"]), -1) < required_rank:\n                reasons.append("insufficient authority")\n            observed = _parse_timestamp(str(evidence["observedAt"]))\n            if observed > selected_now:\n                reasons.append("observation is from the future")\n            elif (selected_now - observed).total_seconds() > int(criterion["freshness_seconds"]):\n                reasons.append("evidence is stale")\n            expires = evidence.get("expiresAt")\n''',
        '''            resolved_evidence = evidence_by_id.get(str(evidence_ref))\n            if resolved_evidence is None:\n                findings.append(f"completion: obligation {obligation_id} references missing evidence {evidence_ref}")\n                continue\n            reasons: list[str] = []\n            if resolved_evidence["jobId"] != current_job_id or resolved_evidence["generation"] != current_generation:\n                reasons.append("stale job/generation")\n            if (\n                resolved_evidence["lineageId"] != value["lineageId"]\n                or resolved_evidence["subject"] != current_subject\n            ):\n                reasons.append("subject/lineage mismatch")\n            if resolved_evidence["criterionId"] != obligation_id:\n                reasons.append("criterion mismatch")\n            if resolved_evidence["evidenceClass"] != requirement["evidence_class"]:\n                reasons.append("evidence class mismatch")\n            if resolved_evidence["proofRecipeId"] != recipe_id:\n                reasons.append("proof recipe mismatch")\n            approved = set(criterion.get("approved_producers", []))\n            if approved and resolved_evidence["producerId"] not in approved:\n                reasons.append("producer not approved")\n            required_rank = _AUTHORITY_RANK.get(str(criterion["required_authority"]), 99)\n            if _AUTHORITY_RANK.get(str(resolved_evidence["authorityClass"]), -1) < required_rank:\n                reasons.append("insufficient authority")\n            observed = _parse_timestamp(str(resolved_evidence["observedAt"]))\n            if observed > selected_now:\n                reasons.append("observation is from the future")\n            elif (selected_now - observed).total_seconds() > int(criterion["freshness_seconds"]):\n                reasons.append("evidence is stale")\n            expires = resolved_evidence.get("expiresAt")\n''',
    )
    replace_once(
        TESTS,
        "def test_stale_generation_handoff_cannot_be_actionable_before_digest_check() -> None:\n",
        "def test_stale_generation_handoff_cannot_be_actionable() -> None:\n",
    )


if __name__ == "__main__":
    main()
