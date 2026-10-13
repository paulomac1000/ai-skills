from pathlib import Path
import importlib.util
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "skills/skill-architect/tools/check_refactor_preservation.py"
spec = importlib.util.spec_from_file_location("check_refactor_preservation_165", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
assess = mod.assess


def case(tmp_path, kind='authority'):
    skill = tmp_path/'skill'
    skill.mkdir()
    (skill/'SKILL.md').write_text('Trigger when destructive action requested; enforce policy before action')
    (skill/'STANDARD.md').write_text('Require policy authorization; retain rollback evidence')
    baseline = {'revision': 'base-sha', 'required_behaviors': [{'id': 'auth', 'kind': kind}]}
    decision = {'id': 'auth', 'disposition': 'MOVE', 'target_path': 'STANDARD.md', 'target_anchor': 'Require policy authorization', 'negative_case': 'unauthorized_call', 'verification': 'negative-test', 'pre_load_path': 'SKILL.md', 'pre_load_trigger': 'Trigger when destructive action'}
    ledger = {'candidate_revision': 'candidate-sha', 'decisions': [decision]}
    return skill, baseline, ledger, decision


def test_omitted_authority_rule_fails_even_with_static_package(tmp_path):
    path, baseline, ledger, decision = case(tmp_path)
    ledger['decisions'] = []
    assert 'missing_required_behavior:auth' in assess(baseline, ledger, path)['findings']
    ledger['decisions'] = [decision | {'disposition': 'REMOVE_WITH_REASON', 'reason': 'shorter'}]
    assert 'required_behavior_removed:auth' in assess(baseline, ledger, path)['findings']


def test_reachable_deduplication_passes_structural_not_behavior(tmp_path):
    path, baseline, ledger, decision = case(tmp_path)
    ledger['decisions'] = [decision | {'disposition': 'REPLACE_BY_CANONICAL_OWNER'}]
    result = assess(baseline, ledger, path)
    assert result['structural'] == 'PASS' and result['behavior'] == 'BEHAVIOR_NOT_VERIFIED'


def test_wrong_illustrative_command_has_no_verified_owner(tmp_path):
    path, baseline, ledger, decision = case(tmp_path)
    ledger['decisions'] = [decision | {'target_anchor': 'unsupported-tool --magic'}]
    assert 'anchor_not_present:auth' in assess(baseline, ledger, path)['findings']


def test_preload_route_lost(tmp_path):
    path, baseline, ledger, decision = case(tmp_path)
    (path/'SKILL.md').write_text('No discoverable trigger')
    assert 'preload_trigger_unreachable:auth' in assess(baseline, ledger, path)['findings']


def test_independent_profiles_not_forcibly_merged(tmp_path):
    path, baseline, ledger, decision = case(tmp_path)
    (path/'references').mkdir()
    (path/'references/p1.md').write_text('first independent route')
    (path/'references/p2.md').write_text('second independent route')
    baseline['required_behaviors'] = [{'id': 'p1', 'kind': 'evidence'}, {'id': 'p2', 'kind': 'evidence'}]
    ledger['decisions'] = [
        {'id': key, 'disposition': 'PRESERVE', 'target_path': f'references/{key}.md', 'target_anchor': f'{word} independent route', 'negative_case': 'other-task', 'verification': key}
        for key, word in [('p1', 'first'), ('p2', 'second')]
    ]
    assert assess(baseline, ledger, path)['structural'] == 'PASS'


def test_structural_green_does_not_claim_model_equivalence(tmp_path):
    path, baseline, ledger, decision = case(tmp_path)
    assert assess(baseline, ledger, path)['behavior'] == 'BEHAVIOR_NOT_VERIFIED'