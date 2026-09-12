#!/usr/bin/env python3
"""Generate an executable durable Steward overlay on the canonical MCP server baseline."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
MCP_TOOLS = ROOT / "skills" / "mcp-server-architect" / "tools"
CONTRACTS = ROOT / "contracts"
STEWARD_CONTRACTS = (
    "steward-profile.schema.json",
    "steward-job.schema.json",
    "external-operation-receipt.schema.json",
    "steward-evidence.schema.json",
    "steward-handoff.schema.json",
    "steward-lineage.schema.json",
    "steward-completion.schema.json",
    "upstream-capability.schema.json",
)
PROFILES = {
    "generic",
    "diagnostic",
    "verification",
    "research-evidence",
    "release-ops",
    "change-manager",
}


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load generator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _base_generator(language: str) -> ModuleType:
    if language == "python":
        return _load_module(MCP_TOOLS / "generate_python_server.py", "ai_skills_mcp_python_generator")
    if language == "dotnet":
        return _load_module(MCP_TOOLS / "generate_dotnet_server.py", "ai_skills_mcp_dotnet_generator")
    raise ValueError("language must be python or dotnet")


def _profile_document(steward_id: str, profile: str, *, durability_profile: str) -> dict[str, Any]:
    constrained_file = durability_profile == "constrained-file"
    return {
        "schema_version": 1,
        "steward": {"id": steward_id, "kind": profile, "contract_revision": 1},
        "authority": {
            "owns": ["durable-job-state"],
            "observes": ["seed-provider-result"],
            "may_mutate": [],
            "verifies": [],
            "parent_completion": "none",
            "never_claims": ["implicit-parent-completion"],
        },
        "subject_identity": {
            "required_dimensions": ["target"],
            "freshness_dimensions": ["target"],
        },
        "durability": {
            "profile": durability_profile,
            "crash_model": ["process-restart"],
            "transactional_store_required": not constrained_file,
            "lineage_fencing": True,
            "attempt_fencing": True,
        },
        "external_operations": {
            "receipt_before_stateful_dispatch": True,
            "ambiguous_delivery": "reconcile-before-retry",
        },
        "credentials": {
            "secret_source": "intentional-provider",
            "persist_secret": False,
            "fallback": {
                "enabled": False,
                "preserve_principal_scope": True,
                "preserve_target": True,
            },
        },
        "model": {"authority_ceiling": "advisory"},
        "completion": {
            "obligations": [
                {
                    "id": "provider-result",
                    "required": True,
                    "evidence_class": "provider-observation",
                }
            ],
            "handoff_digest": "sha256",
        },
        "observability": {"durable_timeline": True, "doctor": True},
    }


def _proof_recipe_document(steward_id: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "recipe_id": f"{steward_id}-seed-proof",
        "revision": 1,
        "criteria": [
            {
                "criterion_id": "provider-result",
                "subject_dimensions": ["target"],
                "required_authority": "observed",
                "freshness_seconds": 300,
                "approved_producers": ["seed-provider"],
                "probes": [],
                "sufficiency": "all-required",
            }
        ],
        "completion": {
            "unresolved_required_criterion": "blocked",
            "advisory_model_findings_require_reproduction": True,
        },
    }


_PYTHON_RUNTIME = r'''"""Durable Steward seed with scheduler/recovery, evidence resolution and completion gating."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import uuid
from datetime import UTC, datetime, timedelta
from importlib.resources import files
from pathlib import Path
from typing import Any

_AUTHORITY_RANK = {"advisory": 0, "observed": 1, "verified": 2, "independent": 3}
_TERMINAL = {"completed", "completed-with-gaps", "failed", "cancelled", "superseded"}


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def compute_handoff_digest(handoff: dict[str, Any]) -> str:
    payload = {key: value for key, value in handoff.items() if key != "digest"}
    return _digest(payload)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FakeClock:
    def __init__(self, initial: datetime | None = None) -> None:
        self._current = initial or datetime(2026, 1, 1, tzinfo=UTC)

    def now(self) -> datetime:
        return self._current

    def advance(self, seconds: float) -> None:
        self._current += timedelta(seconds=seconds)


class FaultInjector:
    def __init__(self, enabled: set[str] | None = None) -> None:
        self._enabled = set(enabled or ())

    @classmethod
    def from_environment(cls) -> "FaultInjector":
        raw = os.environ.get("STEWARD_FAULTS", "")
        return cls({item.strip() for item in raw.split(",") if item.strip()})

    def trip(self, point: str) -> bool:
        if point not in self._enabled:
            return False
        self._enabled.remove(point)
        return True


class FakeProvider:
    """Deterministic stateful provider used by the seed and recovery tests."""

    producer_id = "seed-provider"

    def dispatch(self, operation_id: str, subject: dict[str, Any]) -> str:
        del subject
        return f"remote:{operation_id}"

    def reconcile(self, operation_id: str, subject: dict[str, Any]) -> str:
        del subject
        return f"remote:{operation_id}"

    def poll(self, remote_handle: str, subject: dict[str, Any]) -> dict[str, Any]:
        return {
            "state": "completed",
            "remoteHandle": remote_handle,
            "subject": subject,
            "result": "seed-provider-complete",
        }


class StewardStore:
    def __init__(self, path: Path, clock: SystemClock | FakeClock) -> None:
        self.path = path
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS steward_jobs (
                    job_id TEXT PRIMARY KEY,
                    lineage_id TEXT NOT NULL,
                    generation INTEGER NOT NULL,
                    attempt_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    subject_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    heartbeat_at TEXT NOT NULL,
                    progress_at TEXT NOT NULL,
                    deadline_at TEXT NOT NULL,
                    cancellation TEXT NOT NULL DEFAULT 'none'
                );
                CREATE TABLE IF NOT EXISTS steward_lineages (
                    lineage_id TEXT PRIMARY KEY,
                    current_generation INTEGER NOT NULL,
                    current_job_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    subject_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS external_operations (
                    operation_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    lineage_id TEXT NOT NULL,
                    generation INTEGER NOT NULL,
                    attempt_id TEXT NOT NULL,
                    request_digest TEXT NOT NULL,
                    state TEXT NOT NULL,
                    delivery TEXT NOT NULL,
                    retry_disposition TEXT NOT NULL,
                    credential_slot_id TEXT NOT NULL,
                    remote_handle TEXT NULL,
                    created_at TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES steward_jobs(job_id)
                );
                CREATE TABLE IF NOT EXISTS steward_evidence (
                    evidence_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    lineage_id TEXT NOT NULL,
                    generation INTEGER NOT NULL,
                    subject_json TEXT NOT NULL,
                    criterion_id TEXT NOT NULL,
                    evidence_class TEXT NOT NULL,
                    authority_class TEXT NOT NULL,
                    producer_id TEXT NOT NULL,
                    proof_recipe_id TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    expires_at TEXT NULL,
                    payload_digest TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES steward_jobs(job_id)
                );
                CREATE TABLE IF NOT EXISTS completion_evaluations (
                    evaluation_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    evaluated_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES steward_jobs(job_id)
                );
                CREATE TABLE IF NOT EXISTS steward_handoffs (
                    handoff_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    digest TEXT NOT NULL,
                    sealed_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES steward_jobs(job_id)
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    job_id TEXT NULL,
                    event_type TEXT NOT NULL,
                    at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                """
            )

    def _audit_tx(self, db: sqlite3.Connection, job_id: str | None, event_type: str, payload: dict[str, Any]) -> None:
        db.execute(
            "INSERT INTO audit_events(event_id, job_id, event_type, at, payload_json) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), job_id, event_type, _iso(self.clock.now()), _canonical_json(payload)),
        )

    def admit(self, subject: dict[str, Any], idempotency_key: str) -> tuple[str, bool]:
        if not idempotency_key or len(idempotency_key) > 200:
            raise ValueError("idempotency_key must be 1-200 characters")
        normalized = {
            "type": str(subject.get("type") or "target"),
            "id": str(subject.get("id") or ""),
            "revision": subject.get("revision"),
        }
        if not normalized["id"]:
            raise ValueError("subject.id is required")
        subject_json = _canonical_json(normalized)
        lineage_id = "lineage-" + hashlib.sha256(subject_json.encode("utf-8")).hexdigest()[:24]
        now = _iso(self.clock.now())
        deadline = _iso(self.clock.now() + timedelta(minutes=10))
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            duplicate = db.execute(
                "SELECT job_id, subject_json FROM steward_jobs WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            if duplicate is not None:
                if str(duplicate["subject_json"]) != subject_json:
                    raise RuntimeError("idempotency key reused for a different subject")
                return str(duplicate["job_id"]), True
            lineage = db.execute(
                "SELECT current_generation FROM steward_lineages WHERE lineage_id=?",
                (lineage_id,),
            ).fetchone()
            generation = 1 if lineage is None else int(lineage["current_generation"]) + 1
            job_id = "job-" + uuid.uuid4().hex
            attempt_id = "attempt-" + uuid.uuid4().hex
            db.execute(
                "INSERT INTO steward_jobs VALUES (?, ?, ?, ?, 0, ?, 'queued', 'admitted', ?, ?, ?, ?, ?, ?, 'none')",
                (job_id, lineage_id, generation, attempt_id, subject_json, idempotency_key, now, now, now, now, deadline),
            )
            db.execute(
                "INSERT INTO steward_lineages VALUES (?, ?, ?, 0, ?, ?) "
                "ON CONFLICT(lineage_id) DO UPDATE SET "
                "current_generation=excluded.current_generation, current_job_id=excluded.current_job_id, "
                "version=steward_lineages.version + 1, subject_json=excluded.subject_json, updated_at=excluded.updated_at",
                (lineage_id, generation, job_id, subject_json, now),
            )
            self._audit_tx(db, job_id, "job.admitted", {"generation": generation, "subject": normalized})
            return job_id, False

    def _job_row(self, db: sqlite3.Connection, job_id: str) -> sqlite3.Row:
        row = db.execute("SELECT * FROM steward_jobs WHERE job_id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return row

    def job(self, job_id: str) -> dict[str, Any]:
        with self._connect() as db:
            return self._job_from_row(self._job_row(db, job_id))

    def _refs(self, job_id: str) -> dict[str, list[str]]:
        with self._connect() as db:
            operations = [str(row[0]) for row in db.execute(
                "SELECT operation_id FROM external_operations WHERE job_id=? ORDER BY operation_id", (job_id,)
            )]
            evidence = [str(row[0]) for row in db.execute(
                "SELECT evidence_id FROM steward_evidence WHERE job_id=? ORDER BY evidence_id", (job_id,)
            )]
        return {"operations": operations, "evidence": evidence}

    def _job_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        refs = self._refs(str(row["job_id"]))
        return {
            "schema_version": 1,
            "jobId": str(row["job_id"]),
            "lineageId": str(row["lineage_id"]),
            "generation": int(row["generation"]),
            "attemptId": str(row["attempt_id"]),
            "version": int(row["version"]),
            "subject": json.loads(str(row["subject_json"])),
            "status": str(row["status"]),
            "stage": str(row["stage"]),
            "createdAt": str(row["created_at"]),
            "updatedAt": str(row["updated_at"]),
            "heartbeatAt": str(row["heartbeat_at"]),
            "progressAt": str(row["progress_at"]),
            "deadlineAt": str(row["deadline_at"]),
            "cancellation": str(row["cancellation"]),
            "externalOperationRefs": refs["operations"],
            "evidenceRefs": refs["evidence"],
            "artifactRefs": [],
        }

    def due_job_id(self) -> str | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT job_id FROM steward_jobs WHERE status NOT IN "
                "('completed','completed-with-gaps','failed','cancelled','superseded','blocked') "
                "ORDER BY created_at, job_id LIMIT 1"
            ).fetchone()
            return None if row is None else str(row[0])

    def request_cancel(self, job_id: str) -> dict[str, Any]:
        now = _iso(self.clock.now())
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._job_row(db, job_id)
            if str(row["status"]) in _TERMINAL:
                return self._job_from_row(row)
            db.execute(
                "UPDATE steward_jobs SET cancellation='requested', updated_at=?, version=version+1 WHERE job_id=?",
                (now, job_id),
            )
            self._audit_tx(db, job_id, "job.cancel-requested", {})
        return self.job(job_id)

    def mark_cancelled(self, job_id: str) -> dict[str, Any]:
        now = _iso(self.clock.now())
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._job_row(db, job_id)
            if str(row["status"]) in _TERMINAL:
                return self._job_from_row(row)
            db.execute(
                "UPDATE steward_jobs SET status='cancelled', stage='cancelled', cancellation='completed', "
                "updated_at=?, heartbeat_at=?, progress_at=?, version=version+1 WHERE job_id=?",
                (now, now, now, job_id),
            )
            self._audit_tx(db, job_id, "job.cancelled", {})
        return self.job(job_id)

    def reserve_external(self, job_id: str) -> dict[str, Any]:
        now = _iso(self.clock.now())
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._job_row(db, job_id)
            existing = db.execute(
                "SELECT * FROM external_operations WHERE job_id=? ORDER BY created_at LIMIT 1", (job_id,)
            ).fetchone()
            if existing is not None:
                return dict(existing)
            operation_id = "op-" + uuid.uuid4().hex
            subject = json.loads(str(row["subject_json"]))
            request_digest = _digest({"capability": "seed-provider.start", "subject": subject})
            db.execute(
                "INSERT INTO external_operations VALUES (?, ?, ?, ?, ?, ?, 'reserved', 'not-delivered', "
                "'forbidden', 'seed-primary', NULL, ?, ?)",
                (
                    operation_id,
                    job_id,
                    str(row["lineage_id"]),
                    int(row["generation"]),
                    str(row["attempt_id"]),
                    request_digest,
                    now,
                    now,
                ),
            )
            db.execute(
                "UPDATE steward_jobs SET status='running', stage='external-reserved', updated_at=?, heartbeat_at=?, "
                "progress_at=?, version=version+1 WHERE job_id=?",
                (now, now, now, job_id),
            )
            self._audit_tx(db, job_id, "external.reserved", {"operationId": operation_id, "requestDigest": request_digest})
            return dict(db.execute("SELECT * FROM external_operations WHERE operation_id=?", (operation_id,)).fetchone())

    def operation_for_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM external_operations WHERE job_id=? ORDER BY created_at LIMIT 1", (job_id,)
            ).fetchone()
            return None if row is None else dict(row)

    def mark_delivery_unknown(self, operation_id: str) -> None:
        now = _iso(self.clock.now())
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT job_id FROM external_operations WHERE operation_id=?", (operation_id,)).fetchone()
            if row is None:
                raise KeyError(operation_id)
            job_id = str(row["job_id"])
            db.execute(
                "UPDATE external_operations SET state='dispatched', delivery='delivery-unknown', "
                "retry_disposition='reconcile-first', observed_at=? WHERE operation_id=?",
                (now, operation_id),
            )
            db.execute(
                "UPDATE steward_jobs SET status='reconciling', stage='delivery-unknown', updated_at=?, "
                "heartbeat_at=?, version=version+1 WHERE job_id=?",
                (now, now, job_id),
            )
            self._audit_tx(db, job_id, "external.delivery-unknown", {"operationId": operation_id})

    def mark_delivered(self, operation_id: str, remote_handle: str) -> None:
        now = _iso(self.clock.now())
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT job_id FROM external_operations WHERE operation_id=?", (operation_id,)).fetchone()
            if row is None:
                raise KeyError(operation_id)
            job_id = str(row["job_id"])
            db.execute(
                "UPDATE external_operations SET state='accepted', delivery='delivered', retry_disposition='forbidden', "
                "remote_handle=?, observed_at=? WHERE operation_id=?",
                (remote_handle, now, operation_id),
            )
            db.execute(
                "UPDATE steward_jobs SET status='waiting-external', stage='remote-accepted', updated_at=?, "
                "heartbeat_at=?, progress_at=?, version=version+1 WHERE job_id=?",
                (now, now, now, job_id),
            )
            self._audit_tx(db, job_id, "external.accepted", {"operationId": operation_id, "remoteHandle": remote_handle})

    def persist_evidence(
        self,
        job_id: str,
        *,
        criterion_id: str,
        evidence_class: str,
        authority_class: str,
        producer_id: str,
        proof_recipe_id: str,
        payload: dict[str, Any],
        freshness_seconds: int,
    ) -> str:
        now = self.clock.now()
        evidence_id = "evidence-" + uuid.uuid4().hex
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._job_row(db, job_id)
            current = db.execute(
                "SELECT current_generation, current_job_id, subject_json FROM steward_lineages WHERE lineage_id=?",
                (str(row["lineage_id"]),),
            ).fetchone()
            if current is None or int(current["current_generation"]) != int(row["generation"]) or str(current["current_job_id"]) != job_id:
                raise RuntimeError("stale lineage evidence publication")
            subject_json = str(row["subject_json"])
            expires_at = _iso(now + timedelta(seconds=freshness_seconds))
            db.execute(
                "INSERT INTO steward_evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    evidence_id,
                    job_id,
                    str(row["lineage_id"]),
                    int(row["generation"]),
                    subject_json,
                    criterion_id,
                    evidence_class,
                    authority_class,
                    producer_id,
                    proof_recipe_id,
                    _iso(now),
                    expires_at,
                    _digest(payload),
                ),
            )
            db.execute(
                "UPDATE steward_jobs SET status='finalizing', stage='evidence-persisted', updated_at=?, heartbeat_at=?, "
                "progress_at=?, version=version+1 WHERE job_id=?",
                (_iso(now), _iso(now), _iso(now), job_id),
            )
            self._audit_tx(db, job_id, "evidence.persisted", {"evidenceId": evidence_id, "criterionId": criterion_id})
        return evidence_id

    def _completion_gate_tx(
        self,
        db: sqlite3.Connection,
        row: sqlite3.Row,
        profile: dict[str, Any],
        proof_recipe: dict[str, Any],
    ) -> dict[str, Any]:
        job_id = str(row["job_id"])
        lineage_id = str(row["lineage_id"])
        generation = int(row["generation"])
        subject = json.loads(str(row["subject_json"]))
        current = db.execute(
            "SELECT current_generation, current_job_id, subject_json FROM steward_lineages WHERE lineage_id=?",
            (lineage_id,),
        ).fetchone()
        if current is None or int(current["current_generation"]) != generation or str(current["current_job_id"]) != job_id:
            raise RuntimeError("completion blocked by stale lineage")
        if json.loads(str(current["subject_json"])) != subject:
            raise RuntimeError("completion blocked by stale subject identity")
        ambiguous = [str(item[0]) for item in db.execute(
            "SELECT operation_id FROM external_operations WHERE job_id=? AND delivery='delivery-unknown' ORDER BY operation_id",
            (job_id,),
        )]
        recipe_id = f"{proof_recipe['recipe_id']}@{proof_recipe['revision']}"
        criteria = {item["criterion_id"]: item for item in proof_recipe.get("criteria", [])}
        evidence_rows = list(db.execute("SELECT * FROM steward_evidence WHERE job_id=?", (job_id,)))
        obligations: list[dict[str, Any]] = []
        required_unsatisfied = False
        now = self.clock.now()
        for obligation in profile["completion"]["obligations"]:
            criterion_id = str(obligation["id"])
            criterion = criteria.get(criterion_id)
            matched: list[str] = []
            if criterion is not None:
                required_rank = _AUTHORITY_RANK[str(criterion["required_authority"])]
                approved = set(criterion.get("approved_producers", []))
                max_age = int(criterion["freshness_seconds"])
                for evidence in evidence_rows:
                    if str(evidence["criterion_id"]) != criterion_id:
                        continue
                    if str(evidence["evidence_class"]) != str(obligation["evidence_class"]):
                        continue
                    if str(evidence["proof_recipe_id"]) != recipe_id:
                        continue
                    if approved and str(evidence["producer_id"]) not in approved:
                        continue
                    if _AUTHORITY_RANK.get(str(evidence["authority_class"]), -1) < required_rank:
                        continue
                    if int(evidence["generation"]) != generation or str(evidence["lineage_id"]) != lineage_id:
                        continue
                    if json.loads(str(evidence["subject_json"])) != subject:
                        continue
                    observed = _parse(str(evidence["observed_at"]))
                    if observed > now or (now - observed).total_seconds() > max_age:
                        continue
                    expires = evidence["expires_at"]
                    if expires is not None and _parse(str(expires)) < now:
                        continue
                    matched.append(str(evidence["evidence_id"]))
            state = "satisfied" if matched else "unsatisfied"
            if bool(obligation["required"]) and state != "satisfied":
                required_unsatisfied = True
            obligations.append({"id": criterion_id, "state": state, "evidenceRefs": sorted(matched)})
        disposition = "eligible" if not required_unsatisfied and not ambiguous else "blocked"
        return {
            "schema_version": 1,
            "evaluationId": "completion-" + uuid.uuid4().hex,
            "jobId": job_id,
            "lineageId": lineage_id,
            "generation": generation,
            "subject": subject,
            "decisionIdentity": {
                "generation": generation,
                "profileRevision": int(profile["steward"]["contract_revision"]),
                "proofRecipeRevision": int(proof_recipe["revision"]),
                "subjectRevision": subject.get("revision") or "none",
            },
            "disposition": disposition,
            "obligations": obligations,
            "ambiguousOperationRefs": ambiguous,
            "evaluatedAt": _iso(now),
        }

    def finalize_with_gate(
        self,
        job_id: str,
        profile: dict[str, Any],
        proof_recipe: dict[str, Any],
        *,
        outcome: str,
    ) -> dict[str, Any]:
        now = _iso(self.clock.now())
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._job_row(db, job_id)
            if str(row["status"]) in _TERMINAL:
                existing = db.execute("SELECT payload_json FROM steward_handoffs WHERE job_id=?", (job_id,)).fetchone()
                if existing is None:
                    raise RuntimeError("terminal job is missing handoff")
                return json.loads(str(existing["payload_json"]))
            evaluation = self._completion_gate_tx(db, row, profile, proof_recipe)
            if evaluation["disposition"] != "eligible":
                self._audit_tx(db, job_id, "completion.blocked", {"evaluation": evaluation})
                raise RuntimeError("completion gate blocked terminal publication")
            evidence_refs = sorted({ref for obligation in evaluation["obligations"] for ref in obligation["evidenceRefs"]})
            operation_refs = [str(item[0]) for item in db.execute(
                "SELECT operation_id FROM external_operations WHERE job_id=? ORDER BY operation_id", (job_id,)
            )]
            handoff = {
                "schema_version": 1,
                "handoffId": "handoff-" + uuid.uuid4().hex,
                "jobId": job_id,
                "lineageId": str(row["lineage_id"]),
                "generation": int(row["generation"]),
                "subject": json.loads(str(row["subject_json"])),
                "status": "completed",
                "actionable": True,
                "outcome": outcome,
                "evidenceRefs": evidence_refs,
                "artifactRefs": [],
                "externalOperationRefs": operation_refs,
                "gaps": [],
                "sealedAt": now,
            }
            handoff["digest"] = compute_handoff_digest(handoff)
            db.execute(
                "INSERT INTO completion_evaluations VALUES (?, ?, ?, ?)",
                (evaluation["evaluationId"], job_id, _canonical_json(evaluation), now),
            )
            db.execute(
                "INSERT INTO steward_handoffs VALUES (?, ?, ?, ?, ?)",
                (handoff["handoffId"], job_id, _canonical_json(handoff), handoff["digest"], now),
            )
            db.execute(
                "UPDATE steward_jobs SET status='completed', stage='completed', updated_at=?, heartbeat_at=?, progress_at=?, "
                "version=version+1 WHERE job_id=?",
                (now, now, now, job_id),
            )
            self._audit_tx(db, job_id, "handoff.sealed", {"handoffId": handoff["handoffId"], "digest": handoff["digest"]})
            return handoff

    def handoff(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT payload_json FROM steward_handoffs WHERE job_id=?", (job_id,)).fetchone()
            return None if row is None else json.loads(str(row["payload_json"]))

    def completion(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT payload_json FROM completion_evaluations WHERE job_id=?", (job_id,)).fetchone()
            return None if row is None else json.loads(str(row["payload_json"]))

    def evidence(self, job_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = list(db.execute(
                "SELECT * FROM steward_evidence WHERE job_id=? ORDER BY observed_at, evidence_id", (job_id,)
            ))
        return [
            {
                "schema_version": 1,
                "evidenceId": str(row["evidence_id"]),
                "jobId": str(row["job_id"]),
                "lineageId": str(row["lineage_id"]),
                "generation": int(row["generation"]),
                "subject": json.loads(str(row["subject_json"])),
                "criterionId": str(row["criterion_id"]),
                "evidenceClass": str(row["evidence_class"]),
                "authorityClass": str(row["authority_class"]),
                "producerId": str(row["producer_id"]),
                "proofRecipeId": str(row["proof_recipe_id"]),
                "observedAt": str(row["observed_at"]),
                "expiresAt": row["expires_at"],
                "payloadDigest": str(row["payload_digest"]),
            }
            for row in rows
        ]

    def operations(self, job_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = list(db.execute(
                "SELECT * FROM external_operations WHERE job_id=? ORDER BY created_at, operation_id", (job_id,)
            ))
        return [dict(row) for row in rows]

    def timeline(self, job_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 200))
        with self._connect() as db:
            if job_id is None:
                rows = list(db.execute("SELECT * FROM audit_events ORDER BY sequence DESC LIMIT ?", (limit,)))
            else:
                rows = list(db.execute(
                    "SELECT * FROM audit_events WHERE job_id=? ORDER BY sequence DESC LIMIT ?", (job_id, limit)
                ))
        return [
            {
                "sequence": int(row["sequence"]),
                "eventId": str(row["event_id"]),
                "jobId": row["job_id"],
                "type": str(row["event_type"]),
                "at": str(row["at"]),
                "payload": json.loads(str(row["payload_json"])),
            }
            for row in reversed(rows)
        ]

    def doctor(self, job_id: str | None = None) -> dict[str, Any]:
        with self._connect() as db:
            statuses = {str(row[0]): int(row[1]) for row in db.execute(
                "SELECT status, COUNT(*) FROM steward_jobs GROUP BY status ORDER BY status"
            )}
            ambiguities = int(db.execute(
                "SELECT COUNT(*) FROM external_operations WHERE delivery='delivery-unknown'"
            ).fetchone()[0])
        result: dict[str, Any] = {
            "statusCounts": statuses,
            "deliveryUnknown": ambiguities,
            "recoverableJobs": sum(count for status, count in statuses.items() if status not in _TERMINAL | {"blocked"}),
            "timeline": self.timeline(job_id, 50),
        }
        if job_id is not None:
            result["job"] = self.job(job_id)
        return result


class StewardRuntime:
    def __init__(
        self,
        store: StewardStore,
        profile: dict[str, Any],
        proof_recipe: dict[str, Any],
        provider: FakeProvider | None = None,
        faults: FaultInjector | None = None,
    ) -> None:
        self.store = store
        self.profile = profile
        self.proof_recipe = proof_recipe
        self.provider = provider or FakeProvider()
        self.faults = faults or FaultInjector()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def submit(self, subject_id: str, subject_revision: str | None, idempotency_key: str) -> dict[str, Any]:
        job_id, duplicate = self.store.admit(
            {"type": "target", "id": subject_id, "revision": subject_revision},
            idempotency_key,
        )
        return {"jobId": job_id, "duplicate": duplicate, "status": self.store.job(job_id)["status"]}

    def status(self, job_id: str) -> dict[str, Any]:
        job = self.store.job(job_id)
        return {
            "jobId": job["jobId"],
            "status": job["status"],
            "stage": job["stage"],
            "generation": job["generation"],
            "progressAt": job["progressAt"],
            "cancellation": job["cancellation"],
        }

    def get(self, job_id: str) -> dict[str, Any]:
        return {
            "job": self.store.job(job_id),
            "operations": self.store.operations(job_id),
            "evidence": self.store.evidence(job_id),
            "completion": self.store.completion(job_id),
            "handoff": self.store.handoff(job_id),
            "timeline": self.store.timeline(job_id, 100),
        }

    def cancel(self, job_id: str) -> dict[str, Any]:
        return self.store.request_cancel(job_id)

    def doctor(self, job_id: str | None = None) -> dict[str, Any]:
        return self.store.doctor(job_id)

    def run_once(self) -> bool:
        job_id = self.store.due_job_id()
        if job_id is None:
            return False
        job = self.store.job(job_id)
        if job["cancellation"] == "requested":
            self.store.mark_cancelled(job_id)
            return True
        operation = self.store.operation_for_job(job_id)
        if operation is None:
            operation = self.store.reserve_external(job_id)
            if self.faults.trip("after-reservation"):
                return True
        if operation["delivery"] == "not-delivered":
            subject = self.store.job(job_id)["subject"]
            remote_handle = self.provider.dispatch(str(operation["operation_id"]), subject)
            if self.faults.trip("after-dispatch") or self.faults.trip("before-handle-persist"):
                self.store.mark_delivery_unknown(str(operation["operation_id"]))
                return True
            self.store.mark_delivered(str(operation["operation_id"]), remote_handle)
            return True
        if operation["delivery"] == "delivery-unknown":
            subject = self.store.job(job_id)["subject"]
            handle = self.provider.reconcile(str(operation["operation_id"]), subject)
            self.store.mark_delivered(str(operation["operation_id"]), handle)
            return True
        operation = self.store.operation_for_job(job_id)
        if operation is None or not operation.get("remote_handle"):
            return True
        subject = self.store.job(job_id)["subject"]
        result = self.provider.poll(str(operation["remote_handle"]), subject)
        if result.get("state") != "completed":
            return True
        if not self.store.evidence(job_id):
            if self.faults.trip("before-result-persist"):
                return True
            criterion = self.proof_recipe["criteria"][0]
            recipe_id = f"{self.proof_recipe['recipe_id']}@{self.proof_recipe['revision']}"
            self.store.persist_evidence(
                job_id,
                criterion_id=str(criterion["criterion_id"]),
                evidence_class=str(self.profile["completion"]["obligations"][0]["evidence_class"]),
                authority_class=str(criterion["required_authority"]),
                producer_id=self.provider.producer_id,
                proof_recipe_id=recipe_id,
                payload=result,
                freshness_seconds=int(criterion["freshness_seconds"]),
            )
            return True
        if self.faults.trip("before-terminal-publication"):
            return True
        self.store.finalize_with_gate(job_id, self.profile, self.proof_recipe, outcome="seed-complete")
        return True

    def recover_until_idle(self, max_steps: int = 32) -> int:
        steps = 0
        while steps < max_steps and self.run_once():
            steps += 1
            if self.store.due_job_id() is None:
                break
        return steps

    def start_background(self, interval_seconds: float = 0.05) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()

        def worker() -> None:
            while not self._stop.is_set():
                try:
                    progressed = self.run_once()
                except Exception:
                    progressed = False
                if not progressed:
                    self._stop.wait(interval_seconds)

        self._thread = threading.Thread(target=worker, name="steward-recovery", daemon=True)
        self._thread.start()

    def stop_background(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None


def _load_packaged_json(name: str) -> dict[str, Any]:
    return json.loads(files(__package__).joinpath(name).read_text(encoding="utf-8"))


_DEFAULT_RUNTIME: StewardRuntime | None = None
_DEFAULT_LOCK = threading.Lock()


def default_runtime() -> StewardRuntime:
    global _DEFAULT_RUNTIME
    with _DEFAULT_LOCK:
        if _DEFAULT_RUNTIME is None:
            path = Path(os.environ.get("STEWARD_STATE_PATH", ".steward/steward.db"))
            clock = SystemClock()
            _DEFAULT_RUNTIME = StewardRuntime(
                StewardStore(path, clock),
                _load_packaged_json("steward_profile.json"),
                _load_packaged_json("steward_proof_recipe.json"),
                faults=FaultInjector.from_environment(),
            )
        return _DEFAULT_RUNTIME
'''

_PYTHON_KERNEL = r'''"""Application-owned invocation policy around the durable Steward workflow."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from .manifest import MANIFESTS
from .security import current_principal
from .steward_runtime import default_runtime

_MAX_CONCURRENCY_KEYS = 1024


@dataclass
class _GateEntry:
    limit: int
    queue_limit: int
    active: int = 0
    waiting: int = 0


class _KeyedOperationGate:
    def __init__(self, maximum_keys: int) -> None:
        self._maximum_keys = maximum_keys
        self._condition = threading.Condition(threading.RLock())
        self._entries: dict[str, _GateEntry] = {}

    @contextmanager
    def slot(self, key: str, limit: int, queue_limit: int) -> Iterator[None]:
        with self._condition:
            entry = self._entries.get(key)
            if entry is None:
                if len(self._entries) >= self._maximum_keys:
                    raise RuntimeError("CONCURRENCY_GATE_CAPACITY")
                entry = _GateEntry(limit, queue_limit)
                self._entries[key] = entry
            if entry.limit != limit or entry.queue_limit != queue_limit:
                raise RuntimeError("CONCURRENCY_POLICY_MISMATCH")
            if entry.active >= entry.limit:
                if entry.waiting >= entry.queue_limit:
                    raise RuntimeError("CONCURRENCY_QUEUE_FULL")
                entry.waiting += 1
                try:
                    while entry.active >= entry.limit:
                        self._condition.wait()
                finally:
                    entry.waiting -= 1
            entry.active += 1
        try:
            yield
        finally:
            with self._condition:
                entry.active -= 1
                if entry.active == 0 and entry.waiting == 0:
                    self._entries.pop(key, None)
                self._condition.notify_all()


_GATE = _KeyedOperationGate(_MAX_CONCURRENCY_KEYS)


def _bounded(capability_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result["_meta"] = {"capability_id": capability_id, "principal": current_principal()}
    maximum = int(MANIFESTS[capability_id]["max_response_bytes"])
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(encoded) > maximum:
        raise RuntimeError(f"final response exceeds {maximum} bytes")
    return result


@contextmanager
def _slots(capability_id: str, target: str | None) -> Iterator[None]:
    manifest = MANIFESTS[capability_id]
    policy = manifest.get("concurrency")
    if not isinstance(policy, Mapping):
        raise RuntimeError("capability manifest concurrency policy is missing")
    scope = str(policy["scope"])
    principal = current_principal()
    if scope == "principal":
        key = f"{capability_id}:principal:{principal}"
    elif scope == "principal-target":
        if not target:
            raise RuntimeError("principal-target concurrency requires target")
        key = f"{capability_id}:principal:{principal}:target:{target}"
    elif scope in {"global", "capability"}:
        key = f"{capability_id}:capability"
    else:
        raise RuntimeError(f"unsupported generated Steward concurrency scope: {scope}")
    with _GATE.slot(key, int(policy["limit"]), int(policy["queue_limit"])):
        yield


def describe_capabilities() -> dict[str, Any]:
    with _slots("describe_capabilities", None):
        values = [dict(MANIFESTS[key]) for key in sorted(MANIFESTS)]
        return _bounded("describe_capabilities", {"capabilities": values, "count": len(values)})


def steward_submit(subject_id: str, subject_revision: str | None, idempotency_key: str) -> dict[str, Any]:
    if not subject_id or len(subject_id) > 200 or not idempotency_key or len(idempotency_key) > 200:
        raise ValueError("subject_id and idempotency_key must be 1-200 characters")
    with _slots("steward_submit", subject_id):
        return _bounded("steward_submit", default_runtime().submit(subject_id, subject_revision, idempotency_key))


def steward_status(job_id: str) -> dict[str, Any]:
    with _slots("steward_status", job_id):
        return _bounded("steward_status", default_runtime().status(job_id))


def steward_get(job_id: str) -> dict[str, Any]:
    with _slots("steward_get", job_id):
        return _bounded("steward_get", default_runtime().get(job_id))


def steward_cancel(job_id: str) -> dict[str, Any]:
    with _slots("steward_cancel", job_id):
        return _bounded("steward_cancel", default_runtime().cancel(job_id))


def steward_doctor(job_id: str = "") -> dict[str, Any]:
    with _slots("steward_doctor", job_id or "global"):
        return _bounded("steward_doctor", default_runtime().doctor(job_id or None))
'''

_PYTHON_SERVER = r'''"""Official MCP SDK adapter around the durable Steward semantic kernel."""

from __future__ import annotations

import os

import uvicorn
from mcp.server import MCPServer
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .kernel import describe_capabilities as invoke_describe_capabilities
from .kernel import steward_cancel as invoke_steward_cancel
from .kernel import steward_doctor as invoke_steward_doctor
from .kernel import steward_get as invoke_steward_get
from .kernel import steward_status as invoke_steward_status
from .kernel import steward_submit as invoke_steward_submit
from .security import BearerAuthMiddleware, require_http_token
from .steward_runtime import default_runtime

mcp = MCPServer("__SERVER_NAME__")


@mcp.tool()
def describe_capabilities() -> dict[str, object]:
    """Return the validated application-owned Steward capability catalog."""
    return invoke_describe_capabilities()


@mcp.tool()
def steward_submit(subject_id: str, idempotency_key: str, subject_revision: str | None = None) -> dict[str, object]:
    """Durably admit one Steward job and return before background work completes."""
    return invoke_steward_submit(subject_id, subject_revision, idempotency_key)


@mcp.tool()
def steward_status(job_id: str) -> dict[str, object]:
    """Return bounded operational status for one durable Steward job."""
    return invoke_steward_status(job_id)


@mcp.tool()
def steward_get(job_id: str) -> dict[str, object]:
    """Return bounded evidence, completion evaluation and handoff for one job."""
    return invoke_steward_get(job_id)


@mcp.tool()
def steward_cancel(job_id: str) -> dict[str, object]:
    """Persist cancellation intent for one non-terminal Steward job."""
    return invoke_steward_cancel(job_id)


@mcp.tool()
def steward_doctor(job_id: str = "") -> dict[str, object]:
    """Return bounded durable diagnostics and recovery state."""
    return invoke_steward_doctor(job_id)


@mcp.custom_route("/health/live", methods=["GET"])
async def health_live(request: Request) -> Response:
    del request
    return JSONResponse({"status": "live"})


@mcp.custom_route("/health/ready", methods=["GET"])
async def health_ready(request: Request) -> Response:
    del request
    return JSONResponse({"status": "ready", "doctor": default_runtime().doctor()})


def build_http_app() -> BearerAuthMiddleware:
    app = mcp.streamable_http_app(
        host="127.0.0.1",
        stateless_http=True,
        json_response=True,
        max_request_body_size=1024 * 1024,
    )
    return BearerAuthMiddleware(app, require_http_token())


def _http_host() -> str:
    host = os.environ.get("MCP_HTTP_HOST", "127.0.0.1")
    if host in {"127.0.0.1", "::1", "localhost"}:
        return host
    if host == "0.0.0.0" and os.environ.get("MCP_CONTAINER_BIND") == "1":
        return host
    raise SystemExit(
        "generated HTTP baseline is loopback-only; 0.0.0.0 is allowed only inside an explicitly isolated container network"
    )


def main() -> None:
    runtime = default_runtime()
    runtime.start_background()
    try:
        transport = os.environ.get("MCP_TRANSPORT", "stdio")
        if transport == "stdio":
            mcp.run()
            return
        if transport != "streamable-http":
            raise SystemExit("MCP_TRANSPORT must be stdio or streamable-http")
        try:
            port = int(os.environ.get("MCP_HTTP_PORT", "8000"))
        except ValueError as exc:
            raise SystemExit("MCP_HTTP_PORT must be an integer") from exc
        if not 1 <= port <= 65535:
            raise SystemExit("MCP_HTTP_PORT must be from 1 to 65535")
        uvicorn.run(build_http_app(), host=_http_host(), port=port, log_level="info")
    finally:
        runtime.stop_background()


if __name__ == "__main__":
    main()
'''

_PYTHON_RUNTIME_TEST = r'''from datetime import UTC, datetime
from pathlib import Path

import pytest

from __PACKAGE__.steward_runtime import (
    FakeClock,
    FaultInjector,
    StewardRuntime,
    StewardStore,
    compute_handoff_digest,
)

PROFILE = __PROFILE_JSON__
PROOF = __PROOF_JSON__


def runtime(path: Path, *, faults: set[str] | None = None, clock: FakeClock | None = None) -> StewardRuntime:
    selected_clock = clock or FakeClock()
    return StewardRuntime(
        StewardStore(path, selected_clock),
        PROFILE,
        PROOF,
        faults=FaultInjector(faults),
    )


def test_idempotent_admission_returns_same_job_and_rejects_key_rebinding(tmp_path: Path) -> None:
    value = runtime(tmp_path / "state.db")
    first = value.submit("repo", "abc", "idem-1")
    duplicate = value.submit("repo", "abc", "idem-1")
    assert duplicate["duplicate"] is True
    assert duplicate["jobId"] == first["jobId"]
    with pytest.raises(RuntimeError, match="different subject"):
        value.submit("other", "abc", "idem-1")


def test_restart_reconciles_unknown_delivery_and_completion_gate_seals_handoff(tmp_path: Path) -> None:
    path = tmp_path / "state.db"
    first = runtime(path, faults={"after-dispatch"})
    admitted = first.submit("repo", "abc", "idem-1")
    assert first.run_once() is True
    assert first.run_once() is True
    assert first.status(admitted["jobId"])["status"] == "reconciling"

    recovered = runtime(path)
    recovered.recover_until_idle()
    result = recovered.get(admitted["jobId"])
    assert result["job"]["status"] == "completed"
    assert result["completion"]["disposition"] == "eligible"
    assert result["completion"]["obligations"][0]["evidenceRefs"]
    assert result["handoff"]["digest"] == compute_handoff_digest(result["handoff"])
    assert any(event["type"] == "external.delivery-unknown" for event in result["timeline"])
    assert any(event["type"] == "handoff.sealed" for event in result["timeline"])


def test_completion_gate_rejects_missing_or_expired_evidence(tmp_path: Path) -> None:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    value = runtime(tmp_path / "state.db", clock=clock)
    job_id = value.submit("repo", "abc", "idem-1")["jobId"]
    value.run_once()
    value.run_once()
    with pytest.raises(RuntimeError, match="completion gate"):
        value.store.finalize_with_gate(job_id, PROFILE, PROOF, outcome="forged")
    value.run_once()
    clock.advance(301)
    with pytest.raises(RuntimeError, match="completion gate"):
        value.store.finalize_with_gate(job_id, PROFILE, PROOF, outcome="stale-evidence")


def test_cancel_is_persisted_and_supervisor_closes_without_new_dispatch(tmp_path: Path) -> None:
    value = runtime(tmp_path / "state.db")
    job_id = value.submit("repo", "abc", "idem-1")["jobId"]
    value.cancel(job_id)
    value.run_once()
    result = value.get(job_id)
    assert result["job"]["status"] == "cancelled"
    assert result["operations"] == []
'''


def _python_capability(
    capability_id: str,
    name: str,
    description: str,
    *,
    operation_kind: str,
    risk: str,
    impact: str,
    idempotent: bool,
    idempotency_key_required: bool,
) -> str:
    manifest: dict[str, Any] = {
        "schema_version": 2,
        "contract_revision": 2,
        "id": capability_id,
        "name": name,
        "description": description,
        "operation_kind": operation_kind,
        "risk": risk,
        "determinism": "environment-dependent",
        "latency": "interactive",
        "impact": impact,
        "active_state": "active",
        "retryable": False,
        "idempotent": idempotent,
        "reversible": False,
        "requires_confirmation": False,
        "idempotency_key_required": idempotency_key_required,
        "idempotency": {
            "mode": "keyed" if idempotency_key_required else ("intrinsic" if idempotent else "none"),
            "scope": "principal-target" if operation_kind in {"write", "destructive"} else "invocation",
        },
        "async_model": "external-job" if capability_id == "steward_submit" else "synchronous",
        "outcome_contract": "layered",
        "reconciliation": {
            "supported": capability_id == "steward_submit",
            "required_after_ambiguous_dispatch": capability_id == "steward_submit",
            "method": "custom" if capability_id == "steward_submit" else "none",
        },
        "publication": {"model": "inline", "implies_verification": False},
        "result_bounded": True,
        "runtime_identity": {"supported": False, "level": "none"},
        "authorization_scopes": ["steward:write"] if operation_kind in {"write", "destructive"} else ["steward:read"],
        "concurrency": {
            "scope": "principal-target" if operation_kind in {"write", "destructive"} else "principal",
            "limit": 4,
            "queue_limit": 16,
        },
        "max_response_bytes": 65536,
        "protocol_revisions": ["2026-07-28", "2025-11-25"],
    }
    if operation_kind in {"write", "destructive"} and idempotent:
        manifest["extensions"] = {
            "idempotent_rationale": "Durable idempotency or terminal cancellation semantics prevent duplicate logical effects."
        }
    return json.dumps(manifest, indent=2, sort_keys=False) + "\n"


def _apply_python_overlay(
    files: dict[str, str],
    package: str,
    server_name: str,
    profile_doc: dict[str, Any],
    proof_doc: dict[str, Any],
) -> None:
    capability_prefix = f"src/{package}/capabilities/"
    for path in [key for key in files if key.startswith(capability_prefix)]:
        del files[path]
    files[f"src/{package}/steward_runtime.py"] = _PYTHON_RUNTIME
    files[f"src/{package}/kernel.py"] = _PYTHON_KERNEL
    files[f"src/{package}/server.py"] = _PYTHON_SERVER.replace("__SERVER_NAME__", server_name)
    files[f"src/{package}/steward_profile.json"] = json.dumps(profile_doc, indent=2) + "\n"
    files[f"src/{package}/steward_proof_recipe.json"] = json.dumps(proof_doc, indent=2) + "\n"
    files[f"src/{package}/capabilities/describe_capabilities.json"] = _python_capability(
        "describe_capabilities", "Describe capabilities", "Returns the governed Steward capability catalog.",
        operation_kind="read", risk="low", impact="none", idempotent=True, idempotency_key_required=False,
    )
    files[f"src/{package}/capabilities/steward_submit.json"] = _python_capability(
        "steward_submit", "Submit Steward job", "Durably admits an idempotent Steward job and returns its stable job ID.",
        operation_kind="write", risk="medium", impact="local", idempotent=True, idempotency_key_required=True,
    )
    files[f"src/{package}/capabilities/steward_status.json"] = _python_capability(
        "steward_status", "Steward status", "Returns bounded operational status for one durable Steward job.",
        operation_kind="read", risk="low", impact="none", idempotent=True, idempotency_key_required=False,
    )
    files[f"src/{package}/capabilities/steward_get.json"] = _python_capability(
        "steward_get", "Get Steward result", "Returns bounded evidence, completion evaluation and terminal handoff for one job.",
        operation_kind="read", risk="low", impact="none", idempotent=True, idempotency_key_required=False,
    )
    files[f"src/{package}/capabilities/steward_cancel.json"] = _python_capability(
        "steward_cancel", "Cancel Steward job", "Persists cancellation intent for one non-terminal Steward job.",
        operation_kind="write", risk="medium", impact="local", idempotent=True, idempotency_key_required=False,
    )
    files[f"src/{package}/capabilities/steward_doctor.json"] = _python_capability(
        "steward_doctor", "Steward doctor", "Returns bounded durable diagnostics, open ambiguity and recovery state.",
        operation_kind="read", risk="low", impact="none", idempotent=True, idempotency_key_required=False,
    )
    files["tests/test_steward_runtime.py"] = (
        _PYTHON_RUNTIME_TEST.replace("__PACKAGE__", package)
        .replace("__PROFILE_JSON__", repr(profile_doc))
        .replace("__PROOF_JSON__", repr(proof_doc))
    )
    files.pop("tests/test_generated_contract.py", None)
    files.pop("tests/test_generated_concurrency.py", None)
    pyproject = files.get("pyproject.toml", "")
    marker = f'{package} = ["capabilities/*.json", "contracts/*.json"]'
    replacement = f'{package} = ["capabilities/*.json", "contracts/*.json", "steward_profile.json", "steward_proof_recipe.json"]'
    if marker not in pyproject:
        raise RuntimeError("canonical Python package-data marker changed")
    files["pyproject.toml"] = pyproject.replace(marker, replacement)


_DOTNET_STEWARD = r'''using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace __NAMESPACE__.Mcp.Server;

public sealed record StewardSeedJob(
    string JobId,
    string SubjectId,
    string? SubjectRevision,
    string IdempotencyKey,
    string Status,
    long Generation,
    string AttemptId,
    IReadOnlyList<string> EvidenceRefs,
    string? HandoffDigest);

public sealed class StewardSeedRuntime : IDisposable
{
    private readonly string _statePath;
    private readonly FileStream _ownerLock;
    private StewardSeedState _state;

    public StewardSeedRuntime()
    {
        var directory = Environment.GetEnvironmentVariable("STEWARD_STATE_DIR")
            ?? Path.Combine(AppContext.BaseDirectory, ".steward");
        Directory.CreateDirectory(directory);
        _statePath = Path.Combine(directory, "seed-state.json");
        _ownerLock = new FileStream(
            Path.Combine(directory, "seed-state.lock"),
            FileMode.OpenOrCreate,
            FileAccess.ReadWrite,
            FileShare.None);
        _state = Load();
    }

    public StewardSeedJob Submit(string subjectId, string? subjectRevision, string idempotencyKey)
    {
        if (_state.Idempotency.TryGetValue(idempotencyKey, out var existing))
        {
            var current = _state.Jobs[existing];
            if (current.SubjectId != subjectId || current.SubjectRevision != subjectRevision)
                throw new InvalidOperationException("idempotency key reused for a different subject");
            return current;
        }
        var jobId = "job-" + Guid.NewGuid().ToString("N");
        var job = new StewardSeedJob(
            jobId,
            subjectId,
            subjectRevision,
            idempotencyKey,
            "queued",
            1,
            "attempt-" + Guid.NewGuid().ToString("N"),
            [],
            null);
        _state.Jobs[jobId] = job;
        _state.Idempotency[idempotencyKey] = jobId;
        Audit(jobId, "job.admitted");
        Save();
        return job;
    }

    public StewardSeedJob Status(string jobId) => _state.Jobs.TryGetValue(jobId, out var job)
        ? job
        : throw new KeyNotFoundException(jobId);

    public object Get(string jobId) => new
    {
        job = Status(jobId),
        timeline = _state.Audit.Where(item => item.JobId == jobId).TakeLast(50).ToArray(),
    };

    public StewardSeedJob RunOnce(string jobId)
    {
        var job = Status(jobId);
        if (job.Status is "completed" or "cancelled")
            return job;
        if (job.Status == "queued")
        {
            job = job with { Status = "waiting-external" };
            _state.Jobs[jobId] = job;
            Audit(jobId, "external.accepted");
            Save();
            return job;
        }
        if (job.Status == "waiting-external")
        {
            var evidence = "evidence:" + Convert.ToHexString(
                SHA256.HashData(Encoding.UTF8.GetBytes(job.SubjectId + ":" + job.SubjectRevision))).ToLowerInvariant();
            job = job with { Status = "finalizing", EvidenceRefs = [evidence] };
            _state.Jobs[jobId] = job;
            Audit(jobId, "evidence.persisted");
            Save();
            return job;
        }
        if (job.Status == "finalizing")
        {
            if (job.EvidenceRefs.Count == 0)
                throw new InvalidOperationException("completion gate requires evidence");
            var handoff = new SortedDictionary<string, object?>
            {
                ["generation"] = job.Generation,
                ["jobId"] = job.JobId,
                ["status"] = "completed",
                ["subjectId"] = job.SubjectId,
                ["subjectRevision"] = job.SubjectRevision,
                ["evidenceRefs"] = job.EvidenceRefs,
            };
            var canonical = JsonSerializer.Serialize(handoff, new JsonSerializerOptions { WriteIndented = false });
            var digest = "sha256:" + Convert.ToHexString(
                SHA256.HashData(Encoding.UTF8.GetBytes(canonical))).ToLowerInvariant();
            job = job with { Status = "completed", HandoffDigest = digest };
            _state.Jobs[jobId] = job;
            Audit(jobId, "handoff.sealed");
            Save();
        }
        return job;
    }

    public StewardSeedJob Cancel(string jobId)
    {
        var job = Status(jobId);
        if (job.Status == "completed")
            return job;
        job = job with { Status = "cancelled" };
        _state.Jobs[jobId] = job;
        Audit(jobId, "job.cancelled");
        Save();
        return job;
    }

    public object Doctor(string? jobId = null) => new
    {
        jobs = _state.Jobs.Count,
        selected = jobId is null ? null : Status(jobId),
        timeline = _state.Audit.TakeLast(50).ToArray(),
    };

    public void Dispose() => _ownerLock.Dispose();

    private void Audit(string jobId, string type) =>
        _state.Audit.Add(new StewardSeedAudit(DateTimeOffset.UtcNow, jobId, type));

    private StewardSeedState Load()
    {
        if (!File.Exists(_statePath))
            return new();
        try
        {
            return JsonSerializer.Deserialize<StewardSeedState>(File.ReadAllText(_statePath)) ?? new();
        }
        catch (JsonException)
        {
            File.Move(_statePath, _statePath + $".corrupt-{DateTimeOffset.UtcNow:yyyyMMddHHmmssfff}");
            return new();
        }
    }

    private void Save()
    {
        var temp = _statePath + ".tmp-" + Guid.NewGuid().ToString("N");
        try
        {
            using (var stream = new FileStream(
                temp,
                FileMode.CreateNew,
                FileAccess.Write,
                FileShare.None,
                4096,
                FileOptions.WriteThrough))
            {
                JsonSerializer.Serialize(stream, _state);
                stream.Flush(flushToDisk: true);
            }
            File.Move(temp, _statePath, overwrite: true);
        }
        finally
        {
            if (File.Exists(temp))
                File.Delete(temp);
        }
    }

    public sealed class StewardSeedState
    {
        public Dictionary<string, StewardSeedJob> Jobs { get; init; } = [];
        public Dictionary<string, string> Idempotency { get; init; } = [];
        public List<StewardSeedAudit> Audit { get; init; } = [];
    }

    public sealed record StewardSeedAudit(DateTimeOffset At, string JobId, string Type);
}
'''

_DOTNET_TOOLS = r'''using Microsoft.AspNetCore.Authorization;
using ModelContextProtocol.Server;
using System.ComponentModel;
using System.Security.Claims;
using __NAMESPACE__.Mcp.Domain;

namespace __NAMESPACE__.Mcp.Server;

public sealed record CapabilityListResult(IReadOnlyList<CapabilityManifest> Capabilities, int Count);

[McpServerToolType]
public sealed class CapabilityTools(InvocationKernel kernel)
{
    [Authorize(Policy = "inventory.read")]
    [McpServerTool(
        Name = CapabilityNames.DescribeCapabilities,
        ReadOnly = true,
        Destructive = false,
        Idempotent = true,
        OpenWorld = false,
        UseStructuredContent = true,
        OutputSchemaType = typeof(CapabilityListResult))]
    [Description("Returns zero-I/O governed capabilities visible to the caller.")]
    public async Task<CapabilityListResult> DescribeCapabilitiesAsync(
        ClaimsPrincipal? principal,
        CancellationToken cancellationToken = default)
    {
        var manifests = await kernel.DescribeAsync(principal, cancellationToken);
        return new(manifests, manifests.Count);
    }
}

[McpServerToolType]
public sealed class InventoryTools(InvocationKernel kernel)
{
    [Authorize(Policy = "inventory.read")]
    [McpServerTool(Name = CapabilityNames.ListItems, ReadOnly = true, Destructive = false, Idempotent = true, OpenWorld = false, UseStructuredContent = true, OutputSchemaType = typeof(ListItemsResult))]
    [Description("Lists bounded inventory summaries.")]
    public Task<ListItemsResult> ListItemsAsync(ClaimsPrincipal? principal, int limit = 25, CancellationToken cancellationToken = default) =>
        kernel.ListAsync(principal, limit, cancellationToken).AsTask();

    [Authorize(Policy = "inventory.write")]
    [McpServerTool(Name = CapabilityNames.PutItem, ReadOnly = false, Destructive = false, Idempotent = false, OpenWorld = false, UseStructuredContent = true, OutputSchemaType = typeof(InventoryItem))]
    [Description("Creates or updates one item with mandatory optimistic concurrency and trusted approval.")]
    public Task<InventoryItem> PutItemAsync(ClaimsPrincipal? principal, string itemId, string name, int expectedVersion, string approvalToken, CancellationToken cancellationToken = default) =>
        kernel.PutAsync(principal, itemId, name, expectedVersion, approvalToken, cancellationToken).AsTask();
}

[McpServerToolType]
public sealed class StewardTools(StewardSeedRuntime runtime)
{
    [Authorize(Policy = "inventory.write")]
    [McpServerTool(Name = "steward_submit", ReadOnly = false, Destructive = false, Idempotent = true, OpenWorld = false, UseStructuredContent = true)]
    public StewardSeedJob Submit(string subjectId, string idempotencyKey, string? subjectRevision = null) =>
        runtime.Submit(subjectId, subjectRevision, idempotencyKey);

    [Authorize(Policy = "inventory.read")]
    [McpServerTool(Name = "steward_status", ReadOnly = true, Destructive = false, Idempotent = true, OpenWorld = false, UseStructuredContent = true)]
    public StewardSeedJob Status(string jobId) => runtime.Status(jobId);

    [Authorize(Policy = "inventory.read")]
    [McpServerTool(Name = "steward_get", ReadOnly = true, Destructive = false, Idempotent = true, OpenWorld = false, UseStructuredContent = true)]
    public object Get(string jobId) => runtime.Get(jobId);

    [Authorize(Policy = "inventory.write")]
    [McpServerTool(Name = "steward_cancel", ReadOnly = false, Destructive = false, Idempotent = true, OpenWorld = false, UseStructuredContent = true)]
    public StewardSeedJob Cancel(string jobId) => runtime.Cancel(jobId);

    [Authorize(Policy = "inventory.read")]
    [McpServerTool(Name = "steward_doctor", ReadOnly = true, Destructive = false, Idempotent = true, OpenWorld = false, UseStructuredContent = true)]
    public object Doctor(string? jobId = null) => runtime.Doctor(jobId);
}
'''


def _apply_dotnet_overlay(files: dict[str, str], namespace: str) -> None:
    files[f"src/{namespace}.Mcp.Server/StewardSeedRuntime.cs"] = _DOTNET_STEWARD.replace("__NAMESPACE__", namespace)
    files[f"src/{namespace}.Mcp.Server/Tools.cs"] = _DOTNET_TOOLS.replace("__NAMESPACE__", namespace)
    program_path = f"src/{namespace}.Mcp.Server/Program.cs"
    program = files[program_path]
    program = program.replace(
        "    services.AddSingleton<InvocationKernel>();",
        "    services.AddSingleton<InvocationKernel>();\n    services.AddSingleton<StewardSeedRuntime>();",
    )
    program = program.replace(
        ".WithTools<InventoryTools>();",
        ".WithTools<InventoryTools>()\n        .WithTools<StewardTools>();",
    )
    files[program_path] = program
    smoke_path = f"tests/{namespace}.Mcp.Smoke/Program.cs"
    smoke = files[smoke_path]
    marker = "await VerifyConcurrencyContractAsync();"
    if marker not in smoke:
        raise RuntimeError("canonical .NET smoke marker changed")
    smoke = smoke.replace(marker, marker + "\nVerifyStewardSeed();")
    smoke += f'''\n\nstatic void VerifyStewardSeed()\n{{\n    var directory = Path.Combine(Path.GetTempPath(), "{namespace}.steward-" + Guid.NewGuid().ToString("N"));\n    Environment.SetEnvironmentVariable("STEWARD_STATE_DIR", directory);\n    Directory.CreateDirectory(directory);\n    try\n    {{\n        string jobId;\n        using (var runtime = new {namespace}.Mcp.Server.StewardSeedRuntime())\n        {{\n            var first = runtime.Submit("repo", "abc", "idem-1");\n            var duplicate = runtime.Submit("repo", "abc", "idem-1");\n            if (first.JobId != duplicate.JobId)\n                throw new InvalidOperationException("Steward idempotent admission failed");\n            jobId = first.JobId;\n            runtime.RunOnce(jobId);\n        }}\n        using (var recovered = new {namespace}.Mcp.Server.StewardSeedRuntime())\n        {{\n            recovered.RunOnce(jobId);\n            var completed = recovered.RunOnce(jobId);\n            if (completed.Status != "completed" || string.IsNullOrWhiteSpace(completed.HandoffDigest))\n                throw new InvalidOperationException("Steward restart-to-finalization flow failed");\n        }}\n    }}\n    finally\n    {{\n        Environment.SetEnvironmentVariable("STEWARD_STATE_DIR", null);\n        if (Directory.Exists(directory))\n            Directory.Delete(directory, recursive: true);\n    }}\n}}\n'''
    files[smoke_path] = smoke


def steward_files(language: str, identity: str, server_name: str, steward_id: str, profile: str) -> dict[str, str]:
    if profile not in PROFILES:
        raise ValueError(f"unsupported profile: {profile}")
    base = _base_generator(language)
    files = dict(base.project_files(identity, server_name))
    durability_profile = "single-node-durable" if language == "python" else "constrained-file"
    profile_doc = _profile_document(steward_id, profile, durability_profile=durability_profile)
    proof_doc = _proof_recipe_document(steward_id)
    if language == "python":
        _apply_python_overlay(files, identity, server_name, profile_doc, proof_doc)
    else:
        _apply_dotnet_overlay(files, identity)

    overlay = {
        "steward/steward-profile.yaml": yaml.safe_dump(profile_doc, sort_keys=False),
        "steward/proof-recipe.yaml": yaml.safe_dump(proof_doc, sort_keys=False),
        "steward/fault-injection.yaml": yaml.safe_dump(
            {
                "schema_version": 1,
                "fault_points": [
                    "after-reservation",
                    "after-dispatch",
                    "before-handle-persist",
                    "before-result-persist",
                    "before-terminal-publication",
                ],
            },
            sort_keys=False,
        ),
        "steward/README.md": (
            "# Steward runtime\n\n"
            "The generated seed wires semantic MCP submit/status/get/cancel/doctor roles to durable workflow state. "
            "It includes idempotent admission, a recovery supervisor, deterministic fake clock/provider/fault injection, "
            "durable audit, evidence resolution and a mandatory Completion Gate. Replace the seed provider through a semantic "
            "port without bypassing the application-owned invocation and completion boundaries.\n"
        ),
    }
    for contract_name in STEWARD_CONTRACTS:
        overlay[f"steward/contracts/{contract_name}"] = (CONTRACTS / contract_name).read_text(encoding="utf-8")
    collisions = sorted(set(files) & set(overlay))
    if collisions:
        raise ValueError("Steward overlay collides with base generator: " + ", ".join(collisions))
    files.update(overlay)
    return files


def _publish_no_replace(language: str, staging: Path, destination: Path) -> None:
    base = _base_generator(language)
    if language == "python":
        implementation = getattr(base, "_implementation", None)
        rename = getattr(implementation, "_rename_noreplace", None)
    else:
        rename = getattr(base, "_rename_noreplace", None)
    if not callable(rename):
        raise RuntimeError("canonical MCP generator no-replace publication primitive is unavailable")
    rename(staging, destination)


def generate_project(
    destination: Path,
    *,
    language: str,
    identity: str,
    server_name: str,
    steward_id: str,
    profile: str,
) -> list[Path]:
    files = steward_files(language, identity, server_name, steward_id, profile)
    expanded = destination.expanduser()
    if os.path.lexists(expanded):
        raise FileExistsError(expanded)
    parent = expanded.parent.resolve(strict=False)
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / expanded.name
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=parent))
    published = False
    try:
        for relative, content in sorted(files.items()):
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
        _publish_no_replace(language, staging, destination)
        published = True
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    return [Path(path) for path in sorted(files)]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--language", choices=["python", "dotnet"], required=True)
    parser.add_argument("--identity", required=True, help="Python package or .NET namespace")
    parser.add_argument("--name", required=True, help="Human-readable MCP server name")
    parser.add_argument("--steward-id", required=True)
    parser.add_argument("--profile", choices=sorted(PROFILES), default="generic")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    generated = generate_project(
        args.destination,
        language=args.language,
        identity=args.identity,
        server_name=args.name,
        steward_id=args.steward_id,
        profile=args.profile,
    )
    print(f"generated {len(generated)} files in {args.destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
