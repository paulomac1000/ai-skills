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
