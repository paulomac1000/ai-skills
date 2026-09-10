"""Deterministic transition rules for bounded diagnostic reasoning state."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from copy import deepcopy
from typing import Literal, cast

ProbeVerdict = Literal["supports", "contradicts", "inconclusive"]
RemediationStatus = Literal["verified", "failed", "partial", "unknown"]


class DiagnosticReasoningError(ValueError):
    """Raised when a diagnostic transition would violate evidence discipline."""


def _clone_state(state: Mapping[str, object]) -> dict[str, object]:
    return cast(dict[str, object], deepcopy(dict(state)))


def _mapping_list(value: object, label: str) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise DiagnosticReasoningError(f"{label} must be an array")
    result: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            raise DiagnosticReasoningError(f"{label} entries must be objects")
        result.append(cast(dict[str, object], item))
    return result


def _hypothesis(state: dict[str, object], hypothesis_id: str) -> dict[str, object]:
    for item in _mapping_list(state.get("hypotheses"), "hypotheses"):
        if item.get("id") == hypothesis_id:
            return item
    raise DiagnosticReasoningError(f"unknown hypothesis: {hypothesis_id}")


def _evidence_values(hypothesis: Mapping[str, object]) -> set[str]:
    values: set[str] = set()
    for field in ("supporting_evidence", "contradicting_evidence"):
        raw = hypothesis.get(field)
        if isinstance(raw, list):
            values.update(item for item in raw if isinstance(item, str))
    return values


def _append_evidence(hypothesis: dict[str, object], field: str, evidence_ref: str) -> None:
    other = "contradicting_evidence" if field == "supporting_evidence" else "supporting_evidence"
    other_values = hypothesis.get(other)
    if isinstance(other_values, list) and evidence_ref in other_values:
        raise DiagnosticReasoningError(
            f"evidence {evidence_ref} cannot support and contradict the same hypothesis revision"
        )
    values = hypothesis.get(field)
    if not isinstance(values, list):
        raise DiagnosticReasoningError(f"{field} must be an array")
    if evidence_ref not in values:
        values.append(evidence_ref)


def record_probe_result(
    state: Mapping[str, object],
    hypothesis_id: str,
    evidence_ref: str,
    verdict: ProbeVerdict,
    *,
    next_discriminating_probe: str | None = None,
) -> dict[str, object]:
    """Apply one evidence-bearing discriminating probe result.

    Args:
        state: Current diagnostic state.
        hypothesis_id: Hypothesis evaluated by the probe.
        evidence_ref: Durable reference to the new probe evidence.
        verdict: Whether the evidence supports, contradicts, or is inconclusive.
        next_discriminating_probe: Optional next probe selected after this result.

    Returns:
        A deep-copied state with the deterministic hypothesis transition applied.

    Raises:
        DiagnosticReasoningError: If evidence is malformed or would silently
            resurrect a disproven hypothesis.
    """
    if not evidence_ref:
        raise DiagnosticReasoningError("evidence_ref must be non-empty")
    updated = _clone_state(state)
    hypothesis = _hypothesis(updated, hypothesis_id)
    status = hypothesis.get("status")

    if verdict == "supports":
        if status == "disproven":
            raise DiagnosticReasoningError(
                "disproven hypothesis requires explicit reopen_hypothesis with new evidence"
            )
        _append_evidence(hypothesis, "supporting_evidence", evidence_ref)
        hypothesis["status"] = "supported"
    elif verdict == "contradicts":
        _append_evidence(hypothesis, "contradicting_evidence", evidence_ref)
        hypothesis["status"] = "disproven"
    elif verdict == "inconclusive":
        if status not in {"supported", "disproven"}:
            hypothesis["status"] = "unknown"
    else:
        raise DiagnosticReasoningError(f"unsupported probe verdict: {verdict}")

    if next_discriminating_probe is not None:
        hypothesis["next_discriminating_probe"] = next_discriminating_probe
    return updated


def reopen_hypothesis(
    state: Mapping[str, object],
    hypothesis_id: str,
    evidence_ref: str,
    *,
    next_discriminating_probe: str,
) -> dict[str, object]:
    """Explicitly reopen a disproven hypothesis using genuinely new evidence.

    Args:
        state: Current diagnostic state.
        hypothesis_id: Previously disproven hypothesis to reconsider.
        evidence_ref: New evidence that contradicts the prior disproof.
        next_discriminating_probe: Probe required before stronger causal claims.

    Returns:
        A new state with an incremented revision and explicit reopen record.

    Raises:
        DiagnosticReasoningError: If the hypothesis is not disproven or the
            evidence was already present in its prior revision.
    """
    if not evidence_ref or not next_discriminating_probe:
        raise DiagnosticReasoningError("reopen requires evidence and a discriminating probe")
    updated = _clone_state(state)
    hypothesis = _hypothesis(updated, hypothesis_id)
    if hypothesis.get("status") != "disproven":
        raise DiagnosticReasoningError("only a disproven hypothesis may be reopened")
    if evidence_ref in _evidence_values(hypothesis):
        raise DiagnosticReasoningError("reopen evidence must be new")

    raw_revision = hypothesis.get("revision", 1)
    if not isinstance(raw_revision, int) or isinstance(raw_revision, bool) or raw_revision < 1:
        raise DiagnosticReasoningError("hypothesis revision must be a positive integer")
    hypothesis["revision"] = raw_revision + 1
    hypothesis["reopen"] = {"from_revision": raw_revision, "evidence_ref": evidence_ref}
    _append_evidence(hypothesis, "supporting_evidence", evidence_ref)
    hypothesis["status"] = "active"
    hypothesis["next_discriminating_probe"] = next_discriminating_probe
    return updated


def record_remediation_result(
    state: Mapping[str, object],
    hypothesis_id: str,
    evidence_ref: str,
    *,
    predicted_postcondition: str,
    status: RemediationStatus,
    observed_postcondition: str | None = None,
) -> dict[str, object]:
    """Record whether a remediation produced its predicted observable effect.

    Args:
        state: Current diagnostic state.
        hypothesis_id: Hypothesis whose proposed fix was exercised.
        evidence_ref: Durable evidence for the observed postcondition.
        predicted_postcondition: Observable change expected if the hypothesis is causal.
        status: Verification result for that predicted postcondition.
        observed_postcondition: Optional bounded description of what was observed.

    Returns:
        A new state containing the remediation attempt and updated hypothesis.

    Raises:
        DiagnosticReasoningError: If a verified repair would silently resurrect
            an already disproven hypothesis or required evidence is missing.
    """
    if not evidence_ref or not predicted_postcondition:
        raise DiagnosticReasoningError("remediation result requires evidence and predicted postcondition")
    updated = _clone_state(state)
    hypothesis = _hypothesis(updated, hypothesis_id)
    attempts_raw = updated.setdefault("remediation_attempts", [])
    if not isinstance(attempts_raw, list):
        raise DiagnosticReasoningError("remediation_attempts must be an array")
    attempts_raw.append(
        {
            "hypothesis_id": hypothesis_id,
            "evidence_ref": evidence_ref,
            "predicted_postcondition": predicted_postcondition,
            "observed_postcondition": observed_postcondition,
            "status": status,
        }
    )

    if status == "failed":
        _append_evidence(hypothesis, "contradicting_evidence", evidence_ref)
        hypothesis["status"] = "disproven"
    elif status == "verified":
        if hypothesis.get("status") == "disproven":
            raise DiagnosticReasoningError(
                "verified remediation cannot silently resurrect a disproven hypothesis"
            )
        _append_evidence(hypothesis, "supporting_evidence", evidence_ref)
        hypothesis["status"] = "supported"
    elif status in {"partial", "unknown"} and hypothesis.get("status") not in {"disproven"}:
        hypothesis["status"] = "unknown"
    return updated


def select_discriminating_probe(state: Mapping[str, object]) -> str | None:
    """Select a deterministic probe that discriminates unresolved hypotheses.

    Args:
        state: Diagnostic state containing candidate hypotheses.

    Returns:
        The most shared unresolved next-probe request, with lexical tie-breaking,
        or ``None`` when no unresolved hypothesis declares a next probe.
    """
    probes: list[str] = []
    for hypothesis in _mapping_list(state.get("hypotheses"), "hypotheses"):
        if hypothesis.get("status") == "disproven":
            continue
        probe = hypothesis.get("next_discriminating_probe")
        if isinstance(probe, str) and probe:
            probes.append(probe)
    if not probes:
        return None
    counts = Counter(probes)
    return min(counts, key=lambda probe: (-counts[probe], probe))


def validate_diagnostic_state(state: Mapping[str, object]) -> list[str]:
    """Validate cross-record causal and effective-runtime provenance semantics.

    Args:
        state: Structurally valid diagnostic-state document.

    Returns:
        Semantic findings. An empty list means causal references, disproven-state
        discipline, and effective-config provenance are internally consistent.
    """
    findings: list[str] = []
    try:
        hypotheses = _mapping_list(state.get("hypotheses"), "hypotheses")
        observations = _mapping_list(state.get("observations"), "observations")
    except DiagnosticReasoningError as error:
        return [str(error)]

    hypothesis_by_id: dict[str, Mapping[str, object]] = {}
    for hypothesis in hypotheses:
        hypothesis_id = hypothesis.get("id")
        if not isinstance(hypothesis_id, str) or not hypothesis_id:
            findings.append("hypothesis id is required")
            continue
        if hypothesis_id in hypothesis_by_id:
            findings.append(f"DUPLICATE_HYPOTHESIS_ID: {hypothesis_id}")
        hypothesis_by_id[hypothesis_id] = hypothesis

    observation_ids: set[str] = set()
    for observation in observations:
        observation_id = observation.get("id")
        if isinstance(observation_id, str):
            if observation_id in observation_ids:
                findings.append(f"DUPLICATE_OBSERVATION_ID: {observation_id}")
            observation_ids.add(observation_id)

    causal = state.get("causal_assessment")
    if not isinstance(causal, Mapping):
        return findings + ["causal_assessment must be an object"]
    try:
        causes = _mapping_list(causal.get("causes"), "causal_assessment.causes")
    except DiagnosticReasoningError as error:
        return findings + [str(error)]

    primary_count = sum(1 for cause in causes if cause.get("role") == "primary")
    if primary_count > 1:
        findings.append("MULTIPLE_PRIMARY_CAUSES: causal assessment may contain at most one primary")

    config_entries = state.get("effective_config_provenance", [])
    config_status: dict[str, str] = {}
    if isinstance(config_entries, list):
        for entry in config_entries:
            if isinstance(entry, Mapping):
                source = entry.get("source")
                status = entry.get("status")
                if isinstance(source, str) and isinstance(status, str):
                    config_status[source] = status

    for cause in causes:
        hypothesis_id = cause.get("hypothesis_id")
        if not isinstance(hypothesis_id, str) or hypothesis_id not in hypothesis_by_id:
            findings.append(f"UNKNOWN_CAUSAL_HYPOTHESIS: {hypothesis_id}")
            continue
        hypothesis = hypothesis_by_id[hypothesis_id]
        if hypothesis.get("status") == "disproven":
            findings.append(f"DISPROVEN_CAUSAL_HYPOTHESIS: {hypothesis_id}")
        source_refs = hypothesis.get("config_source_refs", [])
        if isinstance(source_refs, list):
            for source_ref in source_refs:
                if not isinstance(source_ref, str) or config_status.get(source_ref) != "runtime-proven":
                    findings.append(
                        f"CONFIG_SOURCE_NOT_RUNTIME_PROVEN: {hypothesis_id} -> {source_ref}"
                    )

    unresolved = causal.get("unresolved_alternatives")
    if causal.get("status") == "proven":
        if not causes:
            findings.append("PROVEN_WITHOUT_CAUSE: proven assessment requires causal evidence")
        if isinstance(unresolved, list) and unresolved:
            findings.append("PROVEN_WITH_UNRESOLVED_ALTERNATIVES")
        if any(cause.get("support") != "proven" for cause in causes):
            findings.append("PROVEN_WITH_NONPROVEN_CAUSE")

    return findings


def validate_diagnostic_transition(
    previous: Mapping[str, object],
    current: Mapping[str, object],
) -> list[str]:
    """Validate persistence and explicit reopening of disproven hypotheses.

    Args:
        previous: Previously accepted diagnostic state.
        current: Candidate successor state.

    Returns:
        Findings for dropped or silently resurrected disproven hypotheses.
    """
    findings = validate_diagnostic_state(current)
    try:
        previous_hypotheses = _mapping_list(previous.get("hypotheses"), "hypotheses")
        current_hypotheses = _mapping_list(current.get("hypotheses"), "hypotheses")
    except DiagnosticReasoningError as error:
        return findings + [str(error)]

    current_by_id = {
        item["id"]: item
        for item in current_hypotheses
        if isinstance(item.get("id"), str)
    }
    for old in previous_hypotheses:
        hypothesis_id = old.get("id")
        if old.get("status") != "disproven" or not isinstance(hypothesis_id, str):
            continue
        new = current_by_id.get(hypothesis_id)
        if new is None:
            findings.append(f"DISPROVEN_HYPOTHESIS_DROPPED: {hypothesis_id}")
            continue
        if new.get("status") == "disproven":
            continue

        old_revision = old.get("revision", 1)
        new_revision = new.get("revision", 1)
        reopen = new.get("reopen")
        if not isinstance(old_revision, int) or isinstance(old_revision, bool):
            findings.append(f"INVALID_PREVIOUS_REVISION: {hypothesis_id}")
            continue
        if not isinstance(new_revision, int) or isinstance(new_revision, bool) or new_revision <= old_revision:
            findings.append(f"DISPROVEN_HYPOTHESIS_SILENTLY_REOPENED: {hypothesis_id}")
            continue
        if not isinstance(reopen, Mapping):
            findings.append(f"DISPROVEN_HYPOTHESIS_MISSING_REOPEN_EVIDENCE: {hypothesis_id}")
            continue
        evidence_ref = reopen.get("evidence_ref")
        if not isinstance(evidence_ref, str) or evidence_ref in _evidence_values(old):
            findings.append(f"DISPROVEN_HYPOTHESIS_REUSED_OLD_EVIDENCE: {hypothesis_id}")

    return findings
