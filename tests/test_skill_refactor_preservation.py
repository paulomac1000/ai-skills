import hashlib
import importlib.util
import json
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "skills/skill-architect/tools/check_refactor_preservation.py"
spec = importlib.util.spec_from_file_location("check_refactor_preservation_165", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
def assess(baseline, ledger, path, *, baseline_tree=None):
    return mod.assess(baseline, ledger, path, baseline_tree=baseline_tree or path)


def case(tmp_path, kind='authority'):
    skill = tmp_path/'skill'
    skill.mkdir()
    (skill/'SKILL.md').write_text(
        'Trigger when destructive action requested; read STANDARD.md before action'
    )
    (skill/'STANDARD.md').write_text('Require policy authorization; retain rollback evidence')
    baseline = {'revision': 'a' * 40, 'required_behaviors': [{'id': 'auth', 'kind': kind}]}
    decision = {'id': 'auth', 'disposition': 'MOVE', 'target_path': 'STANDARD.md', 'target_anchor': 'Require policy authorization', 'negative_case': 'unauthorized_call', 'verification': 'negative-test', 'pre_load_path': 'SKILL.md', 'pre_load_trigger': 'Trigger when destructive action'}
    def blob(path):
        raw = (skill / path).read_bytes()
        return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()

    decision['entrypoint_route'] = 'Trigger when destructive action requested; read STANDARD.md'
    decision['source_path'] = 'STANDARD.md'
    decision['source_anchor'] = 'Require policy authorization'
    decision['positive_case'] = 'authorized_operation'
    ledger = {
        'candidate_revision': 'candidate-sha',
        'baseline_sha256': 'sha256:' + hashlib.sha256(
            json.dumps(baseline, sort_keys=True, separators=(',', ':')).encode()
        ).hexdigest(),
        'candidate_files': {'SKILL.md': blob('SKILL.md'), 'STANDARD.md': blob('STANDARD.md')},
        'baseline_source_blobs': {'STANDARD.md': blob('STANDARD.md')},
        'decisions': [decision],
    }
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
    (path/'SKILL.md').write_text(
        'Trigger when destructive action requested; read STANDARD.md before action\n'
        'first independent route -> references/p1.md\n'
        'second independent route -> references/p2.md'
    )
    raw_skill = (path / 'SKILL.md').read_bytes()
    ledger['candidate_files']['SKILL.md'] = mod._git_blob_sha(raw_skill)
    baseline['required_behaviors'] = [{'id': 'p1', 'kind': 'evidence'}, {'id': 'p2', 'kind': 'evidence'}]
    ledger['decisions'] = [
        {'id': key, 'disposition': 'PRESERVE', 'target_path': f'references/{key}.md', 'target_anchor': f'{word} independent route', 'negative_case': 'other-task', 'verification': key, 'source_path': f'references/{key}.md', 'source_anchor': f'{word} independent route', 'positive_case': key, 'pre_load_trigger': f'{word} independent route', 'entrypoint_route': f'{word} independent route -> references/{key}.md'}
        for key, word in [('p1', 'first'), ('p2', 'second')]
    ]
    ledger['baseline_sha256'] = 'sha256:' + hashlib.sha256(
        json.dumps(baseline, sort_keys=True, separators=(',', ':')).encode()
    ).hexdigest()
    for key in ('p1', 'p2'):
        raw = (path / f'references/{key}.md').read_bytes()
        ledger['candidate_files'][f'references/{key}.md'] = hashlib.sha1(
            b"blob " + str(len(raw)).encode() + b"\0" + raw, usedforsecurity=False
        ).hexdigest()
        ledger['baseline_source_blobs'][f'references/{key}.md'] = ledger['candidate_files'][f'references/{key}.md']
    assert assess(baseline, ledger, path)['structural'] == 'PASS'


def test_structural_green_does_not_claim_model_equivalence(tmp_path):
    path, baseline, ledger, decision = case(tmp_path)
    assert assess(baseline, ledger, path)['behavior'] == 'BEHAVIOR_NOT_VERIFIED'

def test_real_pilot_tracks_live_normative_sources():
    root = Path(__file__).resolve().parents[1]
    corpus = root / "evals/skills/skill-architect"
    baseline = json.loads((corpus / "refactor-pilot-baseline.json").read_text(encoding="utf-8"))
    ledger = json.loads((corpus / "refactor-pilot-ledger.json").read_text(encoding="utf-8"))
    result = assess(
        baseline, ledger, root / "skills/skill-architect",
        baseline_tree=corpus / "baseline_snapshots",
    )
    assert result["structural"] == "PASS", result["findings"]
    assert result["behavior"] == "BEHAVIOR_NOT_VERIFIED"
    assert result["baseline_revision"] == "5c656ac0602e35f51cb0ba9b576f8e5af10a54ba"
    assert result["candidate_revision"] == "3.26.0"

def test_content_drift_cannot_pass_a_pinned_pilot(tmp_path):
    path, baseline, ledger, decision = case(tmp_path)
    assert assess(baseline, ledger, path)['structural'] == 'PASS'
    (path / 'STANDARD.md').write_text('Require policy authorization; retain rollback evidence\n')
    assert 'candidate_content_mismatch:STANDARD.md' in assess(baseline, ledger, path)['findings']
    (path / 'STANDARD.md').write_text('Require policy authorization; retain rollback evidence')
    baseline['required_behaviors'][0]['kind'] = 'exception'
    assert 'baseline_content_mismatch' in assess(baseline, ledger, path)['findings']


def test_invalid_input_returns_json_and_exit_code_two(tmp_path):
    import subprocess

    invalid = tmp_path / 'invalid.json'
    invalid.write_text('{broken')
    candidate = tmp_path / 'skill'
    candidate.mkdir()
    result = subprocess.run(
        [sys.executable, str(MODULE_PATH), '--baseline', str(invalid),
         '--ledger', str(invalid), '--candidate', str(candidate)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)['structural'] == 'INVALID_INPUT'

def test_critical_route_cannot_move_out_of_skill_entrypoint(tmp_path):
    path, baseline, ledger, decision = case(tmp_path)
    ledger["decisions"] = [decision | {"pre_load_path": "STANDARD.md", "pre_load_trigger": "Require policy authorization"}]
    assert "critical_preload_not_in_skill_entrypoint:auth" in assess(baseline, ledger, path)["findings"]


def test_missing_old_owner_or_positive_case_never_passes(tmp_path):
    path, baseline, ledger, decision = case(tmp_path)
    ledger["decisions"] = [decision | {"positive_case": ""}]
    assert "incomplete_old_to_new_mapping:auth" in assess(baseline, ledger, path)["findings"]
    ledger["decisions"] = [decision | {"source_path": "untrusted.md"}]
    assert "incomplete_old_to_new_mapping:auth" in assess(baseline, ledger, path)["findings"]


def test_pinned_baseline_snapshot_is_not_self_authorizing(tmp_path):
    path, baseline, ledger, decision = case(tmp_path)
    assert assess(baseline, ledger, path)["structural"] == "PASS"
    raw = (path / "STANDARD.md").read_text()
    (path / "STANDARD.md").write_text(raw + "\n")
    assert "baseline_source_drift:STANDARD.md" in assess(baseline, ledger, path)["findings"]
    assert "baseline_source_unverified" in mod.assess(baseline, ledger, path)["findings"]


def test_pilot_revision_resolves_against_actual_git_history():
    root = Path(__file__).resolve().parents[1]
    corpus = root / "evals/skills/skill-architect"
    baseline = json.loads((corpus / "refactor-pilot-baseline.json").read_text(encoding="utf-8"))
    ledger = json.loads((corpus / "refactor-pilot-ledger.json").read_text(encoding="utf-8"))
    import pytest
    import subprocess

    # Other CI matrix jobs use shallow checkouts; exact-head fetches BASE_SHA
    # and runs this verification with real immutable Git history.
    present = subprocess.run(
        ["git", "-C", str(root), "cat-file", "-e", baseline["revision"] + "^{commit}"],
        check=False, capture_output=True, timeout=10,
    )
    if present.returncode != 0:
        pytest.skip("baseline object absent from shallow checkout")
    assert mod._verify_baseline_git_revision(baseline, ledger, root / "skills/skill-architect") == []
    bad = dict(ledger, baseline_source_tree_sha="0" * 40)
    assert mod._verify_baseline_git_revision(baseline, bad, root / "skills/skill-architect") == [
        "baseline_git_tree_mismatch"
    ]


def test_unknown_material_class_cannot_be_structurally_approved(tmp_path):
    path, baseline, ledger, _ = case(tmp_path)
    baseline["required_behaviors"][0]["kind"] = "safety-stop"
    ledger["baseline_sha256"] = "sha256:" + hashlib.sha256(
        json.dumps(baseline, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert "unsupported_behavior_class:auth" in assess(baseline, ledger, path)["findings"]


def test_target_reference_route_must_survive_even_with_refreshed_hash(tmp_path):
    path, baseline, ledger, decision = case(tmp_path)
    assert assess(baseline, ledger, path)["structural"] == "PASS"
    # Keep the trigger visible but remove the conditional route to its owner.
    (path / "SKILL.md").write_text("Trigger when destructive action requested; enforce policy before action")
    ledger["candidate_files"]["SKILL.md"] = mod._git_blob_sha((path / "SKILL.md").read_bytes())
    findings = assess(baseline, ledger, path)["findings"]
    assert "owner_route_unreachable:auth" in findings
    assert "candidate_content_mismatch:SKILL.md" not in findings


def test_noncritical_evidence_owner_route_is_also_required(tmp_path):
    path, baseline, ledger, decision = case(tmp_path, kind="evidence")
    assert assess(baseline, ledger, path)["structural"] == "PASS"
    ledger["decisions"] = [decision | {"entrypoint_route": "Trigger when destructive action requested"}]
    assert "owner_route_unreachable:auth" in assess(baseline, ledger, path)["findings"]

def test_reference_route_rejects_unbound_entrypoint(tmp_path):
    path, baseline, ledger, decision = case(tmp_path, kind="evidence")
    assert assess(baseline, ledger, path)["structural"] == "PASS"
    ledger["candidate_files"].pop("SKILL.md")
    findings = assess(baseline, ledger, path)["findings"]
    assert "owner_entrypoint_unbound:auth" in findings
    assert "candidate_content_mismatch:SKILL.md" not in findings


def test_reference_route_rejects_changed_entrypoint_even_with_live_route(tmp_path):
    path, baseline, ledger, decision = case(tmp_path, kind="evidence")
    assert assess(baseline, ledger, path)["structural"] == "PASS"
    (path / "SKILL.md").write_text(
        "Trigger when destructive action requested; read STANDARD.md before action, unauthorized update"
    )
    assert "owner_entrypoint_unbound:auth" in assess(baseline, ledger, path)["findings"]

def test_malformed_candidate_file_inventory_returns_structured_refusal(tmp_path):
    path, baseline, ledger, decision = case(tmp_path, kind="evidence")
    for invalid in (None, [], ["SKILL.md"], "SKILL.md", 123):
        ledger["candidate_files"] = invalid
        result = assess(baseline, ledger, path)
        assert result["structural"] == "FAILED"
        assert "candidate_files_missing" in result["findings"]
        assert "owner_entrypoint_unbound:auth" in result["findings"]

def test_duplicate_baseline_behavior_ids_are_rejected(tmp_path):
    path, baseline, ledger, decision = case(tmp_path)
    baseline["required_behaviors"].append(dict(baseline["required_behaviors"][0]))
    ledger["baseline_sha256"] = "sha256:" + hashlib.sha256(
        json.dumps(baseline, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    findings = assess(baseline, ledger, path)["findings"]
    assert "duplicate_baseline_rule:auth" in findings


def test_structural_pass_does_not_certify_eval_corpus(tmp_path):
    path, baseline, ledger, decision = case(tmp_path)
    result = assess(baseline, ledger, path)
    assert result["structural"] == "PASS"
    assert result["verification_scope"] == "normative_owner_and_route_mapping"
    assert result["eval_corpus"] == "NOT_VERIFIED"
    assert result["behavior"] == "BEHAVIOR_NOT_VERIFIED"


def test_argparse_failures_emit_bounded_json_and_exit_two(tmp_path):
    import subprocess

    for extra in ([], ["--unrecognized"], ["--baseline"]):
        proc = subprocess.run(
            [sys.executable, str(MODULE_PATH), *extra],
            capture_output=True, text=True, check=False,
        )
        assert proc.returncode == 2
        response = json.loads(proc.stdout)
        assert response["structural"] == "INVALID_INPUT"
        assert response["findings"] == ["invalid_arguments"]

def test_candidate_owned_git_cannot_substitute_trusted_baseline(tmp_path):
    import subprocess

    root = Path(__file__).resolve().parents[1]
    corpus = root / "evals/skills/skill-architect"
    baseline = json.loads((corpus / "refactor-pilot-baseline.json").read_text(encoding="utf-8"))
    ledger = json.loads((corpus / "refactor-pilot-ledger.json").read_text(encoding="utf-8"))
    trusted = subprocess.run(
        ["git", "-C", str(root), "cat-file", "-e", baseline["revision"] + "^{commit}"],
        check=False, capture_output=True, timeout=10,
    )
    if trusted.returncode != 0:
        import pytest

        pytest.skip("baseline Git object absent from shallow checkout")
    foreign = tmp_path / "foreign-skill"
    foreign.mkdir()
    subprocess.run(["git", "init", "-q", str(foreign)], check=True, timeout=10)
    assert mod._verify_baseline_git_revision(baseline, ledger, foreign) == [
        "candidate_outside_trusted_repo"
    ]
    real_skill = root / "skills/skill-architect"
    assert mod._verify_baseline_git_revision(baseline, ledger, real_skill) == []
    bogus = dict(ledger, baseline_source_tree_sha="0" * 40)
    assert mod._verify_baseline_git_revision(baseline, bogus, real_skill) == [
        "baseline_git_tree_mismatch"
    ]

def test_historical_git_resolution_tracks_selected_trusted_skill():
    import pytest
    import subprocess

    root = Path(__file__).resolve().parents[1]
    base = "5c656ac0602e35f51cb0ba9b576f8e5af10a54ba"
    probe = subprocess.run(
        ["git", "-C", str(root), "cat-file", "-e", base + "^{commit}"],
        check=False, capture_output=True, timeout=10,
    )
    if probe.returncode != 0:
        pytest.skip("baseline object unavailable in shallow checkout")

    def rev(rev_spec):
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", rev_spec],
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout.strip()

    target = root / "skills/mcp-steward-architect"
    baseline = {"revision": base}
    ledger = {
        "baseline_source_tree_sha": rev(base + ":skills/mcp-steward-architect"),
        "baseline_source_blobs": {
            "SKILL.md": rev(base + ":skills/mcp-steward-architect/SKILL.md")
        },
    }
    assert mod._verify_baseline_git_revision(baseline, ledger, target) == []
    assert mod._verify_baseline_git_revision(baseline, ledger, root) == [
        "candidate_not_skill_directory"
    ]

def test_cli_rejects_non_object_candidate_files_with_typed_exit(tmp_path):
    import subprocess

    path, baseline, ledger, _ = case(tmp_path)
    baseline_path = tmp_path / "baseline.json"
    ledger_path = tmp_path / "ledger.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    for malformed in (None, [], ["SKILL.md"], "SKILL.md", 123):
        ledger_path.write_text(
            json.dumps({**ledger, "candidate_files": malformed}), encoding="utf-8"
        )
        proc = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--baseline",
                str(baseline_path),
                "--ledger",
                str(ledger_path),
                "--candidate",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 2
        assert json.loads(proc.stdout)["structural"] == "INVALID_INPUT"
        assert "Traceback" not in proc.stderr

def test_cli_rejects_fifo_and_character_device_before_reading(tmp_path):
    import os
    import pytest
    import subprocess

    if not hasattr(os, "mkfifo"):
        pytest.skip("FIFO unsupported")
    path, baseline, ledger, _ = case(tmp_path)
    fifo = tmp_path / "untrusted.fifo"
    os.mkfifo(fifo)
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    inputs = [fifo]
    if Path("/dev/zero").exists():
        inputs.append(Path("/dev/zero"))
    for bad_input in inputs:
        proc = subprocess.run(
            [
                sys.executable, str(MODULE_PATH), "--baseline", str(bad_input),
                "--ledger", str(ledger_path), "--candidate", str(path),
            ],
            capture_output=True, text=True, timeout=5, check=False,
        )
        assert proc.returncode == 2
        assert json.loads(proc.stdout)["structural"] == "INVALID_INPUT"
        assert "Traceback" not in proc.stderr


def test_cli_oversized_regular_file_is_rejected_before_json_parse(tmp_path):
    import subprocess

    path, baseline, ledger, _ = case(tmp_path)
    large = tmp_path / "too-large.json"
    large.write_bytes(b"{" + b" " * 262144 + b"}")
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable, str(MODULE_PATH), "--baseline", str(large),
            "--ledger", str(ledger_path), "--candidate", str(path),
        ],
        capture_output=True, text=True, timeout=5, check=False,
    )
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["structural"] == "INVALID_INPUT"


def test_candidate_symlink_cannot_impersonate_a_pinned_blob(tmp_path):
    import pytest

    path, baseline, ledger, decision = case(tmp_path, kind="evidence")
    real = path / "STANDARD.md"
    alias = path / "reference.md"
    try:
        alias.symlink_to(real.name)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable on this host")
    ledger["candidate_files"]["reference.md"] = ledger["candidate_files"]["STANDARD.md"]
    assert "candidate_symlink_rejected:reference.md" in assess(baseline, ledger, path)["findings"]
    ledger["decisions"] = [
        decision | {"target_path": "reference.md", "entrypoint_route": "Trigger when destructive action requested; read reference.md"}
    ]
    assert "candidate_symlink_rejected:reference.md" in assess(baseline, ledger, path)["findings"]


def test_duplicate_json_keys_produce_structured_invalid_input(tmp_path):
    import subprocess

    path, baseline, ledger, decision = case(tmp_path)
    baseline_file = tmp_path / "base.json"
    ledger_file = tmp_path / "ledger.json"
    for broken_baseline, broken_ledger in (
        ('{"revision":"a","revision":"b","required_behaviors":[]}', json.dumps(ledger)),
        (json.dumps(baseline), '{"candidate_files":{},"candidate_files":{}}'),
    ):
        baseline_file.write_text(broken_baseline, encoding="utf-8")
        ledger_file.write_text(broken_ledger, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--baseline", str(baseline_file),
             "--ledger", str(ledger_file), "--candidate", str(path)],
            capture_output=True, text=True, check=False,
        )
        assert result.returncode == 2
        response = json.loads(result.stdout)
        assert response["structural"] == "INVALID_INPUT"
        assert "invalid_input:ValueError" in response["findings"]


def test_baseline_git_revision_must_be_commit(tmp_path):
    root = Path(__file__).resolve().parents[1]
    corpus = root / "evals/skills/skill-architect"
    baseline = json.loads((corpus / "refactor-pilot-baseline.json").read_text(encoding="utf-8"))
    ledger = json.loads((corpus / "refactor-pilot-ledger.json").read_text(encoding="utf-8"))
    import subprocess
    import pytest

    available = subprocess.run(
        ["git", "-C", str(root), "cat-file", "-e", baseline["revision"] + "^{commit}"],
        capture_output=True, check=False, timeout=10,
    )
    if available.returncode != 0:
        pytest.skip("base Git object unavailable in shallow checkout")
    source = subprocess.run(
        ["git", "-C", str(root), "rev-parse", baseline["revision"] + "^{tree}"],
        check=True, capture_output=True, text=True, timeout=10,
    ).stdout.strip()
    bad = dict(baseline, revision=source)
    assert "baseline_git_commit_mismatch" in mod._verify_baseline_git_revision(
        bad, ledger, root / "skills/skill-architect"
    )


def test_git_provenance_ignores_inherited_repository_overrides(monkeypatch):
    import pytest
    import subprocess

    root = Path(__file__).resolve().parents[1]
    corpus = root / "evals/skills/skill-architect"
    baseline = json.loads((corpus / "refactor-pilot-baseline.json").read_text(encoding="utf-8"))
    ledger = json.loads((corpus / "refactor-pilot-ledger.json").read_text(encoding="utf-8"))
    available = subprocess.run(
        ["git", "-C", str(root), "cat-file", "-e", baseline["revision"] + "^{commit}"],
        check=False, capture_output=True, timeout=10,
    )
    if available.returncode != 0:
        pytest.skip("baseline history unavailable in shallow checkout")

    monkeypatch.setenv("GIT_DIR", str(root / "nonexistent-attacker-repository"))
    monkeypatch.setenv("GIT_WORK_TREE", str(root))
    monkeypatch.setenv("GIT_OBJECT_DIRECTORY", str(root / "nonexistent-attacker-objects"))
    monkeypatch.setenv("GIT_ALTERNATE_OBJECT_DIRECTORIES", str(root / "nonexistent-alternates"))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.repositoryformatversion")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "777")
    assert mod._verify_baseline_git_revision(
        baseline, ledger, root / "skills/skill-architect"
    ) == []
