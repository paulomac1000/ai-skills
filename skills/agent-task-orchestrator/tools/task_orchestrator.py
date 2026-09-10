#!/usr/bin/env python3
"""Deterministic task-intent, delegation, and completion admission helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Collection, Mapping, Sequence


class OrchestrationError(ValueError):
    """Raised when a requested orchestration transition violates the task contract."""


@dataclass(frozen=True)
class ScopeAdmission:
    allowed: bool
    code: str
    target: str
    side_effect_class: str


@dataclass(frozen=True)
class BaseAdmission:
    admission: str
    reason: str


@dataclass(frozen=True)
class ChildAdmission:
    capabilities: tuple[str, ...]
    authority: tuple[str, ...]
    resource_domains: tuple[str, ...]


@dataclass(frozen=True)
class DispatchDecision:
    allowed: bool
    code: str
    child_job_id: str | None


@dataclass(frozen=True)
class ProgressDecision:
    code: str
    consecutive_no_progress: int


@dataclass(frozen=True)
class TerminalDecision:
    code: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class SchedulingDecision:
    code: str
    may_yield: bool


@dataclass(frozen=True)
class CompletionDecision:
    completed: bool
    blockers: tuple[str, ...]


def _strings(values: Collection[str], *, label: str) -> set[str]:
    result = {str(value) for value in values}
    if any(not value for value in result):
        raise OrchestrationError(f"{label} contains an empty identifier")
    return result


def admit_scope(
    *,
    target: str,
    side_effect_class: str,
    in_scope_targets: Collection[str],
    protected_or_out_of_scope_targets: Collection[str],
    allowed_side_effect_classes: Collection[str],
) -> ScopeAdmission:
    """Admit only exact targets and side-effect classes already present in task intent."""
    in_scope = _strings(in_scope_targets, label="in_scope_targets")
    protected = _strings(protected_or_out_of_scope_targets, label="protected_or_out_of_scope_targets")
    side_effects = _strings(allowed_side_effect_classes, label="allowed_side_effect_classes")
    if target in protected:
        return ScopeAdmission(False, "TARGET_PROTECTED_OR_OUT_OF_SCOPE", target, side_effect_class)
    if target not in in_scope:
        return ScopeAdmission(False, "TARGET_NOT_IN_SCOPE", target, side_effect_class)
    if side_effect_class not in side_effects:
        return ScopeAdmission(False, "SIDE_EFFECT_NOT_AUTHORIZED", target, side_effect_class)
    return ScopeAdmission(True, "SCOPE_ADMITTED", target, side_effect_class)


def admit_base(
    planning_base: Mapping[str, str],
    execution_base: Mapping[str, str],
    *,
    base_relationship: str,
    revalidated_assumptions: Sequence[str] = (),
    overlapping_upstream_change: bool | None = None,
) -> BaseAdmission:
    """Classify planning/execution base drift without treating branch movement as sufficient evidence."""
    for base_name, base in (("planning_base", planning_base), ("execution_base", execution_base)):
        for field in ("repository", "ref", "revision"):
            if not base.get(field):
                return BaseAdmission("BASE_UNKNOWN", f"{base_name}.{field} is unknown")

    if planning_base["repository"] != execution_base["repository"]:
        return BaseAdmission("BASE_TOPOLOGY_CHANGED", "repository changed")
    if planning_base["ref"] != execution_base["ref"]:
        return BaseAdmission("BASE_TOPOLOGY_CHANGED", "ref changed")
    if planning_base["revision"] == execution_base["revision"]:
        return BaseAdmission("BASE_UNCHANGED", "execution revision equals planning revision")

    if base_relationship == "unknown" or overlapping_upstream_change is None:
        return BaseAdmission("BASE_UNKNOWN", "base relationship or overlap evidence is unknown")
    if base_relationship != "descendant":
        return BaseAdmission("BASE_TOPOLOGY_CHANGED", f"relationship is {base_relationship}")
    if overlapping_upstream_change:
        return BaseAdmission("BASE_TOPOLOGY_CHANGED", "upstream changes overlap plan assumptions")
    assumptions = tuple(item for item in revalidated_assumptions if item)
    if not assumptions:
        return BaseAdmission("BASE_UNKNOWN", "advanced base lacks explicit assumption revalidation")
    return BaseAdmission("BASE_ADVANCED_COMPATIBLE", "descendant base explicitly revalidated with no overlap")


def admit_child(
    *,
    requested_capabilities: Collection[str],
    available_capabilities: Collection[str],
    requested_authority: Collection[str],
    parent_authority: Collection[str],
    requested_resource_domains: Collection[str],
    parent_resource_domains: Collection[str],
) -> ChildAdmission:
    """Admit only the minimum child capability/authority/resource subset supplied by the parent."""
    requested_caps = _strings(requested_capabilities, label="requested_capabilities")
    available_caps = _strings(available_capabilities, label="available_capabilities")
    requested_auth = _strings(requested_authority, label="requested_authority")
    parent_auth = _strings(parent_authority, label="parent_authority")
    requested_resources = _strings(requested_resource_domains, label="requested_resource_domains")
    parent_resources = _strings(parent_resource_domains, label="parent_resource_domains")

    missing_caps = requested_caps - available_caps
    missing_auth = requested_auth - parent_auth
    missing_resources = requested_resources - parent_resources
    if missing_caps:
        raise OrchestrationError(f"child capability exceeds parent admission: {sorted(missing_caps)}")
    if missing_auth:
        raise OrchestrationError(f"child authority exceeds parent admission: {sorted(missing_auth)}")
    if missing_resources:
        raise OrchestrationError(f"child resource domain exceeds parent admission: {sorted(missing_resources)}")
    return ChildAdmission(
        tuple(sorted(requested_caps)),
        tuple(sorted(requested_auth)),
        tuple(sorted(requested_resources)),
    )


def admit_dispatch(*, attempt_id: str, known_attempts: Mapping[str, str]) -> DispatchDecision:
    """Prevent duplicate dispatch: an existing attempt must be reconciled or continued, never relaunched."""
    if not attempt_id:
        raise OrchestrationError("attempt_id is required")
    child_job_id = known_attempts.get(attempt_id)
    if child_job_id:
        return DispatchDecision(False, "ALREADY_DISPATCHED", child_job_id)
    return DispatchDecision(True, "DISPATCH_ALLOWED", None)


def build_continuation(
    *,
    attempt_id: str,
    child_job_id: str,
    continuation_delta: Mapping[str, Any],
) -> dict[str, Any]:
    """Continue one durable child using delta-only state instead of redispatching the full task."""
    if not attempt_id or not child_job_id:
        raise OrchestrationError("attempt_id and child_job_id are required for continuation")
    if not continuation_delta:
        raise OrchestrationError("continuation_delta must contain only the new information")
    forbidden = {"full_prompt", "full_task", "task_history", "raw_secret"}
    leaked = forbidden.intersection(continuation_delta)
    if leaked:
        raise OrchestrationError(f"continuation_delta contains forbidden replay fields: {sorted(leaked)}")
    return {"attempt_id": attempt_id, "child_job_id": child_job_id, "continuation_delta": dict(continuation_delta)}


def classify_progress(
    samples: Sequence[Mapping[str, Any]],
    *,
    max_consecutive_no_progress: int = 3,
) -> ProgressDecision:
    """Bound silent no-op/heartbeat loops using explicit meaningful-progress evidence."""
    if max_consecutive_no_progress < 1:
        raise OrchestrationError("max_consecutive_no_progress must be positive")
    consecutive = 0
    for sample in reversed(samples):
        meaningful = sample.get("meaningful_change") is True and bool(sample.get("evidence_refs"))
        if meaningful:
            break
        consecutive += 1
    if consecutive >= max_consecutive_no_progress:
        return ProgressDecision("NO_PROGRESS_LIMIT", consecutive)
    return ProgressDecision("PROGRESS_PENDING", consecutive)


def classify_terminal(
    *,
    requires_work: bool,
    child_disposition: str,
    expected_outputs: Collection[str],
    evidence_refs: Collection[str] = (),
    published_revision: str | None = None,
    no_change_evidence_refs: Collection[str] = (),
) -> TerminalDecision:
    """Reject completed child reports that provide no expected artifact/change/no-change evidence."""
    evidence = tuple(sorted(_strings(evidence_refs, label="evidence_refs")))
    no_change = tuple(sorted(_strings(no_change_evidence_refs, label="no_change_evidence_refs")))
    expected = _strings(expected_outputs, label="expected_outputs")
    combined = tuple(sorted(set(evidence) | set(no_change)))
    if child_disposition != "completed":
        return TerminalDecision("CHILD_NOT_COMPLETED", combined)
    if requires_work and expected and not (combined or published_revision):
        return TerminalDecision("COMPLETED_NO_EVIDENCE", ())
    if requires_work and not expected and not combined and not published_revision:
        return TerminalDecision("COMPLETED_NO_EVIDENCE", ())
    return TerminalDecision("TERMINAL_EVIDENCE_PRESENT", combined)


def schedule_parent(*, active_background_children: int, runnable_parent_work: int) -> SchedulingDecision:
    """A parent may yield only when no independent runnable parent work remains."""
    if active_background_children < 0 or runnable_parent_work < 0:
        raise OrchestrationError("work counts cannot be negative")
    if runnable_parent_work:
        return SchedulingDecision("CONTINUE_PARENT_WORK", False)
    if active_background_children:
        return SchedulingDecision("WAIT_FOR_CHILD_EVIDENCE", True)
    return SchedulingDecision("COMPLETE_OR_REPLAN", False)


def resource_domains_conflict(left: Collection[str], right: Collection[str]) -> bool:
    """Conservatively serialize delegates that claim any identical writer/resource domain."""
    return bool(_strings(left, label="left resource domains") & _strings(right, label="right resource domains"))


def completion_gate(
    ledger: Mapping[str, Any],
    *,
    capability_evidence: Mapping[str, Collection[str]],
    method_evidence: Mapping[str, Collection[str]],
    acceptance_evidence: Mapping[str, Collection[str]],
) -> CompletionDecision:
    """Compare current mandatory intent against evidence; child completion never completes the parent by itself."""
    blockers: list[str] = []
    for requirement in ledger.get("requirements", []):
        if not isinstance(requirement, Mapping) or not requirement.get("mandatory"):
            continue
        if requirement.get("status") == "superseded":
            continue
        requirement_id = str(requirement.get("id") or "unknown")
        if requirement.get("status") != "satisfied":
            blockers.append(f"requirement:{requirement_id}:{requirement.get('status', 'unknown')}")
        elif not requirement.get("evidence_refs"):
            blockers.append(f"requirement:{requirement_id}:missing-evidence")

    for capability in ledger.get("required_capabilities", []):
        if not capability_evidence.get(str(capability)):
            blockers.append(f"capability:{capability}:missing-evidence")
    for method in ledger.get("required_execution_methods", []):
        if not method_evidence.get(str(method)):
            blockers.append(f"method:{method}:missing-evidence")
    for criterion in ledger.get("acceptance_criteria", []):
        if not acceptance_evidence.get(str(criterion)):
            blockers.append(f"acceptance:{criterion}:missing-evidence")

    return CompletionDecision(not blockers, tuple(blockers))


def compact_handoff(
    ledger: Mapping[str, Any],
    *,
    active_children: Sequence[Mapping[str, str]] = (),
) -> dict[str, Any]:
    """Return compact continuation state without replaying task history or satisfied requirement prose."""
    unresolved = []
    for requirement in ledger.get("requirements", []):
        if not isinstance(requirement, Mapping):
            continue
        if requirement.get("status") in {"pending", "blocked"}:
            unresolved.append(str(requirement.get("id") or "unknown"))
    children = [
        {
            "attempt_id": child.get("attempt_id"),
            "child_job_id": child.get("child_job_id"),
            "execution_revision": child.get("execution_revision"),
        }
        for child in active_children
    ]
    return {
        "ledger_id": ledger.get("ledger_id"),
        "task_id": ledger.get("task_id"),
        "intent_revision": ledger.get("intent_revision"),
        "unresolved_requirement_ids": unresolved,
        "required_capabilities": list(ledger.get("required_capabilities", [])),
        "required_execution_methods": list(ledger.get("required_execution_methods", [])),
        "scope": dict(ledger.get("scope") or {}),
        "active_children": children,
    }
