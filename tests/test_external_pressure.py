import pytest
import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "skills/mcp-steward-architect/tools/external_pressure.py"
spec = importlib.util.spec_from_file_location("external_pressure_ref", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
ExternalPressure, PressureRejected = module.ExternalPressure, module.PressureRejected


def manager(path, terminated):
    return ExternalPressure(path, global_limit=4, detached_limit=2, per_capability_limit=4,
                            cancellation_reserve=1, reconciliation_reserve=1, verify_termination=lambda op: op in terminated)


class IgnoresCancel:
    def __init__(self):
        self.alive = set()

    def dispatch(self, op):
        self.alive.add(op)

    def cancel(self, op):
        # Caller cancellation is intentionally ignored by the remote provider.
        pass


def test_detached_pressure_survives_cancel_shutdown_and_restart(tmp_path):
    path = tmp_path / 'state.db'
    terminated = set()
    mgr = manager(path, terminated)
    remote = IgnoresCancel()
    for i in range(2):
        name = f'op{i}'
        mgr.dispatch(name, 'provider-a', 1)
        remote.dispatch(name)
        mgr.fence(name, 'superseded' if i == 0 else 'service_shutdown')
        remote.cancel(name)
    assert len(remote.alive) == 2
    assert mgr.doctor()['detached_unresolved'] == 2
    assert not mgr.publish_allowed('op0', 1)
    with pytest.raises(PressureRejected, match='backpressure'):
        mgr.dispatch('new', 'provider-a', 2)
    mgr.acquire_control('cancel-1', 'op0', 'cancel')
    mgr.acquire_control('reconcile-1', 'op1', 'reconcile')
    with pytest.raises(PressureRejected, match='saturated'):
        mgr.acquire_control('cancel-2', 'op1', 'cancel')
    mgr.close()
    mgr = manager(path, terminated)
    assert mgr.doctor()['detached_unresolved'] == 2
    assert mgr.doctor()['control_active'] == {'cancel': 1, 'reconcile': 1}
    mgr.observe('op0', 'unknown', reconciled=False)
    with pytest.raises(PressureRejected, match='termination_proof_required'):
        mgr.observe('op0', 'stopped', reconciled=False)
    with pytest.raises(PressureRejected, match='backpressure'):
        mgr.dispatch('new', 'provider-a', 2)
    terminated.add('op0')
    mgr.observe('op0', 'stopped', reconciled=True)
    mgr.release_control('cancel-1')
    mgr.dispatch('new', 'provider-a', 2)
    assert mgr.publish_allowed('new', 2)
    assert not mgr.publish_allowed('new', 1)
    assert mgr.doctor()['detached_unresolved'] == 1


def test_global_and_capability_limits(tmp_path):
    terminated = {'a'}
    m = ExternalPressure(tmp_path/'other.db', global_limit=2, detached_limit=2, per_capability_limit=1,
                         cancellation_reserve=1, reconciliation_reserve=1, verify_termination=lambda op: op in terminated)
    m.dispatch('a', 'x', 1)
    with pytest.raises(PressureRejected):
        m.dispatch('b', 'x', 1)
    m.dispatch('b', 'y', 1)
    with pytest.raises(PressureRejected):
        m.dispatch('c', 'z', 1)
    m.observe('a', 'stopped', reconciled=True)
    m.dispatch('c', 'z', 1)
    with pytest.raises(PressureRejected, match='durable_capacity_policy_mismatch'):
        ExternalPressure(tmp_path/'other.db', global_limit=99, detached_limit=2, per_capability_limit=1,
                         cancellation_reserve=1, reconciliation_reserve=1, verify_termination=lambda op: op in terminated)


def test_real_profile_schema_requires_control_reserve_when_feature_enabled():
    import json
    import yaml
    from jsonschema import Draft202012Validator

    root = Path(__file__).resolve().parents[1]
    schema = json.loads((root / 'contracts/steward-profile.schema.json').read_text())
    profile = yaml.safe_load((root / 'skills/mcp-steward-architect/templates/steward-profile.yaml.template').read_text())
    validator = Draft202012Validator(schema)
    profile['features']['external_pressure_bounded'] = True
    assert list(validator.iter_errors(profile))
    profile['external_operations']['external_pressure'] = {
        'global_active_limit': 4, 'unresolved_detached_limit': 2,
        'per_capability_limit': 4, 'cancellation_reserve': 1, 'reconciliation_reserve': 1
    }
    assert not list(validator.iter_errors(profile))
    profile['external_operations']['external_pressure']['reconciliation_reserve'] = 0
    assert list(validator.iter_errors(profile))


def test_caller_boolean_cannot_claim_remote_termination(tmp_path):
    terminated = set()
    mgr = manager(tmp_path / 'proof.db', terminated)
    mgr.dispatch('remote', 'provider-a', 1)
    mgr.fence('remote', 'domain_cancel')
    with pytest.raises(PressureRejected, match='termination_proof_required'):
        mgr.observe('remote', 'stopped', reconciled=True)
    assert mgr.doctor()['detached_unresolved'] == 1
    terminated.add('remote')  # trusted provider reports physical stop
    mgr.observe('remote', 'stopped', reconciled=True)
    assert mgr.doctor()['active'] == 0


def test_doctor_aggregates_per_capability_without_exposing_raw_handles(tmp_path):
    m = manager(tmp_path / "metrics.db", set())
    m.dispatch("private-operation-handle", "private-capability-text", 1)
    m.dispatch("op2", "provider-b", 1)
    m.fence("private-operation-handle", "service_shutdown")
    view = m.doctor()
    assert view["active"] == 2 and view["detached_unresolved"] == 1
    assert view["detached_reason_counts"] == {"service_shutdown": 1}
    assert len(view["per_capability"]) == 2
    assert sum(x["active"] for x in view["per_capability"]) == 2
    assert sum(x["detached_unresolved"] for x in view["per_capability"]) == 1
    assert all(x["capability_ref"].startswith("sha256:") for x in view["per_capability"])
    assert "private-operation-handle" not in str(view)
    assert "private-capability-text" not in str(view)

def test_shutdown_durable_operation_requires_host_authority_reacquisition(tmp_path):
    grants = set()
    m = ExternalPressure(
        tmp_path / "shutdown.db",
        global_limit=2,
        detached_limit=2,
        per_capability_limit=2,
        cancellation_reserve=1,
        reconciliation_reserve=1,
        verify_termination=lambda _op: False,
        verify_resume_authority=lambda op, gen: (op, gen) in grants,
    )
    m.dispatch("durable", "remote", 1)
    m.fence("durable", "service_shutdown")
    assert not m.publish_allowed("durable", 1)
    with pytest.raises(PressureRejected, match="resume_authority_unverified"):
        m.resume_after_shutdown("durable", 1)
    grants.add(("durable", 1))
    with pytest.raises(PressureRejected, match="resume_state_conflict"):
        m.resume_after_shutdown("durable", 2)
    m.resume_after_shutdown("durable", 1)
    assert m.publish_allowed("durable", 1)
    assert m.doctor()["detached_unresolved"] == 0


def test_unknown_operation_does_not_touch_provider_verifier(tmp_path):
    called = []
    m = ExternalPressure(
        tmp_path / "unknown.db",
        global_limit=2,
        detached_limit=2,
        per_capability_limit=2,
        cancellation_reserve=1,
        reconciliation_reserve=1,
        verify_termination=lambda op: called.append(op) or False,
    )
    with pytest.raises(PressureRejected, match="unknown_operation"):
        m.observe("hostile-unregistered", "stopped", reconciled=True)
    assert called == []


def test_external_pressure_catalog_rule_is_opt_in():
    import yaml
    from contracts.rule_applicability import RuleContext, expected_rules

    root = Path(__file__).resolve().parents[1]
    catalog = yaml.safe_load((root / "contracts/rule-catalog.yaml").read_text(encoding="utf-8"))
    base = RuleContext("L1")
    opted = RuleContext("L1", profiles=frozenset({"external-pressure-bounded"}))
    rule_id = "steward.external-pressure.bounded"
    assert rule_id not in {r["id"] for r in expected_rules(catalog, "mcp-steward-architect", base)}
    assert rule_id in {r["id"] for r in expected_rules(catalog, "mcp-steward-architect", opted)}

def test_admission_reserves_all_future_detached_pressure(tmp_path):
    m = ExternalPressure(
        tmp_path / "bounded.db", global_limit=5, detached_limit=2,
        per_capability_limit=5, cancellation_reserve=1,
        reconciliation_reserve=1, verify_termination=lambda _op: False,
    )
    m.dispatch("a", "cap", 1)
    m.dispatch("b", "cap", 1)
    with pytest.raises(PressureRejected, match="backpressure"):
        m.dispatch("c", "cap", 1)
    m.fence("a", "superseded")
    m.fence("a", "service_shutdown")
    m.fence("b", "domain_cancel")
    assert m.doctor()["detached_unresolved"] == 2
    assert m.db.execute("SELECT reason FROM pressure_operations WHERE operation_id='a'").fetchone()[0] == "superseded"
    with pytest.raises(PressureRejected, match="resume_state_conflict"):
        m.resume_after_shutdown("a", 1)


def test_resume_verifier_runs_outside_sqlite_writer_lock(tmp_path):
    import sqlite3

    path = tmp_path / "no-lock.db"
    callbacks = []

    def verify(op, generation):
        alternate = sqlite3.connect(str(path), isolation_level=None, timeout=1)
        try:
            alternate.execute("BEGIN IMMEDIATE")
            alternate.execute("ROLLBACK")
            callbacks.append((op, generation))
        finally:
            alternate.close()
        return True

    m = ExternalPressure(
        path, global_limit=2, detached_limit=2,
        per_capability_limit=2, cancellation_reserve=1,
        reconciliation_reserve=1, verify_termination=lambda _op: False,
        verify_resume_authority=verify,
    )
    m.dispatch("durable", "cap", 1)
    m.fence("durable", "service_shutdown")
    m.resume_after_shutdown("durable", 1)
    assert callbacks == [("durable", 1)]
    assert m.publish_allowed("durable", 1)

def test_terminated_operation_cannot_consume_control_reserve(tmp_path):
    m = ExternalPressure(
        tmp_path / "lane.db",
        global_limit=3,
        detached_limit=3,
        per_capability_limit=3,
        cancellation_reserve=1,
        reconciliation_reserve=1,
        verify_termination=lambda op: op == "stopped",
    )
    m.dispatch("stopped", "cap", 1)
    m.observe("stopped", "stopped", reconciled=True)
    m.dispatch("active", "cap", 1)
    m.fence("active", "domain_cancel")
    with pytest.raises(PressureRejected, match="control_operation_ineligible"):
        m.acquire_control("fake", "stopped", "cancel")
    m.acquire_control("real", "active", "cancel")
    assert m.doctor()["control_active"]["cancel"] == 1


def test_shutdown_resume_rejects_aba_authority_cycle(tmp_path):
    path = tmp_path / "epoch.db"
    latest = ExternalPressure(
        path, global_limit=2, detached_limit=2, per_capability_limit=2,
        cancellation_reserve=1, reconciliation_reserve=1,
        verify_termination=lambda _: False,
        verify_resume_authority=lambda _op, _gen: True,
    )
    latest.dispatch("durable", "cap", 1)
    latest.fence("durable", "service_shutdown")
    before = latest.db.execute(
        "SELECT authority_epoch FROM pressure_operations WHERE operation_id='durable'"
    ).fetchone()[0]

    def overlapping_recovery(op, generation):
        other = ExternalPressure(
            path, global_limit=2, detached_limit=2, per_capability_limit=2,
            cancellation_reserve=1, reconciliation_reserve=1,
            verify_termination=lambda _: False,
            verify_resume_authority=lambda _op, _gen: True,
        )
        try:
            other.resume_after_shutdown(op, generation)
            other.fence(op, "service_shutdown")
        finally:
            other.close()
        return True

    latest.verify_resume_authority = overlapping_recovery
    with pytest.raises(PressureRejected, match="resume_state_conflict"):
        latest.resume_after_shutdown("durable", 1)
    after = latest.db.execute(
        "SELECT authority_epoch FROM pressure_operations WHERE operation_id='durable'"
    ).fetchone()[0]
    assert after > before
    assert not latest.publish_allowed("durable", 1)


def test_existing_operation_schema_upgrades_with_epoch(tmp_path):
    import sqlite3

    path = tmp_path / "pre-epoch.db"
    db = sqlite3.connect(str(path))
    db.execute(
        """CREATE TABLE pressure_operations(
        operation_id TEXT PRIMARY KEY, capability TEXT NOT NULL, generation INTEGER NOT NULL,
        authority TEXT NOT NULL, physical TEXT NOT NULL, reconciliation TEXT NOT NULL,
        reason TEXT NOT NULL)"""
    )
    db.execute("INSERT INTO pressure_operations VALUES ('old', 'cap', 1, 'fenced', 'running', 'required', 'service_shutdown')")
    db.commit()
    db.close()
    m = ExternalPressure(
        path, global_limit=2, detached_limit=2, per_capability_limit=2,
        cancellation_reserve=1, reconciliation_reserve=1,
        verify_termination=lambda _: False,
        verify_resume_authority=lambda _op, _gen: True,
    )
    assert m.db.execute("SELECT authority_epoch FROM pressure_operations WHERE operation_id='old'").fetchone() == (0,)
    m.resume_after_shutdown("old", 1)
    assert m.publish_allowed("old", 1)


def test_shutdown_fence_followed_by_supersession_revokes_resume(tmp_path):
    m = ExternalPressure(
        tmp_path / "revoke.db", global_limit=2, detached_limit=2,
        per_capability_limit=2, cancellation_reserve=2,
        reconciliation_reserve=2, verify_termination=lambda _: False,
        verify_resume_authority=lambda _op, _generation: True,
    )
    m.dispatch("job", "cap", 1)
    m.fence("job", "service_shutdown")
    epoch = m.db.execute("SELECT authority_epoch FROM pressure_operations").fetchone()[0]
    m.fence("job", "parent_superseded")
    assert m.db.execute("SELECT reason FROM pressure_operations").fetchone()[0] == "parent_superseded"
    assert m.db.execute("SELECT authority_epoch FROM pressure_operations").fetchone()[0] > epoch
    m.fence("job", "service_shutdown")
    with pytest.raises(PressureRejected, match="resume_state_conflict"):
        m.resume_after_shutdown("job", 1)
    assert not m.publish_allowed("job", 1)


def test_duplicate_control_ids_do_not_exhaust_safe_closure_capacity(tmp_path):
    m = ExternalPressure(
        tmp_path / "control.db", global_limit=3, detached_limit=3,
        per_capability_limit=3, cancellation_reserve=2,
        reconciliation_reserve=2, verify_termination=lambda _: False,
    )
    m.dispatch("a", "cap", 1)
    m.dispatch("b", "cap", 1)
    m.acquire_control("first", "a", "cancel")
    with pytest.raises(PressureRejected, match="active_control_already_reserved"):
        m.acquire_control("retry-different-id", "a", "cancel")
    m.acquire_control("second", "b", "cancel")
    assert m.doctor()["control_active"]["cancel"] == 2


def test_publication_decision_is_atomic_with_fence(tmp_path):
    digest = "sha256:" + "a" * 64
    m = ExternalPressure(
        tmp_path / "publish.db", global_limit=2, detached_limit=2,
        per_capability_limit=2, cancellation_reserve=1,
        reconciliation_reserve=1, verify_termination=lambda _: False,
    )
    m.dispatch("before", "cap", 1)
    receipt = m.commit_publication("before", 1, digest)
    assert receipt["generation"] == 1
    m.fence("before", "parent_superseded")
    assert m.commit_publication("before", 1, digest) == receipt
    with pytest.raises(PressureRejected, match="publication_id_conflict"):
        m.commit_publication("before", 1, "sha256:" + "b" * 64)
    m.dispatch("after", "cap", 2)
    m.fence("after", "parent_superseded")
    with pytest.raises(PressureRejected, match="publication_authority_stale"):
        m.commit_publication("after", 2, digest)
    assert m.db.execute("SELECT COUNT(*) FROM pressure_publications").fetchone()[0] == 1


def test_invalid_dispatch_identity_does_not_strand_pressure(tmp_path):
    m = manager(tmp_path / "text-only.db", set())
    with pytest.raises(PressureRejected, match="invalid_operation_identity"):
        m.dispatch(b"blob", "cap", 1)
    with pytest.raises(PressureRejected, match="invalid_operation_identity"):
        m.dispatch("op", b"blob", 1)
    assert m.doctor()["active"] == 0


def test_durable_control_idempotent_retry_after_restart(tmp_path):
    path = tmp_path / "recover-control.db"
    m = ExternalPressure(
        path, global_limit=2, detached_limit=2, per_capability_limit=2,
        cancellation_reserve=1, reconciliation_reserve=1,
        verify_termination=lambda _: False,
    )
    m.dispatch("op", "cap", 1)
    m.acquire_control("stable-cancel", "op", "cancel")
    m.close()
    resumed = ExternalPressure(
        path, global_limit=2, detached_limit=2, per_capability_limit=2,
        cancellation_reserve=1, reconciliation_reserve=1,
        verify_termination=lambda _: False,
    )
    resumed.acquire_control("stable-cancel", "op", "cancel")
    assert resumed.doctor()["control_active"]["cancel"] == 1
    with pytest.raises(PressureRejected, match="active_control_already_reserved"):
        resumed.acquire_control("different-request", "op", "cancel")
    resumed.release_control("stable-cancel")
    assert resumed.doctor()["control_active"]["cancel"] == 0


def test_duplicate_terminal_observation_skips_provider_probe(tmp_path):
    calls = []
    m = ExternalPressure(
        tmp_path / "terminal-repeat.db", global_limit=2, detached_limit=2,
        per_capability_limit=2, cancellation_reserve=1,
        reconciliation_reserve=1,
        verify_termination=lambda op: calls.append(op) or True,
    )
    m.dispatch("op", "cap", 1)
    m.observe("op", "stopped", reconciled=True)
    epoch = m.db.execute(
        "SELECT authority_epoch FROM pressure_operations WHERE operation_id='op'"
    ).fetchone()[0]
    m.observe("op", "stopped", reconciled=True)
    assert calls == ["op"]
    assert m.db.execute(
        "SELECT authority_epoch FROM pressure_operations WHERE operation_id='op'"
    ).fetchone() == (epoch,)
