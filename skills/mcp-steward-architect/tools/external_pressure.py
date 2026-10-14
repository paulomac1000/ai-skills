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

SQLITE_INT_MAX = (1 << 63) - 1


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
        verify_resume_authority: Callable[[str, int], bool] | None = None,
    ):
        limits = (global_limit, detached_limit, per_capability_limit, cancellation_reserve, reconciliation_reserve)
        if any(type(n) is not int or n < 1 for n in limits):
            raise ValueError("positive_integer_limits_required")
        if not callable(verify_termination):
            raise ValueError("trusted_provider_termination_verifier_required")
        if verify_resume_authority is not None and not callable(verify_resume_authority):
            raise ValueError("trusted_resume_verifier_must_be_callable")
        self.verify_termination = verify_termination
        self.verify_resume_authority = verify_resume_authority
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
                reason TEXT NOT NULL,
                authority_epoch INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS pressure_controls (
                control_id TEXT PRIMARY KEY, operation_id TEXT NOT NULL,
                lane TEXT NOT NULL, state TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pressure_publications (
                operation_id TEXT PRIMARY KEY, generation INTEGER NOT NULL,
                authority_epoch INTEGER NOT NULL, result_digest TEXT NOT NULL
            );
        """)
        # A caller cannot restart with higher limits and pretend prior admissions were below policy.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            columns = {row[1] for row in self.db.execute("PRAGMA table_info(pressure_operations)")}
            if "authority_epoch" not in columns:
                self.db.execute("ALTER TABLE pressure_operations ADD COLUMN authority_epoch INTEGER NOT NULL DEFAULT 0")
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
            WHERE authority!='current' AND physical!='stopped'""").fetchone()[0]
        return active, detached

    def dispatch(self, operation_id: str, capability: str, generation: int) -> None:
        if (
            not isinstance(operation_id, str)
            or not operation_id
            or not isinstance(capability, str)
            or not capability
            or type(generation) is not int
            or not 1 <= generation <= SQLITE_INT_MAX
        ):
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
            if active >= min(self.global_limit, self.detached_limit) or occupied >= self.per_capability_limit:
                raise PressureRejected("external_admission_backpressure")
            self.db.execute(
                """INSERT INTO pressure_operations
                (operation_id, capability, generation, authority, physical, reconciliation, reason)
                VALUES (?, ?, ?, 'current', 'running', 'none', 'admitted')""",
                (operation_id, capability, generation),
            )
            self.db.execute("COMMIT")
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def fence(self, operation_id: str, reason: str) -> None:
        if not isinstance(operation_id, str) or not operation_id:
            raise PressureRejected("invalid_operation_identity")
        if not isinstance(reason, str) or reason not in {
            "superseded",
            "parent_superseded",
            "caller_cancel",
            "provider_cancel",
            "unknown",
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
            if row[1] == "stopped" and reason == "service_shutdown":
                # Terminal completion already has proof; shutdown is not a
                # domain cancellation and must not revoke publication rights.
                self.db.execute("COMMIT")
                return
            # Completion does not imply publication. A stopped but still
            # unpublished operation must lose authority on supersession.
            unpublished_terminal = (
                row[1] == "stopped"
                and not self.db.execute(
                    "SELECT 1 FROM pressure_publications WHERE operation_id=?", (operation_id,)
                ).fetchone()
            )
            if row[1] != "stopped" or unpublished_terminal:
                current = row[0] == "current"
                # A shutdown fence is resumable. A later domain cancellation
                # or supersession revokes that option even for already-fenced work.
                previous = self.db.execute(
                    "SELECT reason FROM pressure_operations WHERE operation_id=?", (operation_id,)
                ).fetchone()[0]
                revoke_shutdown = previous == "service_shutdown" and reason != "service_shutdown"
                if current or revoke_shutdown:
                    self.db.execute(
                        """UPDATE pressure_operations SET authority='fenced',
                        reconciliation='required', reason=?, authority_epoch=authority_epoch+1
                        WHERE operation_id=?""",
                        (reason, operation_id),
                    )
            self.db.execute("COMMIT")
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def resume_after_shutdown(self, operation_id: str, generation: int) -> None:
        """Reclaim shutdown-fenced authority only after host verification and a fresh CAS."""
        if (
            not isinstance(operation_id, str)
            or not operation_id
            or type(generation) is not int
            or not 1 <= generation <= SQLITE_INT_MAX
        ):
            raise PressureRejected("invalid_operation_identity")
        query = """
            SELECT generation, authority, physical, reason, authority_epoch
            FROM pressure_operations WHERE operation_id=?
        """
        before = self.db.execute(query, (operation_id,)).fetchone()
        if before is None:
            raise PressureRejected("unknown_operation")
        if (
            before[0] != generation
            or before[1] != "fenced"
            or before[2] == "stopped"
            or before[3] != "service_shutdown"
        ):
            raise PressureRejected("resume_state_conflict")
        # Provider/authority probes must never execute while holding a durable write lock.
        if self.verify_resume_authority is None or self.verify_resume_authority(operation_id, generation) is not True:
            raise PressureRejected("resume_authority_unverified")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            after = self.db.execute(query, (operation_id,)).fetchone()
            if after != before:
                raise PressureRejected("resume_state_conflict")
            self.db.execute(
                """UPDATE pressure_operations SET authority='current',
                reconciliation='none', reason='resumed',
                authority_epoch=authority_epoch+1 WHERE operation_id=?""",
                (operation_id,),
            )
            self.db.execute("COMMIT")
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def commit_publication(self, operation_id: str, generation: int, result_digest: str) -> dict[str, object]:
        """Atomically accept one immutable result identity at the current authority epoch.

        This is a canonical local publication decision, NOT a remote sink delivery.
        Remote sinks must enforce their own generation/epoch fencing.
        """
        if (
            not isinstance(operation_id, str)
            or not operation_id
            or type(generation) is not int
            or not 1 <= generation <= SQLITE_INT_MAX
            or not isinstance(result_digest, str)
            or len(result_digest) != 71
            or not result_digest.startswith("sha256:")
            or any(ch not in "0123456789abcdef" for ch in result_digest[7:])
        ):
            raise PressureRejected("invalid_publication_identity")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            prior = self.db.execute(
                """SELECT generation, authority_epoch, result_digest FROM pressure_publications
                WHERE operation_id=?""",
                (operation_id,),
            ).fetchone()
            if prior is not None:
                if prior[0] != generation or prior[2] != result_digest:
                    raise PressureRejected("publication_id_conflict")
                receipt = {
                    "operation_id": operation_id,
                    "generation": generation,
                    "authority_epoch": prior[1],
                    "result_digest": result_digest,
                }
            else:
                row = self.db.execute(
                    """SELECT generation, authority, physical, reconciliation, authority_epoch
                    FROM pressure_operations WHERE operation_id=?""",
                    (operation_id,),
                ).fetchone()
                if row is None:
                    raise PressureRejected("unknown_operation")
                if row[0] != generation or row[1] != "current" or row[2] != "stopped" or row[3] != "resolved":
                    raise PressureRejected("publication_authority_stale")
                self.db.execute(
                    "INSERT INTO pressure_publications VALUES (?, ?, ?, ?)",
                    (operation_id, generation, row[4], result_digest),
                )
                receipt = {
                    "operation_id": operation_id,
                    "generation": generation,
                    "authority_epoch": row[4],
                    "result_digest": result_digest,
                }
            self.db.execute("COMMIT")
            return receipt
        except sqlite3.DatabaseError as exc:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise PressureRejected("publication_persistence_failure") from exc
        except Exception:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def publish_allowed(self, operation_id: str, generation: int) -> bool:
        """Advisory only; callers must use commit_publication for a durable decision."""

        row = self.db.execute(
            """SELECT authority, physical, generation, reconciliation
            FROM pressure_operations WHERE operation_id=?""",
            (operation_id,),
        ).fetchone()
        return bool(
            row and row[0] == "current" and row[1] == "stopped" and row[2] == generation and row[3] == "resolved"
        )

    def acquire_control(self, control_id: str, operation_id: str, lane: str) -> None:
        if not isinstance(operation_id, str) or not operation_id:
            raise PressureRejected("invalid_operation_identity")
        if not isinstance(lane, str) or lane not in self.reserves or not isinstance(control_id, str) or not control_id:
            raise PressureRejected("invalid_control_lane")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            op = self.db.execute(
                "SELECT physical, authority FROM pressure_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if op is None:
                raise PressureRejected("unknown_operation")
            if op[0] == "stopped" or (lane == "reconcile" and op[1] != "fenced"):
                raise PressureRejected("control_operation_ineligible")
            existing = self.db.execute(
                """SELECT control_id FROM pressure_controls
                WHERE operation_id=? AND lane=? AND state='active'""",
                (operation_id, lane),
            ).fetchone()
            if existing is not None:
                if existing[0] != control_id:
                    raise PressureRejected("active_control_already_reserved")
                self.db.execute("COMMIT")
                return
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
        if not isinstance(control_id, str) or not control_id:
            raise PressureRejected("invalid_control_identity")
        changed = self.db.execute(
            "UPDATE pressure_controls SET state='complete' WHERE control_id=? AND state='active'", (control_id,)
        ).rowcount
        if changed != 1:
            stored = self.db.execute("SELECT state FROM pressure_controls WHERE control_id=?", (control_id,)).fetchone()
            if stored is not None and stored[0] == "complete":
                return  # Already retired by a proven terminal observation.
            raise PressureRejected("control_not_active")

    def observe(self, operation_id: str, physical: str, *, reconciled: bool) -> None:
        if not isinstance(physical, str) or physical not in {"running", "unknown", "stopped"}:
            raise PressureRejected("invalid_physical_observation")
        if not isinstance(operation_id, str) or not operation_id:
            raise PressureRejected("invalid_operation_identity")
        if type(reconciled) is not bool:
            raise PressureRejected("invalid_reconciliation_flag")
        known = self.db.execute(
            "SELECT physical FROM pressure_operations WHERE operation_id=?", (operation_id,)
        ).fetchone()
        if known is None:
            raise PressureRejected("unknown_operation")
        if known[0] == "stopped" and physical == "stopped":
            self.db.execute(
                """UPDATE pressure_controls SET state='complete'
                WHERE operation_id=? AND state='active'""",
                (operation_id,),
            )
            return  # Verified terminal observation; no repeated provider probe.
        if physical == "stopped" and (not reconciled or self.verify_termination(operation_id) is not True):
            raise PressureRejected("termination_proof_required")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute(
                "SELECT physical, authority FROM pressure_operations WHERE operation_id=?", (operation_id,)
            ).fetchone()
            if row is None:
                raise PressureRejected("unknown_operation")
            if row[0] == "stopped":
                if physical != "stopped":
                    raise PressureRejected("cannot_revive_terminated_operation")
                self.db.execute("COMMIT")
                return
            status = "resolved" if physical == "stopped" else ("required" if row[1] == "fenced" else "none")
            self.db.execute(
                """UPDATE pressure_operations SET physical=?, reconciliation=?,
                authority_epoch=authority_epoch+1 WHERE operation_id=?""",
                (physical, status, operation_id),
            )
            if physical == "stopped":
                self.db.execute(
                    """UPDATE pressure_controls SET state='complete'
                    WHERE operation_id=? AND state='active'""",
                    (operation_id,),
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
            "admission_blocked": active >= min(self.global_limit, self.detached_limit),
            "reason_codes": ["external_pressure_unresolved"] if detached else [],
        }
