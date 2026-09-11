"""Deterministic transition rules for bounded diagnostic reasoning state."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from itertools import combinations
from typing import Literal, cast

ProbeVerdict = Literal["supports", "contradicts", "inconclusive"]
RemediationStatus = Literal["verified", "failed", "partial", "unknown"]


class DiagnosticReasoningError(ValueError):
    """Raised when a diagnostic transition would violate evidence discipline."""


@dataclass(frozen=True, slots=True)
class EvidenceBinding:
    """Semantic provenance for one evidence reference."""

    source_group: str | None
    kind: Literal["observation", "probe"]
    discriminates_for: frozenset[str] = frozenset()


def _clone_state(state: Mapping[str, object]) -> dict[str, object]:
    return deepcopy(dict(state))


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


def _supporting_evidence_values(hypothesis: Mapping[str, object]) -> set[str]:
    raw = hypothesis.get("supporting_evidence")
    if not isinstance(raw, list):
        return set()
    return {item for item in raw if isinstance(item, str)}


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
            raise DiagnosticReasoningError("disproven hypothesis requires explicit reopen_hypothesis with new evidence")
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
            raise DiagnosticReasoningError("verified remediation cannot silently resurrect a disproven hypothesis")
        _append_evidence(hypothesis, "supporting_evidence", evidence_ref)
        hypothesis["status"] = "supported"
    elif status in {"partial", "unknown"} and hypothesis.get("status") != "disproven":
        hypothesis["status"] = "unknown"
    return updated


def _prediction_map(probe: Mapping[str, object]) -> Mapping[str, object]:
    raw = probe.get("predictions")
    return raw if isinstance(raw, Mapping) else {}


def _probe_discrimination_score(probe: Mapping[str, object], hypothesis_ids: set[str]) -> tuple[int, int]:
    predictions = _prediction_map(probe)
    covered = sorted(
        hypothesis_id for hypothesis_id in hypothesis_ids if isinstance(predictions.get(hypothesis_id), str)
    )
    separated = sum(1 for left, right in combinations(covered, 2) if predictions[left] != predictions[right])
    return separated, len(covered)


def select_discriminating_probe(state: Mapping[str, object]) -> str | None:
    """Select the planned probe with greatest prediction-separation power.

    Args:
        state: Diagnostic state containing candidate hypotheses and planned probes.

    Returns:
        Description of the highest-scoring planned discriminating probe, using
        coverage and probe ID as deterministic tie-breakers, or ``None``.
    """
    hypotheses = _mapping_list(state.get("hypotheses"), "hypotheses")
    unresolved = {
        str(item["id"]) for item in hypotheses if item.get("status") != "disproven" and isinstance(item.get("id"), str)
    }
    if len(unresolved) == 1:
        only = next(item for item in hypotheses if item.get("id") in unresolved)
        legacy = only.get("next_discriminating_probe")
        return legacy if isinstance(legacy, str) and legacy else None
    if len(unresolved) < 2:
        return None

    candidates: list[tuple[int, int, str, str]] = []
    for probe in _mapping_list(state.get("probes", []), "probes"):
        if probe.get("observed_outcome") is not None:
            continue
        probe_id = probe.get("id")
        description = probe.get("description")
        if not isinstance(probe_id, str) or not isinstance(description, str):
            continue
        separated, coverage = _probe_discrimination_score(probe, unresolved)
        if separated > 0:
            candidates.append((separated, coverage, probe_id, description))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return candidates[0][3]


def _source_group(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _evidence_registry(
    observations: list[dict[str, object]],
    probes: list[dict[str, object]],
    hypothesis_ids: set[str],
) -> tuple[dict[str, EvidenceBinding], list[str]]:
    registry: dict[str, EvidenceBinding] = {}
    findings: list[str] = []

    def add(evidence_ref: object, binding: EvidenceBinding) -> None:
        if not isinstance(evidence_ref, str) or not evidence_ref:
            return
        if evidence_ref in registry:
            findings.append(f"DUPLICATE_EVIDENCE_REF: {evidence_ref}")
        else:
            registry[evidence_ref] = binding

    for observation in observations:
        add(
            observation.get("evidence_ref"),
            EvidenceBinding(_source_group(observation.get("source_group")), "observation"),
        )

    for probe in probes:
        evidence_ref = probe.get("evidence_ref")
        observed = probe.get("observed_outcome")
        if evidence_ref is None and observed is None:
            continue
        if not isinstance(evidence_ref, str) or not isinstance(observed, str):
            findings.append(f"INCOMPLETE_PROBE_EVIDENCE: {probe.get('id')}")
            continue
        predictions = _prediction_map(probe)
        discriminates_for: set[str] = set()
        for hypothesis_id in hypothesis_ids:
            predicted = predictions.get(hypothesis_id)
            if predicted != observed:
                continue
            alternatives = hypothesis_ids - {hypothesis_id}
            if all(
                isinstance(predictions.get(alternative), str) and predictions[alternative] != predicted
                for alternative in alternatives
            ):
                discriminates_for.add(hypothesis_id)
        add(
            evidence_ref,
            EvidenceBinding(
                _source_group(probe.get("source_group")),
                "probe",
                frozenset(discriminates_for),
            ),
        )
    return registry, findings


def _string_list(value: object, label: str, findings: list[str]) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        findings.append(f"{label} must be an array of strings")
        return []
    return cast(list[str], value)


def validate_diagnostic_state(state: Mapping[str, object]) -> list[str]:
    """Validate causal claims against independent, discriminating evidence.

    Args:
        state: Structurally valid diagnostic-state document.

    Returns:
        Semantic findings. A ``proven`` causal assessment is accepted only when
        its evidence exists, is independently sourced, and includes an executed
        probe whose prediction discriminates the winning hypothesis from every
        still-credible alternative.
    """
    findings: list[str] = []
    try:
        hypotheses = _mapping_list(state.get("hypotheses"), "hypotheses")
        observations = _mapping_list(state.get("observations"), "observations")
        probes = _mapping_list(state.get("probes", []), "probes")
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

    non_disproven_hypothesis_ids = {
        hypothesis_id
        for hypothesis_id, hypothesis in hypothesis_by_id.items()
        if hypothesis.get("status") != "disproven"
    }
    evidence, evidence_findings = _evidence_registry(
        observations,
        probes,
        non_disproven_hypothesis_ids,
    )
    findings.extend(evidence_findings)

    causal = state.get("causal_assessment")
    if not isinstance(causal, Mapping):
        return findings + ["causal_assessment must be an object"]
    try:
        causes = _mapping_list(causal.get("causes"), "causal_assessment.causes")
    except DiagnosticReasoningError as error:
        return findings + [str(error)]

    primary_causes = [cause for cause in causes if cause.get("role") == "primary"]
    if len(primary_causes) > 1:
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
        cause_hypothesis = hypothesis_by_id[hypothesis_id]
        if cause_hypothesis.get("status") == "disproven":
            findings.append(f"DISPROVEN_CAUSAL_HYPOTHESIS: {hypothesis_id}")
        source_refs = cause_hypothesis.get("config_source_refs", [])
        if isinstance(source_refs, list):
            for source_ref in source_refs:
                if not isinstance(source_ref, str) or config_status.get(source_ref) != "runtime-proven":
                    findings.append(f"CONFIG_SOURCE_NOT_RUNTIME_PROVEN: {hypothesis_id} -> {source_ref}")
        cause_refs = _string_list(cause.get("evidence_refs"), f"cause {hypothesis_id} evidence_refs", findings)
        supporting = _supporting_evidence_values(cause_hypothesis)
        missing_support = sorted(ref for ref in cause_refs if ref not in supporting)
        if missing_support:
            findings.append(f"PROVEN_EVIDENCE_NOT_BOUND_TO_HYPOTHESIS: {hypothesis_id} -> {missing_support}")
        for evidence_ref in cause_refs:
            if evidence_ref not in evidence:
                findings.append(f"UNKNOWN_CAUSAL_EVIDENCE: {hypothesis_id} -> {evidence_ref}")

    unresolved = causal.get("unresolved_alternatives")
    if causal.get("status") == "proven":
        if not causes:
            findings.append("PROVEN_WITHOUT_CAUSE: proven assessment requires causal evidence")
        if len(primary_causes) != 1:
            findings.append("PROVEN_WITHOUT_SINGLE_PRIMARY_CAUSE")
        if isinstance(unresolved, list) and unresolved:
            findings.append("PROVEN_WITH_UNRESOLVED_ALTERNATIVES")
        if any(cause.get("support") != "proven" for cause in causes):
            findings.append("PROVEN_WITH_NONPROVEN_CAUSE")

        if len(primary_causes) == 1:
            primary = primary_causes[0]
            winner = primary.get("hypothesis_id")
            if isinstance(winner, str) and winner in hypothesis_by_id:
                refs = _string_list(primary.get("evidence_refs"), f"cause {winner} evidence_refs", findings)
                bindings = [evidence[ref] for ref in refs if ref in evidence]
                source_groups = {binding.source_group for binding in bindings if binding.source_group is not None}
                if len(source_groups) < 2:
                    findings.append(f"PROVEN_WITHOUT_INDEPENDENT_CONFIRMATION: {winner}")
                if not any(winner in binding.discriminates_for for binding in bindings):
                    findings.append(f"PROVEN_WITHOUT_DISCRIMINATING_EVIDENCE: {winner}")

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
        current_observations = _mapping_list(current.get("observations"), "observations")
        current_probes = _mapping_list(current.get("probes", []), "probes")
    except DiagnosticReasoningError as error:
        return findings + [str(error)]

    current_by_id = {item["id"]: item for item in current_hypotheses if isinstance(item.get("id"), str)}
    current_non_disproven_ids = {
        hypothesis_id
        for hypothesis_id, hypothesis in current_by_id.items()
        if hypothesis.get("status") != "disproven"
    }
    current_evidence, _ = _evidence_registry(current_observations, current_probes, current_non_disproven_ids)
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
        from_revision = reopen.get("from_revision")
        if from_revision != old_revision:
            findings.append(f"DISPROVEN_HYPOTHESIS_REOPEN_REVISION_MISMATCH: {hypothesis_id}")
        evidence_ref = reopen.get("evidence_ref")
        if not isinstance(evidence_ref, str) or evidence_ref in _evidence_values(old):
            findings.append(f"DISPROVEN_HYPOTHESIS_REUSED_OLD_EVIDENCE: {hypothesis_id}")
            continue
        if evidence_ref not in current_evidence:
            findings.append(f"DISPROVEN_HYPOTHESIS_UNREGISTERED_REOPEN_EVIDENCE: {hypothesis_id} -> {evidence_ref}")
        if evidence_ref not in _supporting_evidence_values(new):
            findings.append(f"DISPROVEN_HYPOTHESIS_REOPEN_EVIDENCE_NOT_SUPPORTING: {hypothesis_id} -> {evidence_ref}")

    return findings
