"""Deterministic, append-only reference contract for amendable Steward evidence.

A trusted host injects authenticated principal and separate grant callbacks. Caller
payloads may not grant their own amendment authority.  SQLite is the durable CAS
boundary; downstream consumers bind to `effective_revision`.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any


class AmendmentRejected(ValueError):
    """Typed fail-closed refusal with a bounded current revision."""

    def __init__(self, reason: str, current_revision: int | None = None):
        super().__init__(reason)
        self.reason = reason
        self.current_revision = current_revision


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _digest(value: object) -> str:
    return "sha256:" + hashlib.sha256(_json(value).encode()).hexdigest()


def _bounded_mapping(value: Mapping[str, Any], *, field: str, max_bytes: int) -> tuple[dict[str, Any], str]:
    try:
        result = dict(value)
        canonical = _json(result)
    except (TypeError, ValueError, OverflowError) as exc:
        raise AmendmentRejected("invalid_" + field) from exc
    if len(canonical.encode("utf-8")) > max_bytes:
        raise AmendmentRejected("oversized_" + field)
    return result, canonical


class AmendmentLineage:
    """A single SQLite-backed linear history (one SQLite writer lock per database)."""

    def __init__(
        self,
        path: str | Path,
        authorize: Callable[[str, str, str], str | None],
        authenticated_principal: Callable[[], str],
    ):
        if not callable(authorize) or not callable(authenticated_principal):
            raise ValueError("trusted_authority_and_identity_callbacks_required")
        self.authorize = authorize
        self.authenticated_principal = authenticated_principal
        self.db = sqlite3.connect(str(path), isolation_level=None, timeout=5)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS lineage (
                lineage_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, head_id TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS amendments (
                lineage_id TEXT NOT NULL, revision INTEGER NOT NULL, operation_id TEXT NOT NULL,
                fingerprint TEXT NOT NULL, record_id TEXT NOT NULL, predecessor TEXT,
                op TEXT NOT NULL, principal TEXT NOT NULL, authority_ref TEXT NOT NULL,
                reason TEXT NOT NULL, payload TEXT, provenance TEXT NOT NULL,
                PRIMARY KEY(lineage_id, revision), UNIQUE(lineage_id, operation_id),
                UNIQUE(lineage_id, record_id)
            );
            CREATE TRIGGER IF NOT EXISTS no_amendment_update BEFORE UPDATE ON amendments
                BEGIN SELECT RAISE(ABORT, 'amendments_are_immutable'); END;
            CREATE TRIGGER IF NOT EXISTS no_amendment_delete BEFORE DELETE ON amendments
                BEGIN SELECT RAISE(ABORT, 'amendments_are_immutable'); END;
        """)

    def close(self) -> None:
        self.db.close()

    def _read_admit(self, lineage_id: str, action: str) -> None:
        """Require separately issued host authority for payload/provenance disclosure."""
        self._check_lineage_id(lineage_id)
        principal = self.authenticated_principal()
        if (
            not isinstance(principal, str)
            or not principal
            or not isinstance(grant := self.authorize(principal, lineage_id, action), str)
            or not grant
        ):
            raise AmendmentRejected("read_unauthorized")

    @staticmethod
    def _check_lineage_id(lineage_id: str) -> None:
        if not isinstance(lineage_id, str) or not lineage_id:
            raise AmendmentRejected("invalid_lineage_id")

    def _begin(self) -> None:
        try:
            self.db.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                raise AmendmentRejected("writer_busy") from exc
            raise AmendmentRejected("persistence_unavailable") from exc

    def _snapshot(self, lineage_id: str, revision: int) -> dict[str, Any]:
        row = self.db.execute(
            """SELECT record_id, op, payload, provenance FROM amendments
            WHERE lineage_id=? AND revision=?""",
            (lineage_id, revision),
        ).fetchone()
        if row is None:
            raise AmendmentRejected("unknown_lineage")
        record_id, op, raw, provenance = row
        payload = json.loads(raw) if op != "retract" else None
        identity = _digest([lineage_id, revision, record_id, op, payload])
        latest = self.db.execute("SELECT revision FROM lineage WHERE lineage_id=?", (lineage_id,)).fetchone()
        is_current = bool(latest is not None and latest[0] == revision)
        return {
            "lineage_id": lineage_id,
            "revision": revision,
            "head_id": record_id,
            "effective": payload,
            "status": "superseded" if not is_current else ("retracted" if op == "retract" else "current"),
            "is_current": is_current,
            "effective_revision": identity,
            "provenance": json.loads(provenance),
        }

    def _admit(self, principal: str, lineage_id: str, action: str, authority_ref: str) -> None:
        self._check_lineage_id(lineage_id)
        if (
            not isinstance(principal, str)
            or not principal
            or not isinstance(authority_ref, str)
            or not authority_ref
            or self.authenticated_principal() != principal
            or self.authorize(principal, lineage_id, action) != authority_ref
        ):
            raise AmendmentRejected("unauthorized")

    def create(
        self,
        *,
        lineage_id: str,
        record_id: str,
        payload: Mapping[str, Any],
        provenance: Mapping[str, Any],
        principal: str,
        authority_ref: str,
    ) -> dict[str, Any]:
        self._admit(principal, lineage_id, "create", authority_ref)
        self._read_admit(lineage_id, "read_current")
        if (
            not isinstance(record_id, str)
            or not record_id
            or not isinstance(payload, Mapping)
            or not isinstance(provenance, Mapping)
        ):
            raise AmendmentRejected("invalid_initial_record")
        if len(record_id) > 256 or len(lineage_id) > 256:
            raise AmendmentRejected("oversized_identity")
        _, material = _bounded_mapping(payload, field="payload", max_bytes=65536)
        _, source = _bounded_mapping(provenance, field="provenance", max_bytes=16384)
        fingerprint = _digest([material, source, principal, authority_ref, record_id])
        self._begin()
        try:
            # Host callbacks for transactional checks must be synchronous and local.
            self._admit(principal, lineage_id, "create", authority_ref)
            self._read_admit(lineage_id, "read_current")
            existing = self.db.execute(
                """SELECT record_id, fingerprint FROM amendments
                WHERE lineage_id=? AND revision=0""",
                (lineage_id,),
            ).fetchone()
            if existing is not None:
                if existing != (record_id, fingerprint):
                    raise AmendmentRejected("create_persistence_conflict")
            else:
                self.db.execute("INSERT INTO lineage VALUES (?, 0, ?)", (lineage_id, record_id))
                self.db.execute(
                    "INSERT INTO amendments VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        lineage_id,
                        "initial:" + record_id,
                        fingerprint,
                        record_id,
                        None,
                        "create",
                        principal,
                        authority_ref,
                        "initial_record",
                        material,
                        source,
                    ),
                )
            self.db.execute("COMMIT")
        except sqlite3.DatabaseError as exc:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise AmendmentRejected("create_persistence_conflict") from exc
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
        return self._snapshot(lineage_id, 0)

    def current(self, lineage_id: str) -> dict[str, Any]:
        self._read_admit(lineage_id, "read_current")
        row = self.db.execute("SELECT revision FROM lineage WHERE lineage_id=?", (lineage_id,)).fetchone()
        if row is None:
            raise AmendmentRejected("unknown_lineage")
        return self._snapshot(lineage_id, row[0])

    def amend(
        self,
        *,
        lineage_id: str,
        operation_id: str,
        record_id: str,
        expected_revision: int,
        operation: str,
        reason: str,
        principal: str,
        authority_ref: str,
        payload: Mapping[str, Any] | None = None,
        provenance: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._admit(principal, lineage_id, operation, authority_ref)
        self._read_admit(lineage_id, "read_current")
        if (
            operation not in {"correct", "retract", "supersede"}
            or not isinstance(operation_id, str)
            or not operation_id
            or not isinstance(record_id, str)
            or not record_id
            or not isinstance(reason, str)
            or not reason.strip()
        ):
            raise AmendmentRejected("invalid_amendment")
        if type(expected_revision) is not int or expected_revision < 0:
            raise AmendmentRejected("invalid_expected_revision")
        if operation != "retract" and (not isinstance(payload, Mapping) or not isinstance(provenance, Mapping)):
            raise AmendmentRejected("replacement_payload_and_provenance_required")
        if operation == "retract" and payload is not None:
            raise AmendmentRejected("retraction_must_not_replace_payload")
        if len(lineage_id) > 256 or len(operation_id) > 256 or len(record_id) > 256 or len(reason) > 4096:
            raise AmendmentRejected("oversized_identity_or_reason")
        normalized_payload = None
        if payload is not None:
            normalized_payload, _ = _bounded_mapping(payload, field="payload", max_bytes=65536)
        normalized_provenance = None
        if provenance is not None:
            normalized_provenance, _ = _bounded_mapping(provenance, field="provenance", max_bytes=16384)
        fingerprint = _digest(
            [
                operation_id,
                record_id,
                expected_revision,
                operation,
                reason,
                principal,
                authority_ref,
                normalized_payload,
                normalized_provenance,
            ]
        )
        self._begin()
        try:
            self._admit(principal, lineage_id, operation, authority_ref)
            self._read_admit(lineage_id, "read_current")
            replay = self.db.execute(
                "SELECT fingerprint, revision FROM amendments WHERE lineage_id=? AND operation_id=?",
                (lineage_id, operation_id),
            ).fetchone()
            if replay:
                if replay[0] != fingerprint:
                    raise AmendmentRejected("operation_id_conflict")
                self.db.execute("COMMIT")
                return self._snapshot(lineage_id, replay[1])
            head = self.db.execute("SELECT revision, head_id FROM lineage WHERE lineage_id=?", (lineage_id,)).fetchone()
            if head is None:
                raise AmendmentRejected("unknown_lineage")
            if head[0] != expected_revision:
                raise AmendmentRejected("stale_revision", head[0])
            if self.db.execute(
                "SELECT 1 FROM amendments WHERE lineage_id=? AND record_id=?", (lineage_id, record_id)
            ).fetchone():
                raise AmendmentRejected("record_id_conflict", head[0])
            new_revision = head[0] + 1
            self.db.execute(
                "INSERT INTO amendments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    lineage_id,
                    new_revision,
                    operation_id,
                    fingerprint,
                    record_id,
                    head[1],
                    operation,
                    principal,
                    authority_ref,
                    reason,
                    None if normalized_payload is None else _json(normalized_payload),
                    _json(normalized_provenance or {}),
                ),
            )
            changed = self.db.execute(
                "UPDATE lineage SET revision=?, head_id=? WHERE lineage_id=? AND revision=?",
                (new_revision, record_id, lineage_id, expected_revision),
            ).rowcount
            if changed != 1:
                raise AmendmentRejected("stale_revision")
            self.db.execute("COMMIT")
        except sqlite3.DatabaseError as exc:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise AmendmentRejected("amend_persistence_failure") from exc
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
        return self._snapshot(lineage_id, new_revision)

    def history(self, lineage_id: str, *, after_revision: int = -1, limit: int = 20) -> list[dict[str, Any]]:
        self._read_admit(lineage_id, "read_history")
        if type(after_revision) is not int or after_revision < -1 or type(limit) is not int or not 1 <= limit <= 50:
            raise AmendmentRejected("invalid_history_page")
        rows = self.db.execute(
            """SELECT revision, record_id, predecessor, op, principal, authority_ref,
            reason, payload, provenance FROM amendments
            WHERE lineage_id=? AND revision>? ORDER BY revision LIMIT ?""",
            (lineage_id, after_revision, limit),
        )
        return [
            {
                "revision": r,
                "record_id": rid,
                "predecessor": pred,
                "operation": op,
                "principal": actor,
                "authority_ref": auth,
                "reason": reason,
                "payload": json.loads(p) if p is not None else None,
                "provenance": json.loads(prov),
            }
            for r, rid, pred, op, actor, auth, reason, p, prov in rows
        ]

    def dependency_status(self, lineage_id: str, effective_revision: str) -> str:
        self._read_admit(lineage_id, "read_current")
        return (
            "CURRENT"
            if self.current(lineage_id)["effective_revision"] == effective_revision
            else "RE_EVALUATION_REQUIRED"
        )
