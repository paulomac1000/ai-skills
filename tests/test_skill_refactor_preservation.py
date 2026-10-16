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
    (skill/'manifest.yaml').write_text('name: fixture-skill\nversion: 0.0.0\n')
    baseline = {'revision': 'a' * 40, 'required_behaviors': [{'id': 'auth', 'kind': kind}]}
    decision = {'id': 'auth', 'disposition': 'MOVE', 'target_path': 'STANDARD.md', 'target_anchor': 'Require policy authorization', 'negative_case': 'unauthorized_call', 'verification': 'negative-test', 'pre_load_path': 'SKILL.md', 'pre_load_trigger': 'Trigger when destructive action'}
    def blob(path):
        raw = (skill / path).read_bytes()
        return mod._git_blob_sha(raw)

    decision['entrypoint_route'] = 'Trigger when destructive action requested; read STANDARD.md'
    decision['source_path'] = 'STANDARD.md'
    decision['source_anchor'] = 'Require policy authorization'
    decision['positive_case'] = 'authorized_operation'
    ledger = {
        'candidate_revision': 'candidate-sha',
        'baseline_sha256': 'sha256:' + hashlib.sha256(
            json.dumps(baseline, sort_keys=True, separators=(',', ':')).encode()
        ).hexdigest(),
        'candidate_files': {'SKILL.md': blob('SKILL.md'), 'STANDARD.md': blob('STANDARD.md'), 'manifest.yaml': blob('manifest.yaml')},
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
        '- first independent route -> references/p1.md\n'
        '- second independent route -> references/p2.md'
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
    assert result["candidate_revision"] == "NOT_VERIFIED"
    assert result["declared_candidate_version"] == "3.26.0"

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


def test_git_provenance_does_not_resolve_executable_through_inherited_path(tmp_path, monkeypatch):
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
        pytest.skip("baseline unavailable in shallow checkout")

    fake = tmp_path / "git"
    fake.write_text("#!/bin/sh\necho forged-history\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert Path(mod._trusted_git_executable()).is_absolute()
    assert mod._verify_baseline_git_revision(
        baseline, ledger, root / "skills/skill-architect"
    ) == []


def test_cyclic_symlink_bindings_fail_closed_before_resolve(tmp_path):
    import pytest

    path, baseline, ledger, decision = case(tmp_path, kind="evidence")
    loop = path / "loop.md"
    try:
        loop.symlink_to("loop.md")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable")
    ledger["candidate_files"]["loop.md"] = ledger["candidate_files"]["STANDARD.md"]
    ledger["decisions"] = [decision | {"target_path": "loop.md"}]
    result = assess(baseline, ledger, path)
    assert result["structural"] == "FAILED"
    assert "candidate_symlink_rejected:loop.md" in result["findings"]

def test_verified_anchor_reads_are_from_original_hashed_bytes(tmp_path, monkeypatch):
    path, baseline, ledger, _ = case(tmp_path)
    original = Path.read_text

    def guarded_read_text(self, *args, **kwargs):
        if self == path / "SKILL.md" or self == path / "STANDARD.md":
            raise AssertionError("verified file reopened after hash")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    assert assess(baseline, ledger, path)["structural"] == "PASS"


def test_modified_ledger_target_remains_failed_even_with_matching_anchor(tmp_path):
    path, baseline, ledger, decision = case(tmp_path, kind="evidence")
    (path / "STANDARD.md").write_text("Require policy authorization; retain rollback evidence / edited")
    result = assess(baseline, ledger, path)
    assert result["structural"] == "FAILED"
    assert "candidate_content_mismatch:STANDARD.md" in result["findings"]

def test_negated_entrypoint_route_rejected_with_correct_blob_binding(tmp_path):
    path, baseline, ledger, decision = case(tmp_path)
    route = "Trigger when destructive action requested; do not read STANDARD.md"
    (path / "SKILL.md").write_text(route, encoding="utf-8")
    ledger["candidate_files"]["SKILL.md"] = mod._git_blob_sha((path / "SKILL.md").read_bytes())
    ledger["decisions"] = [decision | {"entrypoint_route": route}]
    result = assess(baseline, ledger, path)
    assert "owner_route_unreachable:auth" in result["findings"]
    assert "candidate_content_mismatch:SKILL.md" not in result["findings"]


def test_typographic_and_unlisted_contractions_fail_closed():
    owner = "STANDARD.md"
    for negative in ("Don’t", "won't", "isn't", "can't", "wouldn't", "shouldn’t", "no"):
        route = f"Trigger when destructive action requested; {negative} read {owner}"
        assert not mod._positive_entrypoint_route(route, owner), negative


def test_route_cannot_hide_same_line_negation_before_declared_text(tmp_path):
    path, baseline, ledger, decision = case(tmp_path, kind="evidence")
    skill_text = "Do not apply: Trigger when destructive action requested; read STANDARD.md before action"
    (path / "SKILL.md").write_text(skill_text, encoding="utf-8")
    ledger["candidate_files"]["SKILL.md"] = mod._git_blob_sha((path / "SKILL.md").read_bytes())
    result = assess(baseline, ledger, path)
    assert "owner_route_unreachable:auth" in result["findings"]
    assert "candidate_content_mismatch:SKILL.md" not in result["findings"]


def test_route_at_list_item_line_start_is_reachable(tmp_path):
    path, baseline, ledger, decision = case(tmp_path, kind="evidence")
    (path / "SKILL.md").write_text("- Trigger when destructive action requested; read STANDARD.md before action")
    ledger["candidate_files"]["SKILL.md"] = mod._git_blob_sha((path / "SKILL.md").read_bytes())
    assert assess(baseline, ledger, path)["structural"] == "PASS"


def test_distant_negative_route_never_counts_as_positive():
    owner = "references/owner.md"
    route = "Never " + ("under any circumstances " * 8) + "consult " + owner
    assert len(route[: route.index(owner)]) > 128
    assert not mod._positive_entrypoint_route(route, owner)


def test_post_owner_negation_in_declared_route_rejected():
    owner = "STANDARD.md"
    route = "Trigger when destructive action requested; read STANDARD.md, but not before action"
    assert not mod._positive_entrypoint_route(route, owner)


def test_post_owner_negation_outside_ledger_route_rejected(tmp_path):
    path, baseline, ledger, decision = case(tmp_path, kind="evidence")
    route = decision["entrypoint_route"]
    (path / "SKILL.md").write_text(route + ", but not before the destructive action")
    ledger["candidate_files"]["SKILL.md"] = mod._git_blob_sha((path / "SKILL.md").read_bytes())
    result = assess(baseline, ledger, path)
    assert "owner_route_unreachable:auth" in result["findings"]
    assert "candidate_content_mismatch:SKILL.md" not in result["findings"]


def test_post_owner_positive_qualifier_preserves_route(tmp_path):
    path, baseline, ledger, decision = case(tmp_path, kind="evidence")
    route = decision["entrypoint_route"]
    (path / "SKILL.md").write_text("- " + route + " before any governed effect")
    ledger["candidate_files"]["SKILL.md"] = mod._git_blob_sha((path / "SKILL.md").read_bytes())
    assert assess(baseline, ledger, path)["structural"] == "PASS"


def test_delayed_owner_route_is_rejected_for_critical_rules(tmp_path):
    path, baseline, ledger, decision = case(tmp_path, kind="authority")
    route = "Trigger when destructive action requested; read STANDARD.md only after action"
    (path / "SKILL.md").write_text(route)
    ledger["candidate_files"]["SKILL.md"] = mod._git_blob_sha((path / "SKILL.md").read_bytes())
    ledger["decisions"] = [decision | {"entrypoint_route": route}]
    result = assess(baseline, ledger, path)
    assert "owner_route_unreachable:auth" in result["findings"]
    assert not mod._positive_entrypoint_route(route, "STANDARD.md", require_pre_action=True)


def test_once_complete_and_unqualified_critical_routes_fail_closed(tmp_path):
    path, baseline, ledger, decision = case(tmp_path, kind="authority")
    for suffix in ("once the action is complete", "when convenient"):
        route = "Trigger when destructive action requested; read STANDARD.md " + suffix
        (path / "SKILL.md").write_text(route)
        ledger["candidate_files"]["SKILL.md"] = mod._git_blob_sha((path / "SKILL.md").read_bytes())
        ledger["decisions"] = [decision | {"entrypoint_route": route}]
        assert "owner_route_unreachable:auth" in assess(baseline, ledger, path)["findings"]


def test_explicit_before_action_route_is_accepted(tmp_path):
    path, baseline, ledger, decision = case(tmp_path, kind="authority")
    assert assess(baseline, ledger, path)["structural"] == "PASS"
    assert mod._positive_entrypoint_route(
        (path / "SKILL.md").read_text(), "STANDARD.md", require_pre_action=True
    )


def test_retained_critical_skill_route_rejects_negation_and_delay(tmp_path):
    path, baseline, ledger, decision = case(tmp_path, kind="authority")
    ledger["decisions"] = [
        decision
        | {
            "target_path": "SKILL.md",
            "target_anchor": "Require authorization",
            "pre_load_trigger": "Require authorization",
        }
    ]
    for line, valid in (
        ("Require authorization before action", True),
        ("Do not Require authorization before action", False),
        ("Require authorization only after action", False),
        ("Require authorization", False),
    ):
        (path / "SKILL.md").write_text(line)
        ledger["candidate_files"]["SKILL.md"] = mod._git_blob_sha((path / "SKILL.md").read_bytes())
        result = assess(baseline, ledger, path)
        if valid:
            assert result["structural"] == "PASS", result["findings"]
        else:
            assert "critical_entrypoint_not_affirmative:auth" in result["findings"]


def test_untrusted_candidate_revision_is_not_reported_as_verified(tmp_path):
    path, baseline, ledger, decision = case(tmp_path)
    for raw in ("attacker-controlled", None, "f" * 40):
        ledger["candidate_revision"] = raw
        result = assess(baseline, ledger, path)
        assert result["structural"] == "PASS"
        assert result["candidate_revision"] == "NOT_VERIFIED"
        assert result["declared_candidate_version"] is None
    ledger["candidate_revision"] = "3.26.0"
    result = assess(baseline, ledger, path)
    assert result["candidate_revision"] == "NOT_VERIFIED"
    assert result["declared_candidate_version"] == "3.26.0"


def test_moved_critical_owner_must_contain_affirmative_rule(tmp_path):
    path, baseline, ledger, decision = case(tmp_path, kind="authority")
    assert assess(baseline, ledger, path)["structural"] == "PASS"
    (path / "STANDARD.md").write_text("Do not Require policy authorization; retain rollback evidence")
    ledger["candidate_files"]["STANDARD.md"] = mod._git_blob_sha((path / "STANDARD.md").read_bytes())
    result = assess(baseline, ledger, path)
    assert "critical_owner_rule_negated:auth" in result["findings"]
    assert "candidate_content_mismatch:STANDARD.md" not in result["findings"]


def test_explicit_git_override_is_absolute_and_ignores_path(monkeypatch, tmp_path):
    import pytest

    fake = tmp_path / "git"
    fake.write_text("#!/bin/sh\\necho forged-history\\n")
    fake.chmod(0o777)
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(ValueError, match="trusted_git_executable_not_absolute"):
        mod._trusted_git_executable("git")
    if sys.platform == "win32":
        with pytest.raises(ValueError, match="trusted_git_override_unsupported_on_windows"):
            mod._trusted_git_executable(str(fake))
    else:
        with pytest.raises(FileNotFoundError, match="trusted_git_executable_unavailable"):
            mod._trusted_git_executable(str(fake))
    try:
        default_git = mod._trusted_git_executable()
    except FileNotFoundError:
        default_git = None
    if default_git is not None:
        assert mod._trusted_git_executable() == default_git
        if sys.platform != "win32":
            assert mod._trusted_git_executable(default_git) == default_git


def test_pre_action_timing_must_identify_a_governed_effect(tmp_path):
    path, baseline, ledger, decision = case(tmp_path, kind="authority")
    route = decision["entrypoint_route"]
    for suffix in ("before lunch", "prior to breakfast", "before the end of the day"):
        (path / "SKILL.md").write_text(route + " " + suffix)
        ledger["candidate_files"]["SKILL.md"] = mod._git_blob_sha((path / "SKILL.md").read_bytes())
        assert "owner_route_unreachable:auth" in assess(baseline, ledger, path)["findings"]
    for suffix in ("before action", "prior to any governed effect"):
        (path / "SKILL.md").write_text(route + " " + suffix)
        ledger["candidate_files"]["SKILL.md"] = mod._git_blob_sha((path / "SKILL.md").read_bytes())
        assert assess(baseline, ledger, path)["structural"] == "PASS"


def test_critical_owner_rejects_optional_and_modal_weakening(tmp_path):
    path, baseline, ledger, decision = case(tmp_path, kind="authority")
    for weakened in (
        "Require policy authorization is optional",
        "You may Require policy authorization",
        "Require policy authorization when convenient",
    ):
        (path / "STANDARD.md").write_text(weakened)
        ledger["candidate_files"]["STANDARD.md"] = mod._git_blob_sha((path / "STANDARD.md").read_bytes())
        assert "critical_owner_rule_negated:auth" in assess(baseline, ledger, path)["findings"]


def test_critical_retained_owner_must_be_mandatory(tmp_path):
    path, baseline, ledger, decision = case(tmp_path, kind="authority")
    ledger["decisions"] = [
        decision
        | {"target_path": "SKILL.md", "target_anchor": "Require authorization", "pre_load_trigger": "Require authorization"}
    ]
    (path / "SKILL.md").write_text("Require authorization is optional before action")
    ledger["candidate_files"]["SKILL.md"] = mod._git_blob_sha((path / "SKILL.md").read_bytes())
    result = assess(baseline, ledger, path)
    assert "critical_entrypoint_not_affirmative:auth" in result["findings"]
    assert "critical_owner_rule_negated:auth" in result["findings"]


def test_owner_path_must_end_at_a_token_boundary(tmp_path):
    path, baseline, ledger, decision = case(tmp_path)
    route = decision["entrypoint_route"]
    for suffix in (".bak", "/child", "-backup"):
        tampered = route.replace("STANDARD.md", "STANDARD.md" + suffix)
        (path / "SKILL.md").write_text(tampered + " before action")
        ledger["candidate_files"]["SKILL.md"] = mod._git_blob_sha((path / "SKILL.md").read_bytes())
        ledger["decisions"] = [decision | {"entrypoint_route": tampered}]
        assert "owner_route_unreachable:auth" in assess(baseline, ledger, path)["findings"]
        assert not mod._positive_entrypoint_route(
            tampered + " before action", "STANDARD.md", require_pre_action=True
        )


def test_optional_critical_owner_route_is_not_pre_action_proof(tmp_path):
    path, baseline, ledger, decision = case(tmp_path, kind="authority")
    route = decision["entrypoint_route"]
    for qualifier in ("if convenient", "if available", "unless waived", "optionally", "you may skip"):
        line = route + " before action " + qualifier
        (path / "SKILL.md").write_text(line)
        ledger["candidate_files"]["SKILL.md"] = mod._git_blob_sha((path / "SKILL.md").read_bytes())
        assert "owner_route_unreachable:auth" in assess(baseline, ledger, path)["findings"]
    (path / "SKILL.md").write_text(route + " before action")
    ledger["candidate_files"]["SKILL.md"] = mod._git_blob_sha((path / "SKILL.md").read_bytes())
    assert assess(baseline, ledger, path)["structural"] == "PASS"


def test_noncritical_material_rule_cannot_be_negated_in_owner(tmp_path):
    for kind in ("recovery", "exception", "completion", "evidence"):
        kind_root = tmp_path / kind
        kind_root.mkdir()
        path, baseline, ledger, decision = case(kind_root, kind=kind)
        assert assess(baseline, ledger, path)["structural"] == "PASS"
        (path / "STANDARD.md").write_text("Do not Require policy authorization; retain rollback evidence")
        ledger["candidate_files"]["STANDARD.md"] = mod._git_blob_sha((path / "STANDARD.md").read_bytes())
        findings = assess(baseline, ledger, path)["findings"]
        assert "material_owner_rule_negated:auth" in findings


def test_critical_route_cannot_ignore_its_owner_after_loading(tmp_path):
    path, baseline, ledger, decision = case(tmp_path, kind="authority")
    route = decision["entrypoint_route"]
    for trailing in (
        "and ignore its requirements",
        "and disregard its instructions",
        "and bypass policy safeguards",
        "and waive mandatory checks",
        "and omit owner constraints",
    ):
        line = route + " before action " + trailing
        (path / "SKILL.md").write_text(line)
        ledger["candidate_files"]["SKILL.md"] = mod._git_blob_sha((path / "SKILL.md").read_bytes())
        assert "owner_route_unreachable:auth" in assess(baseline, ledger, path)["findings"]


def test_critical_route_timing_must_govern_owner_read(tmp_path):
    path, baseline, ledger, decision = case(tmp_path, kind="authority")
    route = decision["entrypoint_route"]
    (path / "SKILL.md").write_text(route + " eventually; write audit log before action")
    ledger["candidate_files"]["SKILL.md"] = mod._git_blob_sha((path / "SKILL.md").read_bytes())
    assert "owner_route_unreachable:auth" in assess(baseline, ledger, path)["findings"]


def test_retained_critical_route_rejects_unrelated_timed_log(tmp_path):
    path, baseline, ledger, decision = case(tmp_path, kind="authority")
    ledger["decisions"] = [
        decision
        | {
            "target_path": "SKILL.md",
            "target_anchor": "Require authorization",
            "pre_load_trigger": "Require authorization",
        }
    ]
    (path / "SKILL.md").write_text("Require authorization; write audit log before action")
    ledger["candidate_files"]["SKILL.md"] = mod._git_blob_sha((path / "SKILL.md").read_bytes())
    assert "critical_entrypoint_not_affirmative:auth" in assess(baseline, ledger, path)["findings"]


def test_noncritical_owner_historical_mention_does_not_preserve_rule(tmp_path):
    path, baseline, ledger, decision = case(tmp_path, kind="recovery")
    (path / "STANDARD.md").write_text("The legacy documentation mentioned Require policy authorization")
    ledger["candidate_files"]["STANDARD.md"] = mod._git_blob_sha((path / "STANDARD.md").read_bytes())
    assert "material_owner_rule_negated:auth" in assess(baseline, ledger, path)["findings"]


def test_retained_authority_does_not_borrow_unrelated_resource_timing(tmp_path):
    path, baseline, ledger, decision = case(tmp_path, kind="authority")
    ledger["decisions"] = [
        decision
        | {
            "target_path": "SKILL.md",
            "target_anchor": "Require authorization",
            "pre_load_trigger": "Require authorization",
        }
    ]
    (path / "SKILL.md").write_text("Require authorization; read audit.md before action")
    ledger["candidate_files"]["SKILL.md"] = mod._git_blob_sha((path / "SKILL.md").read_bytes())
    assert "critical_entrypoint_not_affirmative:auth" in assess(baseline, ledger, path)["findings"]


def test_windows_junction_cannot_escape_attested_root(tmp_path, monkeypatch):
    import subprocess

    import pytest

    if sys.platform != "win32":
        pytest.skip("Windows junction API only")
    root = tmp_path / "skill"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "owner.md").write_text("external")
    junction = root / "references"
    attempt = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(junction), str(outside)],
        capture_output=True,
        text=True,
        check=False,
    )
    if attempt.returncode:
        pytest.skip("Windows runner does not permit creating junctions")
    assert mod._contains_symlink(root, "references/owner.md")
    with pytest.raises(ValueError):
        mod._read_attested_regular_file(root, "references/owner.md")
    monkeypatch.setattr(mod, "_contains_symlink", lambda *_: False)
    with pytest.raises(ValueError, match="outside_root_handle"):
        mod._read_attested_regular_file(root, "references/owner.md")


def test_owner_anchor_rejects_passive_or_inflected_prohibitions(tmp_path):
    path, baseline, ledger, decision = case(tmp_path, kind="authority")
    for line in (
        "Require policy authorization is prohibited",
        "Require policy authorization is forbidden",
        "Require policy authorization was disallowed",
        "Require policy authorization is revoked",
        "Require policy authorization is no longer required",
        "Require policy authorization is optional",
    ):
        (path / "STANDARD.md").write_text(line)
        ledger["candidate_files"]["STANDARD.md"] = mod._git_blob_sha((path / "STANDARD.md").read_bytes())
        result = assess(baseline, ledger, path)
        assert "critical_owner_rule_negated:auth" in result["findings"], line


def test_required_normative_document_inventory_cannot_omit_files(tmp_path):
    path, baseline, ledger, decision = case(tmp_path)
    for required in ("SKILL.md", "STANDARD.md", "manifest.yaml"):
        omission = {key: blob for key, blob in ledger["candidate_files"].items() if key != required}
        result = assess(baseline, {**ledger, "candidate_files": omission}, path)
        assert "required_candidate_document_missing:" + required in result["findings"]


def test_code_fence_and_comment_routes_do_not_count_as_live_instructions(tmp_path):
    path, baseline, ledger, decision = case(tmp_path)
    route = decision["entrypoint_route"] + " before action"
    for content in (
        "```markdown\n" + route + "\n```",
        "~~~yaml\n" + route + "\n~~~",
        "<!-- " + route + " -->",
        "    " + route,
        "> " + route,
    ):
        (path / "SKILL.md").write_text(content)
        ledger["candidate_files"]["SKILL.md"] = mod._git_blob_sha((path / "SKILL.md").read_bytes())
        result = assess(baseline, ledger, path)
        assert "owner_route_unreachable:auth" in result["findings"]


def test_unreachable_baseline_git_commit_rejected_when_object_exists(monkeypatch):
    import subprocess
    import pytest

    root = Path(__file__).resolve().parents[1]
    corpus = root / "evals/skills/skill-architect"
    baseline = json.loads((corpus / "refactor-pilot-baseline.json").read_text(encoding="utf-8"))
    ledger = json.loads((corpus / "refactor-pilot-ledger.json").read_text(encoding="utf-8"))
    probe = subprocess.run(["git", "-C", str(root), "cat-file", "-e", baseline["revision"] + "^{commit}"], check=False)
    if probe.returncode:
        pytest.skip("baseline Git object unavailable")
    original = mod.subprocess.run

    def blocked_ancestry(argv, **kwargs):
        if "merge-base" in argv and "--is-ancestor" in argv:
            assert argv[-1] == "refs/remotes/origin/main"
            return subprocess.CompletedProcess(argv, 1)
        return original(argv, **kwargs)

    monkeypatch.setattr(mod.subprocess, "run", blocked_ancestry)
    actual = mod._verify_baseline_git_revision(baseline, ledger, root / "skills/skill-architect")
    assert actual == ["baseline_git_revision_untrusted"]


def test_wrapped_owner_negation_and_entrypoint_skip_fail_closed(tmp_path):
    path, baseline, ledger, decision = case(tmp_path)
    (path / "STANDARD.md").write_text("Require policy authorization\nis prohibited.")
    ledger["candidate_files"]["STANDARD.md"] = mod._git_blob_sha((path / "STANDARD.md").read_bytes())
    assert "critical_owner_rule_negated:auth" in assess(baseline, ledger, path)["findings"]
    (path / "STANDARD.md").write_text("Require policy authorization; retain rollback evidence")
    ledger["candidate_files"]["STANDARD.md"] = mod._git_blob_sha((path / "STANDARD.md").read_bytes())
    route = decision["entrypoint_route"]
    for text in (
        route + " before action\nbut skip it for small edits.",
        "Do not apply:\n" + route + " before action",
    ):
        (path / "SKILL.md").write_text(text)
        ledger["candidate_files"]["SKILL.md"] = mod._git_blob_sha((path / "SKILL.md").read_bytes())
        assert "owner_route_unreachable:auth" in assess(baseline, ledger, path)["findings"]


def test_logical_lines_keep_independent_list_items_separate():
    assert mod._logical_lines("- read STANDARD.md before action\n- preserve rollback") == [
        "- read STANDARD.md before action",
        "- preserve rollback",
    ]
    assert mod._logical_lines("Require policy authorization\nis prohibited.") == [
        "Require policy authorization is prohibited."
    ]


def test_observed_absent_references_do_not_negate_inspection():
    line = (
        "Inspect representative runs for unexpected skill selection, "
        "references always or never opened, repeated unnecessary reads."
    )
    assert mod._mandatory_owner_instruction(line, "Inspect representative runs")
    assert not mod._mandatory_owner_instruction(
        "Inspect representative runs, but never inspect them",
        "Inspect representative runs",
    )


def test_positive_route_grammar_covers_read_consult_and_arrow():
    assert mod._positive_entrypoint_route("read STANDARD.md", "STANDARD.md")
    assert mod._positive_entrypoint_route(
        "For a refactor consult references/behavior.md", "references/behavior.md"
    )
    assert mod._positive_entrypoint_route("routine -> references/owner.md", "references/owner.md")
    assert not mod._positive_entrypoint_route("never consult references/owner.md", "references/owner.md")
    assert not mod._positive_entrypoint_route("without reading references/owner.md", "references/owner.md")
