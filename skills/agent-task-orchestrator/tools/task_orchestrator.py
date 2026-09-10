#!/usr/bin/env python3
"""Deterministic task-intent, delegation, and completion admission helpers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FULL_REVISION = re.compile(r"^[0-9a-fA-F]{40}$")
FORBIDDEN_CONTINUATION_FIELDS = frozenset({"full_prompt", "full_task", "task_history", "raw_secret"})
MAX_DISPATCH_RECORD_BYTES = 64 * 1024


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
class DispatchReservation:
    allowed: bool
    code: str
    attempt_id: str
    reservation_token: str | None
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


def _exact_revision(value: object) -> str | None:
    if not isinstance(value, str) or FULL_REVISION.fullmatch(value) is None:
        return None
    return value


def _bound_evidence(
    ref: str,
    bindings: Mapping[str, Mapping[str, Any]],
    *,
    intent_revision: int,
    execution_revision: str,
    subject: str,
) -> bool:
    binding = bindings.get(ref)
    if not isinstance(binding, Mapping):
        return False
    if binding.get("intent_revision") != intent_revision:
        return False
    if binding.get("execution_revision") != execution_revision:
        return False
    subjects = binding.get("subjects")
    if not isinstance(subjects, Sequence) or isinstance(subjects, (str, bytes, bytearray)):
        return False
    return subject in {str(value) for value in subjects}


def _contains_forbidden_continuation_field(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if key_text in FORBIDDEN_CONTINUATION_FIELDS:
                found.add(key_text)
            found.update(_contains_forbidden_continuation_field(item))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            found.update(_contains_forbidden_continuation_field(item))
    return found


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
    """Classify planning/execution base drift using immutable full revisions."""
    for base_name, base in (("planning_base", planning_base), ("execution_base", execution_base)):
        for field in ("repository", "ref"):
            if not base.get(field):
                return BaseAdmission("BASE_UNKNOWN", f"{base_name}.{field} is unknown")
        if _exact_revision(base.get("revision")) is None:
            return BaseAdmission("BASE_UNKNOWN", f"{base_name}.revision is not an immutable full revision")

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
    """Admit a child only with a strict authority subset and bounded resources."""
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
    if requested_auth == parent_auth:
        raise OrchestrationError("child authority must be a strict subset of parent authority")
    if missing_resources:
        raise OrchestrationError(f"child resource domain exceeds parent admission: {sorted(missing_resources)}")
    return ChildAdmission(
        tuple(sorted(requested_caps)),
        tuple(sorted(requested_auth)),
        tuple(sorted(requested_resources)),
    )


def admit_dispatch(*, attempt_id: str, known_attempts: Mapping[str, str]) -> DispatchDecision:
    """Classify known attempts; new dispatch still requires atomic reserve_dispatch()."""
    if not attempt_id:
        raise OrchestrationError("attempt_id is required")
    child_job_id = known_attempts.get(attempt_id)
    if child_job_id:
        return DispatchDecision(False, "ALREADY_DISPATCHED", child_job_id)
    return DispatchDecision(False, "ATOMIC_RESERVATION_REQUIRED", None)


def _attempt_record_path(attempt_store: Path, attempt_id: str) -> Path:
    digest = hashlib.sha256(attempt_id.encode("utf-8")).hexdigest()
    return attempt_store / f"{digest}.json"


def _prepare_attempt_store(attempt_store: Path) -> Path:
    attempt_store.mkdir(parents=True, exist_ok=True)
    if attempt_store.is_symlink():
        raise OrchestrationError("attempt store must not be a symlink")
    try:
        resolved = attempt_store.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise OrchestrationError(f"attempt store cannot be resolved safely: {error}") from error
    if not resolved.is_dir():
        raise OrchestrationError("attempt store must be a directory")
    return resolved


def _read_attempt_record(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise OrchestrationError("attempt record is missing or not a regular file")
    try:
        size = path.stat().st_size
    except OSError as error:
        raise OrchestrationError(f"attempt record cannot be inspected: {error}") from error
    if size > MAX_DISPATCH_RECORD_BYTES:
        raise OrchestrationError("attempt record exceeds bounded size")
    with path.open("rb") as handle:
        data = handle.read(MAX_DISPATCH_RECORD_BYTES + 1)
    if len(data) > MAX_DISPATCH_RECORD_BYTES:
        raise OrchestrationError("attempt record exceeds bounded size")
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise OrchestrationError(f"attempt record is invalid: {error}") from error
    if not isinstance(value, dict):
        raise OrchestrationError("attempt record must be an object")
    return value


def reserve_dispatch(
    *,
    attempt_store: Path,
    attempt_id: str,
    intent_revision: int,
    execution_revision: str,
) -> DispatchReservation:
    """Atomically reserve one attempt before any child launch."""
    if not attempt_id:
        raise OrchestrationError("attempt_id is required")
    if not isinstance(intent_revision, int) or isinstance(intent_revision, bool) or intent_revision < 1:
        raise OrchestrationError("intent_revision must be a positive integer")
    if _exact_revision(execution_revision) is None:
        raise OrchestrationError("execution_revision must be an immutable full revision")

    store = _prepare_attempt_store(attempt_store)
    record_path = _attempt_record_path(store, attempt_id)
    reservation_token = secrets.token_hex(32)
    record = {
        "schema_version": 1,
        "attempt_id": attempt_id,
        "intent_revision": intent_revision,
        "execution_revision": execution_revision,
        "state": "reserved",
        "reservation_token": reservation_token,
        "child_job_id": None,
    }
    payload = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(record_path, flags, 0o600)
    except FileExistsError:
        existing = _read_attempt_record(record_path)
        child_job_id = existing.get("child_job_id")
        code = "ALREADY_DISPATCHED" if isinstance(child_job_id, str) and child_job_id else "ATTEMPT_ALREADY_RESERVED"
        return DispatchReservation(
            False,
            code,
            attempt_id,
            None,
            child_job_id if isinstance(child_job_id, str) else None,
        )
    except OSError as error:
        raise OrchestrationError(f"attempt reservation failed: {error}") from error

    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            record_path.unlink()
        except OSError:
            pass
        raise
    return DispatchReservation(True, "DISPATCH_RESERVED", attempt_id, reservation_token, None)


def bind_dispatched_child(
    *,
    attempt_store: Path,
    attempt_id: str,
    reservation_token: str,
    child_job_id: str,
) -> DispatchReservation:
    """Bind the exact durable child identity to the winning reservation."""
    if not reservation_token or not child_job_id:
        raise OrchestrationError("reservation_token and child_job_id are required")
    store = _prepare_attempt_store(attempt_store)
    path = _attempt_record_path(store, attempt_id)
    record = _read_attempt_record(path)
    if record.get("attempt_id") != attempt_id:
        raise OrchestrationError("attempt record identity does not match requested attempt")
    existing_child = record.get("child_job_id")
    if isinstance(existing_child, str) and existing_child:
        if existing_child != child_job_id:
            raise OrchestrationError("attempt is already bound to a different child job")
        return DispatchReservation(False, "ALREADY_DISPATCHED", attempt_id, None, existing_child)
    if record.get("state") != "reserved" or record.get("reservation_token") != reservation_token:
        raise OrchestrationError("attempt reservation token does not authorize child binding")

    updated = {**record, "state": "dispatched", "child_job_id": child_job_id}
    payload = (json.dumps(updated, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    temp_path = store / f".{path.name}.{secrets.token_hex(8)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        descriptor = os.open(temp_path, flags, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except OSError as error:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise OrchestrationError(f"child binding could not be persisted: {error}") from error
    return DispatchReservation(False, "ALREADY_DISPATCHED", attempt_id, None, child_job_id)


def dispatch_once(
    *,
    attempt_store: Path,
    attempt_id: str,
    intent_revision: int,
    execution_revision: str,
    dispatch: Callable[[], str],
) -> DispatchReservation:
    """Run the child-launch callback only for the winner of durable attempt reservation."""
    reservation = reserve_dispatch(
        attempt_store=attempt_store,
        attempt_id=attempt_id,
        intent_revision=intent_revision,
        execution_revision=execution_revision,
    )
    if not reservation.allowed:
        return reservation
    assert reservation.reservation_token is not None
    try:
        child_job_id = dispatch()
    except Exception as error:
        raise OrchestrationError(
            "child dispatch outcome is ambiguous after durable reservation; reconcile the reserved attempt before retry"
        ) from error
    if not isinstance(child_job_id, str) or not child_job_id:
        raise OrchestrationError(
            "child dispatch returned no durable child identity; reconcile the reserved attempt before retry"
        )
    return bind_dispatched_child(
        attempt_store=attempt_store,
        attempt_id=attempt_id,
        reservation_token=reservation.reservation_token,
        child_job_id=child_job_id,
    )


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
    leaked = _contains_forbidden_continuation_field(continuation_delta)
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
    task_id: str | None = None,
    intent_revision: int | None = None,
    execution_revision: str | None = None,
    evidence_bindings: Mapping[str, Mapping[str, Any]] | None = None,
    evidence_refs: Collection[str] = (),
    published_revision: str | None = None,
    no_change_evidence_refs: Collection[str] = (),
) -> TerminalDecision:
    """Accept terminal work evidence only when bound to current intent, execution, task, and outputs."""
    evidence = tuple(sorted(_strings(evidence_refs, label="evidence_refs")))
    no_change = tuple(sorted(_strings(no_change_evidence_refs, label="no_change_evidence_refs")))
    expected = _strings(expected_outputs, label="expected_outputs")
    combined = tuple(sorted(set(evidence) | set(no_change)))
    if child_disposition != "completed":
        return TerminalDecision("CHILD_NOT_COMPLETED", combined)
    if not requires_work:
        return TerminalDecision("TERMINAL_EVIDENCE_PRESENT", combined)
    if (
        not isinstance(intent_revision, int)
        or isinstance(intent_revision, bool)
        or intent_revision < 1
        or execution_revision is None
        or _exact_revision(execution_revision) is None
        or evidence_bindings is None
    ):
        return TerminalDecision("COMPLETED_NO_EVIDENCE", ())

    refs = set(combined)
    for output in expected:
        if output == "published-revision" and published_revision == execution_revision:
            continue
        if not any(
            _bound_evidence(
                ref,
                evidence_bindings,
                intent_revision=intent_revision,
                execution_revision=execution_revision,
                subject=f"output:{output}",
            )
            for ref in refs
        ):
            return TerminalDecision("COMPLETED_NO_EVIDENCE", ())
    if not expected:
        if published_revision == execution_revision:
            return TerminalDecision("TERMINAL_EVIDENCE_PRESENT", combined)
        if not task_id or not refs:
            return TerminalDecision("COMPLETED_NO_EVIDENCE", ())
        if not any(
            _bound_evidence(
                ref,
                evidence_bindings,
                intent_revision=intent_revision,
                execution_revision=execution_revision,
                subject=f"task:{task_id}",
            )
            for ref in refs
        ):
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
    execution_revision: str | None = None,
    evidence_bindings: Mapping[str, Mapping[str, Any]] | None = None,
    capability_evidence: Mapping[str, Collection[str]],
    method_evidence: Mapping[str, Collection[str]],
    acceptance_evidence: Mapping[str, Collection[str]],
) -> CompletionDecision:
    """Complete only structurally valid current intent with evidence bound to its exact execution."""
    blockers: list[str] = []
    required_fields = (
        "intent_revision",
        "requirements",
        "required_capabilities",
        "required_execution_methods",
        "acceptance_criteria",
    )
    for field in required_fields:
        if field not in ledger:
            blockers.append(f"ledger:missing:{field}")
    intent_revision = ledger.get("intent_revision")
    if not isinstance(intent_revision, int) or isinstance(intent_revision, bool) or intent_revision < 1:
        blockers.append("ledger:invalid:intent_revision")
    if _exact_revision(execution_revision) is None:
        blockers.append("execution:missing-or-invalid-revision")
    if evidence_bindings is None:
        blockers.append("evidence:bindings-missing")

    can_bind = (
        isinstance(intent_revision, int)
        and not isinstance(intent_revision, bool)
        and intent_revision >= 1
        and isinstance(execution_revision, str)
        and _exact_revision(execution_revision) is not None
        and evidence_bindings is not None
    )

    requirements = ledger.get("requirements")
    if isinstance(requirements, Sequence) and not isinstance(requirements, (str, bytes, bytearray)):
        for requirement in requirements:
            if not isinstance(requirement, Mapping):
                blockers.append("requirement:invalid-entry")
                continue
            if not requirement.get("mandatory"):
                continue
            if requirement.get("status") == "superseded":
                continue
            requirement_id = str(requirement.get("id") or "unknown")
            if requirement.get("status") != "satisfied":
                blockers.append(f"requirement:{requirement_id}:{requirement.get('status', 'unknown')}")
                continue
            refs = requirement.get("evidence_refs")
            if not isinstance(refs, Sequence) or isinstance(refs, (str, bytes, bytearray)) or not refs:
                blockers.append(f"requirement:{requirement_id}:missing-evidence")
                continue
            if can_bind and not any(
                isinstance(ref, str)
                and _bound_evidence(
                    ref,
                    evidence_bindings,
                    intent_revision=intent_revision,
                    execution_revision=execution_revision,
                    subject=f"requirement:{requirement_id}",
                )
                for ref in refs
            ):
                blockers.append(f"requirement:{requirement_id}:unbound-evidence")
    elif "requirements" in ledger:
        blockers.append("ledger:invalid:requirements")

    def check_axis(
        ledger_field: str,
        evidence: Mapping[str, Collection[str]],
        prefix: str,
    ) -> None:
        values = ledger.get(ledger_field)
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
            if ledger_field in ledger:
                blockers.append(f"ledger:invalid:{ledger_field}")
            return
        for raw in values:
            subject_value = str(raw)
            refs = evidence.get(subject_value)
            if not refs:
                blockers.append(f"{prefix}:{subject_value}:missing-evidence")
                continue
            if can_bind and not any(
                _bound_evidence(
                    str(ref),
                    evidence_bindings,
                    intent_revision=intent_revision,
                    execution_revision=execution_revision,
                    subject=f"{prefix}:{subject_value}",
                )
                for ref in refs
            ):
                blockers.append(f"{prefix}:{subject_value}:unbound-evidence")

    check_axis("required_capabilities", capability_evidence, "capability")
    check_axis("required_execution_methods", method_evidence, "method")
    check_axis("acceptance_criteria", acceptance_evidence, "acceptance")
    return CompletionDecision(not blockers, tuple(dict.fromkeys(blockers)))


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
