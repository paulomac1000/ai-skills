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
    return AmendmentLineage(tmp_path / 'lineage.db', lambda principal, lineage, op: principal == 'trusted')


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