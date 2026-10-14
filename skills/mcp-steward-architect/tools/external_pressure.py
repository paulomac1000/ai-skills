"""Reference pressure accounting for cancellation-insensitive external operations.

This is an admission/accounting state machine, not a scheduler or a provider API.
Durable SQLite rows remain pressure-bearing until physical resolution is proven.
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any


class PressureRejected(ValueError):
    """Typed admission/reconciliation refusal with no provider payload."""


class ExternalPressure:
    def __init__(
        self,
        path: str | Path,
        *,
        global_limit: int,
        detached_limit: int,
        per_capability_limit: int,
        cancellation_reserve: int,
        reconciliation_reserve: int,
        verify_termination: Callable[[str], bool],
    ):
        limits = (global_limit, detached_limit, per_capability_limit, cancellation_reserve, reconciliation_reserve)
        if any(type(n) is not int or n < 1 for n in limits):
            raise ValueError("positive_integer_limits_required")
        if not callable(verify_termination):
            raise ValueError("trusted_provider_termination_verifier_required")
        self.verify_termination = verify_termination
        self.global_limit, self.detached_limit, self.per_capability_limit = limits[:3]
        self.reserves = {"cancel": cancellation_reserve, "reconcile": reconciliation_reserve}
        self.db = sqlite3.connect(str(path), isolation_level=None, timeout=5)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS pressure_operations (
                operation_id TEXT PRIMARY KEY, capability TEXT NOT NULL,
                generation INTEGER NOT NULL, authority TEXT NOT NULL,
                physical TEXT NOT NULL, reconciliation TEXT NOT NULL,
                reason TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pressure_controls (
                control_id TEXT PRIMARY KEY, operation_id TEXT NOT NULL,
                lane TEXT NOT NULL, state TEXT NOT NULL
            );
        """)
        # A caller cannot restart with higher limits and pretend prior admissions were below policy.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS pressure_limits (slot INTEGER PRIMARY KEY CHECK(slot=1), caps TEXT NOT NULL)"
            )
            caps = ",".join(str(n) for n in limits)
            row = self.db.execute("SELECT caps FROM pressure_limits WHERE slot=1").fetchone()
            if row is None:
                self.db.execute("INSERT INTO pressure_limits VALUES (1, ?)", (caps,))
            elif row[0] != caps:
                raise PressureRejected("durable_capacity_policy_mismatch")
            self.db.execute("COMMIT")
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def close(self) -> None:
        self.db.close()

    def _counts(self) -> tuple[int, int]:
        active = self.db.execute("SELECT COUNT(*) FROM pressure_operations WHERE physical!='stopped'").fetchone()[0]
        detached = self.db.execute("""SELECT COUNT(*) FROM pressure_operations
            WHERE authority='fenced' AND physical!='stopped'""").fetchone()[0]
        return active, detached

    def dispatch(self, operation_id: str, capability: str, generation: int) -> None:
        if not operation_id or not capability or type(generation) is not int or generation < 1:
            raise PressureRejected("invalid_operation_identity")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            if self.db.execute("SELECT 1 FROM pressure_operations WHERE operation_id=?", (operation_id,)).fetchone():
                raise PressureRejected("operation_id_conflict")
            active, detached = self._counts()
            occupied = self.db.execute(
                """SELECT COUNT(*) FROM pressure_operations
                WHERE capability=? AND physical!='stopped'""",
                (capability,),
            ).fetchone()[0]
            if active >= self.global_limit or detached >= self.detached_limit or occupied >= self.per_capability_limit:
                raise PressureRejected("external_admission_backpressure")
            self.db.execute(
                "INSERT INTO pressure_operations VALUES (?, ?, ?, 'current', 'running', 'none', 'admitted')",
                (operation_id, capability, generation),
            )
            self.db.execute("COMMIT")
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def fence(self, operation_id: str, reason: str) -> None:
        if reason not in {
            "superseded",
            "application_deadline",
            "transport_timeout",
            "domain_cancel",
            "service_shutdown",
        }:
            raise PressureRejected("invalid_fence_reason")
        # shutdown is not a domain cancellation; physical status remains unchanged.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT authority, physical FROM pressure_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if row is None:
                raise PressureRejected("unknown_operation")
            if row[1] != "stopped":
                self.db.execute(
                    """UPDATE pressure_operations SET authority='fenced',
                    reconciliation='required', reason=? WHERE operation_id=?""",
                    (reason, operation_id),
                )
            self.db.execute("COMMIT")
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def publish_allowed(self, operation_id: str, generation: int) -> bool:
        row = self.db.execute(
            "SELECT authority, physical, generation FROM pressure_operations WHERE operation_id=?", (operation_id,)
        ).fetchone()
        return bool(row and row[0] == "current" and row[1] == "running" and row[2] == generation)

    def acquire_control(self, control_id: str, operation_id: str, lane: str) -> None:
        if lane not in self.reserves or not control_id:
            raise PressureRejected("invalid_control_lane")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            op = self.db.execute("SELECT 1 FROM pressure_operations WHERE operation_id=?", (operation_id,)).fetchone()
            if op is None:
                raise PressureRejected("unknown_operation")
            current = self.db.execute(
                "SELECT COUNT(*) FROM pressure_controls WHERE lane=? AND state='active'", (lane,)
            ).fetchone()[0]
            if current >= self.reserves[lane]:
                raise PressureRejected("control_lane_saturated")
            self.db.execute(
                "INSERT INTO pressure_controls VALUES (?, ?, ?, 'active')", (control_id, operation_id, lane)
            )
            self.db.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise PressureRejected("control_id_conflict") from exc
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def release_control(self, control_id: str) -> None:
        changed = self.db.execute(
            "UPDATE pressure_controls SET state='complete' WHERE control_id=? AND state='active'", (control_id,)
        ).rowcount
        if changed != 1:
            raise PressureRejected("control_not_active")

    def observe(self, operation_id: str, physical: str, *, reconciled: bool) -> None:
        if physical not in {"running", "unknown", "stopped"}:
            raise PressureRejected("invalid_physical_observation")
        if physical == "stopped" and (not reconciled or not self.verify_termination(operation_id)):
            raise PressureRejected("termination_proof_required")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT physical, authority FROM pressure_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if row is None:
                raise PressureRejected("unknown_operation")
            if row[0] == "stopped" and physical != "stopped":
                raise PressureRejected("cannot_revive_terminated_operation")
            status = "resolved" if physical == "stopped" else ("required" if row[1] == "fenced" else "none")
            self.db.execute(
                "UPDATE pressure_operations SET physical=?, reconciliation=? WHERE operation_id=?",
                (physical, status, operation_id),
            )
            self.db.execute("COMMIT")
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def doctor(self) -> dict[str, Any]:
        active, detached = self._counts()
        control = {
            lane: self.db.execute(
                """SELECT COUNT(*) FROM pressure_controls
                WHERE lane=? AND state='active'""",
                (lane,),
            ).fetchone()[0]
            for lane in self.reserves
        }
        # Group active physical pressure by capability but never expose the
        # supplied capability strings or remote execution handles.
        rows = self.db.execute(
            """SELECT capability, COUNT(*),
            SUM(CASE WHEN authority='fenced' THEN 1 ELSE 0 END)
            FROM pressure_operations WHERE physical!='stopped'
            GROUP BY capability"""
        ).fetchall()
        per_capability = sorted(
            (
                {
                    "capability_ref": "sha256:" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:16],
                    "active": count,
                    "detached_unresolved": unresolved,
                }
                for name, count, unresolved in rows
            ),
            key=lambda entry: entry["capability_ref"],
        )
        detached_reason_counts = dict(
            self.db.execute(
                """SELECT reason, COUNT(*) FROM pressure_operations
                WHERE authority='fenced' AND physical!='stopped'
                GROUP BY reason"""
            )
        )
        return {
            "active": active,
            "detached_unresolved": detached,
            "control_active": control,
            "per_capability": per_capability,
            "detached_reason_counts": detached_reason_counts,
            "admission_blocked": active >= self.global_limit or detached >= self.detached_limit,
            "reason_codes": ["external_pressure_unresolved"] if detached else [],
        }
