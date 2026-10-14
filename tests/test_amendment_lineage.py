import pytest
import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "skills/mcp-steward-architect/tools/amendment_lineage.py"
spec = importlib.util.spec_from_file_location("amendment_lineage_ref", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
AmendmentLineage, AmendmentRejected = module.AmendmentLineage, module.AmendmentRejected


def store(tmp_path):
    return AmendmentLineage(tmp_path / 'lineage.db', lambda principal, lineage, op: ('host-policy' if lineage == 'l1' else 'policy') if principal == 'trusted' else None,
                            lambda: 'trusted')


def test_correction_supersession_and_retraction_preserve_audit(tmp_path):
    obj = store(tmp_path)
    first = obj.create(lineage_id='l1', record_id='r0', payload={'value': 1}, provenance={'source': 'p0'}, principal='trusted', authority_ref='host-policy')
    a = obj.amend(lineage_id='l1', operation_id='a', record_id='r1', expected_revision=0, operation='correct', reason='bad source', principal='trusted', authority_ref='host-policy', payload={'value': 2}, provenance={'source': 'p1'})
    assert a['effective'] == {'value': 2}
    assert obj.dependency_status('l1', first['effective_revision']) == 'RE_EVALUATION_REQUIRED'
    assert obj.amend(lineage_id='l1', operation_id='a', record_id='r1', expected_revision=0, operation='correct', reason='bad source', principal='trusted', authority_ref='host-policy', payload={'value': 2}, provenance={'source': 'p1'}) == a
    b = obj.amend(lineage_id='l1', operation_id='b', record_id='r2', expected_revision=1, operation='supersede', reason='new observation', principal='trusted', authority_ref='host-policy', payload={'value': 3}, provenance={'source': 'p2'})
    assert b['effective'] == {'value': 3}
    c = obj.amend(lineage_id='l1', operation_id='c', record_id='r3', expected_revision=2, operation='retract', reason='withdrawn', principal='trusted', authority_ref='host-policy')
    assert c['effective'] is None and c['status'] == 'retracted'
    assert [h['predecessor'] for h in obj.history('l1')] == [None, 'r0', 'r1', 'r2']
    assert obj.history('l1')[0]['provenance'] == {'source': 'p0'}
    obj.close()
    reopened = store(tmp_path)
    assert reopened.current('l1') == c
    with pytest.raises(Exception):
        reopened.db.execute("UPDATE amendments SET reason='tampered'")


def test_competing_cas_and_stale_and_unauthorized(tmp_path):
    obj = store(tmp_path)
    obj.create(lineage_id='l', record_id='r0', payload={'v': 0}, provenance={}, principal='trusted', authority_ref='policy')
    kwargs = dict(lineage_id='l', expected_revision=0, operation='correct', reason='fix', principal='trusted', authority_ref='policy', payload={'v': 1}, provenance={})
    obj.amend(operation_id='winning', record_id='r1', **kwargs)
    with pytest.raises(AmendmentRejected) as ex:
        obj.amend(operation_id='loser', record_id='r2', **kwargs)
    assert ex.value.reason == 'stale_revision' and ex.value.current_revision == 1
    with pytest.raises(AmendmentRejected) as ex:
        obj.amend(operation_id='winning', record_id='r1', **(kwargs | {'payload': {'v': 99}}))
    assert ex.value.reason == 'operation_id_conflict'
    with pytest.raises(AmendmentRejected) as ex:
        obj.amend(operation_id='spoof', record_id='r2', **(kwargs | {'principal': 'model'}))
    assert ex.value.reason == 'unauthorized'
    assert len(obj.history('l')) == 2


def test_adversarial_validation(tmp_path):
    obj = store(tmp_path)
    obj.create(lineage_id='l', record_id='r', payload={}, provenance={}, principal='trusted', authority_ref='policy')
    with pytest.raises(AmendmentRejected):
        obj.amend(lineage_id='l', operation_id='x', record_id='r2', expected_revision=True, operation='correct', reason='bad', principal='trusted', authority_ref='policy', payload={}, provenance={})
    with pytest.raises(AmendmentRejected):
        obj.amend(lineage_id='l', operation_id='x', record_id='r2', expected_revision=0, operation='retract', reason='withdraw', principal='trusted', authority_ref='policy', payload={})
    assert obj.current('l')['revision'] == 0


def test_real_profile_schema_requires_authority_when_feature_enabled():
    import json
    import yaml
    from jsonschema import Draft202012Validator

    root = Path(__file__).resolve().parents[1]
    schema = json.loads((root / 'contracts/steward-profile.schema.json').read_text())
    profile = yaml.safe_load((root / 'skills/mcp-steward-architect/templates/steward-profile.yaml.template').read_text())
    validator = Draft202012Validator(schema)
    # The generator replaces the placeholder ID; the schema doesn't require specific ID syntax.
    profile['features']['amendable_facts'] = True
    assert list(validator.iter_errors(profile)), 'must reject feature without policy'
    profile['amendment'] = {'mode': 'append_only', 'supported_operations': ['correct', 'retract', 'supersede'],
                            'authority_policy_ref': 'host-owned-amendments-policy', 'effective_revision_required': True}
    assert not list(validator.iter_errors(profile))
    profile['amendment']['authority_policy_ref'] = ''
    assert list(validator.iter_errors(profile))


def test_authority_reference_is_not_caller_issued(tmp_path):
    obj = store(tmp_path)
    with pytest.raises(AmendmentRejected, match='unauthorized'):
        obj.create(lineage_id='l', record_id='r', payload={}, provenance={}, principal='trusted', authority_ref='forged-policy')
    obj.create(lineage_id='l', record_id='r', payload={}, provenance={}, principal='trusted', authority_ref='policy')
    with pytest.raises(AmendmentRejected, match='unauthorized'):
        obj.amend(lineage_id='l', operation_id='a', record_id='r1', expected_revision=0, operation='correct', reason='fix', principal='trusted', authority_ref='forged-policy', payload={}, provenance={})


def test_initial_record_is_one_atomic_transaction(tmp_path):
    obj = store(tmp_path)
    obj.db.execute("CREATE TRIGGER inject_failure BEFORE INSERT ON amendments BEGIN SELECT RAISE(ABORT, 'synthetic_failure'); END")
    with pytest.raises(AmendmentRejected, match='create_persistence_conflict'):
        obj.create(lineage_id='l', record_id='r', payload={}, provenance={}, principal='trusted', authority_ref='policy')
    assert obj.db.execute("SELECT COUNT(*) FROM lineage").fetchone()[0] == 0
    assert obj.db.execute("SELECT COUNT(*) FROM amendments").fetchone()[0] == 0


def test_principal_text_cannot_impersonate_trusted_identity(tmp_path):
    path = tmp_path / 'identity.db'
    evaluator = lambda principal, lineage, op: 'policy' if principal == 'trusted' else None
    unprivileged = AmendmentLineage(path, evaluator, lambda: 'model')
    with pytest.raises(AmendmentRejected, match='unauthorized'):
        unprivileged.create(lineage_id='l', record_id='r0', payload={}, provenance={}, principal='trusted', authority_ref='policy')
    assert unprivileged.db.execute('SELECT COUNT(*) FROM lineage').fetchone()[0] == 0

def test_exact_replay_after_later_amendment_returns_original_result(tmp_path):
    obj = store(tmp_path)
    create = dict(
        lineage_id="l1", record_id="r0", payload={"v": 0},
        provenance={"source": "s0"}, principal="trusted", authority_ref="host-policy",
    )
    first = obj.create(**create)
    a = obj.amend(
        lineage_id="l1", operation_id="a", record_id="r1",
        expected_revision=0, operation="correct", reason="correct",
        principal="trusted", authority_ref="host-policy",
        payload={"v": 1}, provenance={"source": "s1"},
    )
    b = obj.amend(
        lineage_id="l1", operation_id="b", record_id="r2",
        expected_revision=1, operation="supersede", reason="replace",
        principal="trusted", authority_ref="host-policy",
        payload={"v": 2}, provenance={"source": "s2"},
    )
    replay_initial = obj.create(**create)
    assert replay_initial["effective_revision"] == first["effective_revision"]
    assert replay_initial["status"] == "superseded" and not replay_initial["is_current"]
    replay_a = obj.amend(
        lineage_id="l1", operation_id="a", record_id="r1",
        expected_revision=0, operation="correct", reason="correct",
        principal="trusted", authority_ref="host-policy",
        payload={"v": 1}, provenance={"source": "s1"},
    )
    assert replay_a["effective_revision"] == a["effective_revision"]
    assert replay_a["status"] == "superseded" and not replay_a["is_current"]
    assert obj.current("l1") == b
    with pytest.raises(AmendmentRejected, match="create_persistence_conflict"):
        obj.create(**(create | {"payload": {"v": 999}}))


def test_lineage_ids_reject_coercion_and_read_disclosure_requires_host_grant(tmp_path):
    policy = {"read_current", "read_history", "create", "correct"}
    obj = AmendmentLineage(
        tmp_path / "reads.db",
        lambda principal, lineage, action: "policy" if action in policy and principal == "trusted" else None,
        lambda: "trusted",
    )
    with pytest.raises(AmendmentRejected, match="invalid_lineage_id"):
        obj.create(lineage_id=1, record_id="r", payload={}, provenance={}, principal="trusted", authority_ref="policy")
    obj.create(lineage_id="l", record_id="r", payload={"secret": True}, provenance={}, principal="trusted", authority_ref="policy")
    before = obj.current("l")["effective_revision"]
    with pytest.raises(AmendmentRejected, match="invalid_lineage_id"):
        obj.current(1)
    assert obj.current("l")["effective_revision"] == before
    policy.remove("read_current")
    with pytest.raises(AmendmentRejected, match="read_unauthorized"):
        obj.current("l")
    policy.remove("read_history")
    with pytest.raises(AmendmentRejected, match="read_unauthorized"):
        obj.history("l")


def test_sqlite_busy_write_is_a_typed_refusal(tmp_path):
    import sqlite3

    path = tmp_path / "locked.db"
    obj = AmendmentLineage(path, lambda *_: "policy", lambda: "trusted")
    obj.db.execute("PRAGMA busy_timeout=1")
    blocker = sqlite3.connect(str(path), timeout=1, isolation_level=None)
    blocker.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(AmendmentRejected, match="writer_busy"):
            obj.create(lineage_id="l", record_id="r", payload={}, provenance={},
                       principal="trusted", authority_ref="policy")
    finally:
        blocker.execute("ROLLBACK")
        blocker.close()

def test_write_grant_revoked_during_writer_wait_fails_closed(tmp_path):
    allowed = {"create", "correct", "read_current", "read_history"}
    obj = AmendmentLineage(
        tmp_path / "race.db",
        lambda principal, lineage, action: "policy" if action in allowed else None,
        lambda: "trusted",
    )
    real_begin = obj._begin

    def revoked_begin():
        real_begin()
        allowed.discard("create")

    obj._begin = revoked_begin
    with pytest.raises(AmendmentRejected, match="unauthorized"):
        obj.create(lineage_id="l", record_id="r", payload={}, provenance={},
                   principal="trusted", authority_ref="policy")
    assert obj.db.execute("SELECT COUNT(*) FROM lineage").fetchone()[0] == 0
    allowed.add("create")
    obj._begin = real_begin
    obj.create(lineage_id="l", record_id="r", payload={}, provenance={},
               principal="trusted", authority_ref="policy")

    def revoked_amend_begin():
        real_begin()
        allowed.discard("correct")

    obj._begin = revoked_amend_begin
    with pytest.raises(AmendmentRejected, match="unauthorized"):
        obj.amend(
            lineage_id="l", operation_id="a", record_id="r1", expected_revision=0,
            operation="correct", reason="correction", principal="trusted",
            authority_ref="policy", payload={"v": 1}, provenance={},
        )
    assert obj.current("l")["revision"] == 0


def test_mapping_normalization_and_invalid_payload_are_typed(tmp_path):
    from collections import UserDict
    from types import MappingProxyType

    obj = store(tmp_path)
    obj.create(
        lineage_id="l1", record_id="r", payload=UserDict({"v": 1}),
        provenance=MappingProxyType({"source": "ok"}),
        principal="trusted", authority_ref="host-policy",
    )
    amended = obj.amend(
        lineage_id="l1", operation_id="a", record_id="r1", expected_revision=0,
        operation="correct", reason="change", principal="trusted",
        authority_ref="host-policy", payload=UserDict({"v": 2}),
        provenance=MappingProxyType({"source": "ok"}),
    )
    assert amended["effective"] == {"v": 2}
    with pytest.raises(AmendmentRejected, match="invalid_payload"):
        obj.amend(
            lineage_id="l1", operation_id="bad", record_id="r2", expected_revision=1,
            operation="correct", reason="invalid", principal="trusted",
            authority_ref="host-policy", payload={"nan": float("nan")}, provenance={},
        )


def test_history_pagination_is_bounded_and_cursor_stable(tmp_path):
    obj = store(tmp_path)
    obj.create(lineage_id="l1", record_id="r0", payload={}, provenance={},
               principal="trusted", authority_ref="host-policy")
    for rev in range(1, 26):
        obj.amend(
            lineage_id="l1", operation_id=f"op{rev}", record_id=f"r{rev}",
            expected_revision=rev - 1, operation="supersede", reason="update",
            principal="trusted", authority_ref="host-policy",
            payload={"rev": rev}, provenance={},
        )
    first = obj.history("l1")
    assert len(first) == 20 and [x["revision"] for x in first] == list(range(20))
    second = obj.history("l1", after_revision=19, limit=20)
    assert [x["revision"] for x in second] == list(range(20, 26))
    with pytest.raises(AmendmentRejected, match="invalid_history_page"):
        obj.history("l1", limit=10_000)

def test_sqlite_write_failure_translates_to_typed_refusal(tmp_path):
    obj = store(tmp_path)
    obj.create(lineage_id="l1", record_id="r0", payload={}, provenance={},
               principal="trusted", authority_ref="host-policy")
    obj.db.execute(
        """CREATE TRIGGER fail_write BEFORE INSERT ON amendments
        BEGIN SELECT RAISE(ABORT, 'synthetic_failure'); END"""
    )
    with pytest.raises(AmendmentRejected, match="amend_persistence_failure"):
        obj.amend(
            lineage_id="l1", operation_id="new", record_id="r1", expected_revision=0,
            operation="correct", reason="repair", payload={"v": 1}, provenance={},
            principal="trusted", authority_ref="host-policy",
        )
    assert obj.current("l1")["revision"] == 0


def test_amendment_opt_in_catalog_application():
    import yaml
    from contracts.rule_applicability import RuleContext, expected_rules

    root = Path(__file__).resolve().parents[1]
    catalog = yaml.safe_load((root / "contracts/rule-catalog.yaml").read_text(encoding="utf-8"))
    rule_id = "steward.amendment.append-only"
    assert rule_id not in {
        r["id"] for r in expected_rules(catalog, "mcp-steward-architect", RuleContext("L1"))
    }
    assert rule_id in {
        r["id"] for r in expected_rules(
            catalog, "mcp-steward-architect",
            RuleContext("L1", profiles=frozenset({"amendable-facts"})),
        )
    }


def test_current_uses_single_snapshot_for_head_and_amendment(tmp_path):
    obj = store(tmp_path)
    obj.create(
        lineage_id="l1", record_id="r0", payload={"v": 0}, provenance={},
        principal="trusted", authority_ref="host-policy",
    )
    queries = []
    obj.db.set_trace_callback(lambda sql: queries.append(sql) if sql.lstrip().upper().startswith("SELECT") else None)
    try:
        assert obj.current("l1")["is_current"]
        assert len(queries) == 1
        assert "JOIN amendments" in queries[0]
        queries.clear()
        assert obj.dependency_status("l1", obj.current("l1")["effective_revision"]) == "CURRENT"
        assert len(queries) == 2
    finally:
        obj.db.set_trace_callback(None)


def test_nested_payload_mutation_during_writer_wait_cannot_change_fingerprint(tmp_path):
    obj = store(tmp_path)
    obj.create(
        lineage_id="l1", record_id="r0", payload={}, provenance={},
        principal="trusted", authority_ref="host-policy",
    )
    nested = {"items": [{"v": 1}]}
    provenance = {"ids": [1]}
    real_begin = obj._begin

    def mutate_while_waiting():
        nested["items"][0]["v"] = 999
        provenance["ids"].append(2)
        real_begin()

    obj._begin = mutate_while_waiting
    saved = obj.amend(
        lineage_id="l1", operation_id="a", record_id="r1", expected_revision=0,
        operation="correct", reason="first", principal="trusted",
        authority_ref="host-policy", payload=nested, provenance=provenance,
    )
    assert saved["effective"] == {"items": [{"v": 1}]}
    assert saved["provenance"] == {"ids": [1]}
    obj._begin = real_begin
    replay = obj.amend(
        lineage_id="l1", operation_id="a", record_id="r1", expected_revision=0,
        operation="correct", reason="first", principal="trusted",
        authority_ref="host-policy", payload={"items": [{"v": 1}]}, provenance={"ids": [1]},
    )
    assert replay["effective_revision"] == saved["effective_revision"]


def test_sqlite_revision_integer_overflow_is_typed_rejection(tmp_path):
    obj = store(tmp_path)
    obj.create(
        lineage_id="l1", record_id="r0", payload={}, provenance={},
        principal="trusted", authority_ref="host-policy",
    )
    above_sqlite = 1 << 63
    with pytest.raises(AmendmentRejected, match="invalid_expected_revision"):
        obj.amend(
            lineage_id="l1", operation_id="overflow", record_id="r1",
            expected_revision=above_sqlite, operation="correct",
            reason="test", principal="trusted", authority_ref="host-policy",
            payload={}, provenance={},
        )
    with pytest.raises(AmendmentRejected, match="invalid_history_page"):
        obj.history("l1", after_revision=above_sqlite)
    assert obj.current("l1")["revision"] == 0

def test_deep_json_mapping_returns_typed_refusal(tmp_path):
    obj = store(tmp_path)
    nested = {}
    current = nested
    for _ in range(1500):
        following = {}
        current["child"] = following
        current = following
    with pytest.raises(AmendmentRejected, match="invalid_payload"):
        obj.create(
            lineage_id="l1", record_id="r", payload=nested, provenance={},
            principal="trusted", authority_ref="host-policy",
        )
    obj.create(
        lineage_id="l1", record_id="r0", payload={}, provenance={},
        principal="trusted", authority_ref="host-policy",
    )
    with pytest.raises(AmendmentRejected, match="invalid_provenance"):
        obj.amend(
            lineage_id="l1", operation_id="deep", record_id="r1", expected_revision=0,
            operation="correct", reason="deep", principal="trusted",
            authority_ref="host-policy", payload={}, provenance=nested,
        )

def test_nested_json_depth_policy_does_not_depend_on_python_version(tmp_path):
    obj = store(tmp_path)
    payload = {}
    head = payload
    for _ in range(32):
        nxt = {"child": {}}
        head["child"] = nxt
        head = nxt
    created = obj.create(
        lineage_id="l1", record_id="r0", payload=payload, provenance={},
        principal="trusted", authority_ref="host-policy",
    )
    assert created["is_current"]
    too_deep = {}
    head = too_deep
    for _ in range(65):
        child = {}
        head["child"] = child
        head = child
    with pytest.raises(AmendmentRejected, match="invalid_payload"):
        obj.amend(
            lineage_id="l1", operation_id="deep", record_id="r1",
            expected_revision=0, operation="correct", reason="too deep",
            principal="trusted", authority_ref="host-policy",
            payload=too_deep, provenance={},
        )
