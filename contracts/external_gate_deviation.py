#!/usr/bin/env python3
"""Provider-neutral external-gate availability, substitute, and catch-up receipts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ROOT = frozenset(
    {
        "schema_version",
        "receipt_kind",
        "gate",
        "observation",
        "incident",
        "retry_policy",
        "substitute",
        "catchup",
        "receipt_digest",
    }
)
_GATE = frozenset({"gate_id", "provider", "expected_subject_ref", "policy_revision"})
_OBS = frozenset(
    {
        "state",
        "product_verdict",
        "repository_steps_executed",
        "failure_class",
        "observed_at",
        "evidence_ref",
        "evidence_digest",
    }
)
_INC = frozenset(
    {"fingerprint", "scope", "scope_ref", "first_observed_at", "last_observed_at", "fresh_until", "reopen_on"}
)
_RETRY = frozenset({"mode", "next_eligible_at"})
_SUB = frozenset(
    {
        "allowed",
        "authority_ref",
        "profile_ref",
        "exact_subject_ref",
        "evidence_ref",
        "evidence_digest",
        "verdict",
        "reproduction",
    }
)
_REPRO = frozenset(
    {
        "original_workflow_digest",
        "exact_subject_ref",
        "source_checkout",
        "environment_digest",
        "inherited_workspace_state",
        "isolation_ref",
        "command_ref",
        "report_digest",
    }
)
_CATCHUP = frozenset({"required", "subject_ref", "state", "evidence_ref", "evidence_digest"})


class GateExecutionState(StrEnum):
    EXECUTED = "EXECUTED"
    NOT_EXECUTED = "NOT_EXECUTED"
    OBSERVER_UNAVAILABLE = "OBSERVER_UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class GateVerdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class FailureClass(StrEnum):
    NONE = "none"
    BILLING = "billing"
    QUOTA = "quota"
    RUNNER_UNAVAILABLE = "runner_unavailable"
    PROVIDER_OUTAGE = "provider_outage"
    AUTH = "auth"
    REPOSITORY = "repository"
    UNKNOWN = "unknown"


class IncidentScope(StrEnum):
    ACCOUNT = "account"
    ORGANIZATION = "organization"
    REPOSITORY = "repository"
    WORKFLOW = "workflow"
    RUNNER_POOL = "runner_pool"
    UNKNOWN = "unknown"


class RetryMode(StrEnum):
    NORMAL = "normal"
    SUPPRESS_UNTIL_CHANGE = "suppress_until_change"
    BOUNDED_BACKOFF = "bounded_backoff"
    OPERATOR_ONLY = "operator_only"


class CatchupState(StrEnum):
    PENDING = "PENDING"
    SATISFIED = "SATISFIED"
    SUPERSEDED = "SUPERSEDED"
    NOT_REQUIRED = "NOT_REQUIRED"


@dataclass(frozen=True)
class GateObservation:
    state: GateExecutionState
    product_verdict: GateVerdict
    repository_steps_executed: bool | None
    observed_at: str
    evidence_ref: str
    evidence_digest: str
    failure_class: FailureClass = FailureClass.NONE


@dataclass(frozen=True)
class GateIncident:
    fingerprint: str
    scope: IncidentScope
    scope_ref: str
    first_observed_at: str
    last_observed_at: str
    fresh_until: str | None
    reopen_on: tuple[str, ...] = ("provider_generation_change", "scheduled_retry_after", "operator_override")


@dataclass(frozen=True)
class SubstituteReproduction:
    original_workflow_digest: str
    exact_subject_ref: str
    source_checkout: str
    environment_digest: str
    inherited_workspace_state: bool
    isolation_ref: str
    command_ref: str
    report_digest: str


@dataclass(frozen=True)
class SubstituteEvidence:
    allowed: bool
    authority_ref: str | None = None
    profile_ref: str | None = None
    exact_subject_ref: str | None = None
    evidence_ref: str | None = None
    evidence_digest: str | None = None
    verdict: GateVerdict = GateVerdict.UNKNOWN
    reproduction: SubstituteReproduction | None = None


@dataclass(frozen=True)
class CatchupObligation:
    required: bool
    subject_ref: str | None
    state: CatchupState
    evidence_ref: str | None = None
    evidence_digest: str | None = None


def _text(value: object, name: str, limit: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must be bounded non-empty text")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{name} must contain Unicode scalar values") from exc
    return value


def _digest(value: object, name: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be a sha256:<64 lowercase hex> digest")
    return value


def _time(value: object, name: str) -> datetime:
    raw = _text(value, name, 128)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an RFC3339/ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed.astimezone(UTC)


def _doc_digest(document: dict[str, Any]) -> str:
    raw = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _exact(value: object, fields: frozenset[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{name} has an invalid field set")
    return value


def _validate_observation(value: GateObservation) -> None:
    _time(value.observed_at, "observation.observed_at")
    _text(value.evidence_ref, "observation.evidence_ref")
    _digest(value.evidence_digest, "observation.evidence_digest")
    if type(value.repository_steps_executed) not in {bool, type(None)}:
        raise ValueError("repository_steps_executed must be boolean or null")
    if value.state is GateExecutionState.EXECUTED:
        if value.repository_steps_executed is not True or value.product_verdict not in {
            GateVerdict.PASS,
            GateVerdict.FAIL,
        }:
            raise ValueError("EXECUTED requires executed repository steps and a real PASS/FAIL")
        if value.failure_class is not FailureClass.NONE:
            raise ValueError("EXECUTED cannot retain an infrastructure failure class")
        return
    if value.product_verdict is not GateVerdict.UNKNOWN or value.failure_class is FailureClass.NONE:
        raise ValueError(
            "non-executed/unknown external gate cannot carry a product PASS or FAIL and requires a typed failure class"
        )
    if value.state is GateExecutionState.NOT_EXECUTED and value.repository_steps_executed is not False:
        raise ValueError("NOT_EXECUTED requires repository_steps_executed=false")
    if (
        value.state in {GateExecutionState.OBSERVER_UNAVAILABLE, GateExecutionState.UNKNOWN}
        and value.repository_steps_executed is not None
    ):
        raise ValueError("observer-unavailable/unknown requires repository_steps_executed=null")


def _validate_incident(value: GateIncident) -> None:
    _digest(value.fingerprint, "incident.fingerprint")
    _text(value.scope_ref, "incident.scope_ref")
    first, last = (
        _time(value.first_observed_at, "incident.first_observed_at"),
        _time(value.last_observed_at, "incident.last_observed_at"),
    )
    if last < first:
        raise ValueError("incident last observation precedes first")
    if value.fresh_until is not None and _time(value.fresh_until, "incident.fresh_until") < last:
        raise ValueError("incident freshness precedes last observation")
    if not value.reopen_on or len(value.reopen_on) != len(set(value.reopen_on)):
        raise ValueError("incident reopen signals must be non-empty and unique")
    if len(value.reopen_on) > 32:
        # the pinned schema declares maxItems: 32; no silent truncation, no acceptance
        raise ValueError("incident reopen signals exceed the schema limit of 32")
    for item in value.reopen_on:
        _text(item, "incident.reopen_on", 128)


def _validate_substitute(value: SubstituteEvidence, subject: str) -> None:
    if type(value.allowed) is not bool:
        raise ValueError("substitute.allowed must be boolean")
    if not value.allowed:
        if (
            any(
                x is not None
                for x in (
                    value.authority_ref,
                    value.profile_ref,
                    value.exact_subject_ref,
                    value.evidence_ref,
                    value.evidence_digest,
                    value.reproduction,
                )
            )
            or value.verdict is not GateVerdict.UNKNOWN
        ):
            raise ValueError("disallowed substitute cannot carry authority/evidence/verdict")
        return
    _text(value.authority_ref, "substitute.authority_ref")
    _text(value.profile_ref, "substitute.profile_ref")
    if value.verdict is GateVerdict.UNKNOWN:
        if any(
            x is not None
            for x in (value.exact_subject_ref, value.evidence_ref, value.evidence_digest, value.reproduction)
        ):
            raise ValueError("unused substitute cannot carry result evidence")
        return
    if _text(value.exact_subject_ref, "substitute.exact_subject_ref") != subject:
        raise ValueError("substitute evidence must bind the exact current subject")
    _text(value.evidence_ref, "substitute.evidence_ref")
    _digest(value.evidence_digest, "substitute.evidence_digest")
    r = value.reproduction
    if r is None:
        raise ValueError("used substitute requires a reproduction profile")
    _digest(r.original_workflow_digest, "reproduction.original_workflow_digest")
    if _text(r.exact_subject_ref, "reproduction.exact_subject_ref") != subject:
        raise ValueError("substitute reproduction must bind the exact gate subject")
    if (
        r.source_checkout != "clean_detached_or_equivalent"
        or type(r.inherited_workspace_state) is not bool
        or r.inherited_workspace_state
    ):
        raise ValueError("substitute reproduction must use clean isolated source state")
    _digest(r.environment_digest, "reproduction.environment_digest")
    _text(r.isolation_ref, "reproduction.isolation_ref")
    _text(r.command_ref, "reproduction.command_ref")
    _digest(r.report_digest, "reproduction.report_digest")


def _validate_catchup(value: CatchupObligation) -> None:
    if type(value.required) is not bool:
        raise ValueError("catchup.required must be boolean")
    if not value.required:
        if value.state is not CatchupState.NOT_REQUIRED or any(
            x is not None for x in (value.subject_ref, value.evidence_ref, value.evidence_digest)
        ):
            raise ValueError("non-required catch-up must be empty NOT_REQUIRED")
        return
    if value.state is CatchupState.NOT_REQUIRED:
        raise ValueError("required catch-up cannot be NOT_REQUIRED")
    if value.subject_ref is not None:
        _text(value.subject_ref, "catchup.subject_ref")
    if value.state is CatchupState.SATISFIED:
        _text(value.subject_ref, "catchup.subject_ref")
        _text(value.evidence_ref, "catchup.evidence_ref")
        _digest(value.evidence_digest, "catchup.evidence_digest")
    elif value.evidence_ref is not None or value.evidence_digest is not None:
        raise ValueError("pending/superseded catch-up cannot carry satisfaction evidence")


def build_external_gate_receipt(
    *,
    gate_id: str,
    provider: str,
    expected_subject_ref: str,
    policy_revision: str,
    observation: GateObservation,
    retry_mode: RetryMode,
    incident: GateIncident | None = None,
    next_eligible_at: str | None = None,
    substitute: SubstituteEvidence | None = None,
    catchup: CatchupObligation | None = None,
) -> dict[str, Any]:
    """Build a strict receipt without conflating availability, product result, or substitute evidence."""
    _text(gate_id, "gate_id", 256)
    _text(provider, "provider", 128)
    _text(expected_subject_ref, "expected_subject_ref")
    _text(policy_revision, "policy_revision")
    _validate_observation(observation)
    if incident is not None:
        _validate_incident(incident)
    if retry_mode is RetryMode.SUPPRESS_UNTIL_CHANGE and incident is None:
        raise ValueError("suppress_until_change requires an incident")
    if retry_mode is RetryMode.BOUNDED_BACKOFF and next_eligible_at is None:
        raise ValueError("bounded_backoff requires next_eligible_at")
    if next_eligible_at is not None:
        _time(next_eligible_at, "retry_policy.next_eligible_at")
    substitute = substitute or SubstituteEvidence(False)
    catchup = catchup or CatchupObligation(False, None, CatchupState.NOT_REQUIRED)
    _validate_substitute(substitute, expected_subject_ref)
    _validate_catchup(catchup)
    r = substitute.reproduction
    document: dict[str, Any] = {
        "schema_version": 1,
        "receipt_kind": "external_gate_deviation",
        "gate": {
            "gate_id": gate_id,
            "provider": provider,
            "expected_subject_ref": expected_subject_ref,
            "policy_revision": policy_revision,
        },
        "observation": {
            "state": observation.state.value,
            "product_verdict": observation.product_verdict.value,
            "repository_steps_executed": observation.repository_steps_executed,
            "failure_class": observation.failure_class.value,
            "observed_at": observation.observed_at,
            "evidence_ref": observation.evidence_ref,
            "evidence_digest": observation.evidence_digest,
        },
        "incident": None
        if incident is None
        else {
            "fingerprint": incident.fingerprint,
            "scope": incident.scope.value,
            "scope_ref": incident.scope_ref,
            "first_observed_at": incident.first_observed_at,
            "last_observed_at": incident.last_observed_at,
            "fresh_until": incident.fresh_until,
            "reopen_on": list(incident.reopen_on),
        },
        "retry_policy": {"mode": retry_mode.value, "next_eligible_at": next_eligible_at},
        "substitute": {
            "allowed": substitute.allowed,
            "authority_ref": substitute.authority_ref,
            "profile_ref": substitute.profile_ref,
            "exact_subject_ref": substitute.exact_subject_ref,
            "evidence_ref": substitute.evidence_ref,
            "evidence_digest": substitute.evidence_digest,
            "verdict": substitute.verdict.value,
            "reproduction": None
            if r is None
            else {
                "original_workflow_digest": r.original_workflow_digest,
                "exact_subject_ref": r.exact_subject_ref,
                "source_checkout": r.source_checkout,
                "environment_digest": r.environment_digest,
                "inherited_workspace_state": r.inherited_workspace_state,
                "isolation_ref": r.isolation_ref,
                "command_ref": r.command_ref,
                "report_digest": r.report_digest,
            },
        },
        "catchup": {
            "required": catchup.required,
            "subject_ref": catchup.subject_ref,
            "state": catchup.state.value,
            "evidence_ref": catchup.evidence_ref,
            "evidence_digest": catchup.evidence_digest,
        },
    }
    document["receipt_digest"] = _doc_digest(document)
    return document


def _rebuild(receipt: object) -> dict[str, Any]:
    root = _exact(receipt, _ROOT, "receipt")
    # Exact JSON type: ``1 == 1.0 == True`` in Python, so a plain comparison lets a
    # boolean or float masquerade as the integer schema version. The pinned schema
    # declares ``const: 1``; the canonical owner enforces the exact integer type.
    version = root["schema_version"]
    if type(version) is not int or version != 1 or root["receipt_kind"] != "external_gate_deviation":
        raise ValueError("unsupported receipt identity")
    g = _exact(root["gate"], _GATE, "gate")
    o = _exact(root["observation"], _OBS, "observation")
    rp = _exact(root["retry_policy"], _RETRY, "retry_policy")
    s = _exact(root["substitute"], _SUB, "substitute")
    c = _exact(root["catchup"], _CATCHUP, "catchup")
    incident = None
    if root["incident"] is not None:
        i = _exact(root["incident"], _INC, "incident")
        if not isinstance(i["reopen_on"], list):
            raise ValueError("incident.reopen_on must be a list")
        incident = GateIncident(
            i["fingerprint"],
            IncidentScope(i["scope"]),
            i["scope_ref"],
            i["first_observed_at"],
            i["last_observed_at"],
            i["fresh_until"],
            tuple(i["reopen_on"]),
        )
    reproduction = None
    if s["reproduction"] is not None:
        r = _exact(s["reproduction"], _REPRO, "reproduction")
        reproduction = SubstituteReproduction(**r)
    return build_external_gate_receipt(
        gate_id=g["gate_id"],
        provider=g["provider"],
        expected_subject_ref=g["expected_subject_ref"],
        policy_revision=g["policy_revision"],
        observation=GateObservation(
            GateExecutionState(o["state"]),
            GateVerdict(o["product_verdict"]),
            o["repository_steps_executed"],
            o["observed_at"],
            o["evidence_ref"],
            o["evidence_digest"],
            FailureClass(o["failure_class"]),
        ),
        retry_mode=RetryMode(rp["mode"]),
        incident=incident,
        next_eligible_at=rp["next_eligible_at"],
        substitute=SubstituteEvidence(
            s["allowed"],
            s["authority_ref"],
            s["profile_ref"],
            s["exact_subject_ref"],
            s["evidence_ref"],
            s["evidence_digest"],
            GateVerdict(s["verdict"]),
            reproduction,
        ),
        catchup=CatchupObligation(
            c["required"], c["subject_ref"], CatchupState(c["state"]), c["evidence_ref"], c["evidence_digest"]
        ),
    )


def verify_external_gate_receipt_integrity(receipt: object) -> bool:
    """Require both semantic validity and canonical digest equality."""
    try:
        return _rebuild(receipt) == receipt
    except (KeyError, TypeError, ValueError):
        return False


def _incident_current(document: dict[str, Any] | None, now: datetime, changed_signals: Iterable[str]) -> bool:
    if document is None or set(changed_signals).intersection(document["reopen_on"]):
        return False
    return document["fresh_until"] is None or now.astimezone(UTC) <= _time(
        document["fresh_until"], "incident.fresh_until"
    )


def derive_external_gate_decision(
    receipt: object, *, now: datetime, changed_signals: Iterable[str] = ()
) -> dict[str, str]:
    if not verify_external_gate_receipt_integrity(receipt):
        return {"gate_disposition": "UNKNOWN", "retry_disposition": "NOT_APPLICABLE", "catchup_disposition": "UNKNOWN"}
    assert isinstance(receipt, dict)
    o, sub = receipt["observation"], receipt["substitute"]
    if o["state"] == "EXECUTED":
        gate = "PASS_ORIGINAL" if o["product_verdict"] == "PASS" else "FAIL_ORIGINAL"
        retry = "NOT_APPLICABLE"
    else:
        gate = (
            f"{sub['verdict']}_SUBSTITUTE"
            if sub["allowed"] and sub["verdict"] in {"PASS", "FAIL"}
            else ("UNKNOWN" if o["state"] == "UNKNOWN" else "BLOCKED_UNAVAILABLE")
        )
        mode, next_at = receipt["retry_policy"]["mode"], receipt["retry_policy"]["next_eligible_at"]
        if mode == "operator_only":
            retry = "OPERATOR_ONLY"
        elif mode == "suppress_until_change" and _incident_current(receipt["incident"], now, changed_signals):
            retry = "SUPPRESSED"
        elif next_at is not None and now.astimezone(UTC) < _time(next_at, "retry_policy.next_eligible_at"):
            retry = "WAIT"
        else:
            retry = "ELIGIBLE"
    c = receipt["catchup"]
    return {
        "gate_disposition": gate,
        "retry_disposition": retry,
        "catchup_disposition": c["state"] if c["required"] else "NOT_REQUIRED",
    }


def satisfy_catchup(
    receipt: object,
    *,
    observed_subject_ref: str,
    provider: str,
    gate_id: str,
    provider_observation: GateObservation,
) -> dict[str, Any]:
    """Close catch-up only for exact original gate with executed PASS.

    The consumer must independently authenticate provider evidence and subject.
    This pure helper validates semantics; it cannot verify provider signatures.
    """
    if not verify_external_gate_receipt_integrity(receipt):
        raise ValueError("cannot satisfy catch-up on invalid receipt")
    assert isinstance(receipt, dict)
    c = receipt["catchup"]
    if not c["required"] or c["state"] != "PENDING" or c["subject_ref"] is None:
        raise ValueError("catch-up is not pending with an exact subject")
    if _text(observed_subject_ref, "observed_subject_ref") != c["subject_ref"]:
        raise ValueError("unrelated provider run cannot satisfy catch-up")
    if provider != receipt["gate"]["provider"] or gate_id != receipt["gate"]["gate_id"]:
        raise ValueError("catch-up must execute the original provider gate")
    _validate_observation(provider_observation)
    if _time(provider_observation.observed_at, "provider_observation.observed_at") <= _time(
        receipt["observation"]["observed_at"], "observation.observed_at"
    ):
        raise ValueError("catch-up evidence must postdate the deviation observation")
    if (
        provider_observation.state is not GateExecutionState.EXECUTED
        or provider_observation.product_verdict is not GateVerdict.PASS
    ):
        raise ValueError("catch-up requires executed original gate PASS")
    updated = json.loads(json.dumps(receipt))
    updated["catchup"] = {
        "required": True,
        "subject_ref": c["subject_ref"],
        "state": "SATISFIED",
        "evidence_ref": provider_observation.evidence_ref,
        "evidence_digest": provider_observation.evidence_digest,
    }
    updated.pop("receipt_digest")
    updated["receipt_digest"] = _doc_digest(updated)
    if not verify_external_gate_receipt_integrity(updated):
        raise AssertionError("constructed catch-up receipt is invalid")
    return updated
