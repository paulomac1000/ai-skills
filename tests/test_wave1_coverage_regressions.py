from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CI_TOOLS = ROOT / "skills" / "ci-cd-architect" / "tools"
AGENT_TOOLS = ROOT / "skills" / "agents-md-architect" / "tools"
if str(AGENT_TOOLS) not in sys.path:
    sys.path.insert(0, str(AGENT_TOOLS))


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PARITY = _load("wave1_coverage_parity", CI_TOOLS / "check_local_ci_parity.py")
CORPUS = _load("wave1_coverage_corpus", CI_TOOLS / "check_test_corpus.py")
GATES = _load("wave1_coverage_gate_sources", AGENT_TOOLS / "agents_md_gate_sources.py")
DISCOVERY = _load("wave1_coverage_discovery", AGENT_TOOLS / "discover_repository.py")


def _write(path: Path, text: str, *, executable: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if executable:
        path.chmod(0o755)
    return path


def _workflow(root: Path, text: str) -> Path:
    return _write(root / ".github/workflows/ci.yml", text)


def _valid_parity_root(root: Path) -> dict[str, object]:
    _workflow(
        root,
        "on:\n  pull_request:\n\njobs:\n  verify:\n    runs-on: ubuntu-latest\n    steps: []\n",
    )
    _write(root / "scripts/check.py", "if __name__ == '__main__':\n    print('ok')\n")
    _write(root / "policy.md", "policy\n")
    _write(root / "requirements.lock", "locked\n")
    return {
        "schema_version": 1,
        "policy_revision": "policy-1",
        "gates": [
            {
                "id": "verify",
                "merge_blocking": True,
                "local_entrypoint": "python scripts/check.py",
                "policy_ref": "policy.md#rule",
                "dependency_ref": "requirements.lock",
            }
        ],
    }


@pytest.mark.parametrize(
    ("trigger", "expected"),
    [
        ("pull_request", True),
        ("push", False),
        (["push", "pull_request_target"], True),
        (["push"], False),
        ({"pull_request": {}}, True),
        ({"push": {}}, False),
        (None, False),
    ],
)
def test_parity_trigger_shapes(trigger: object, expected: bool) -> None:
    document: dict[object, object] = {"on": trigger}
    assert PARITY._workflow_triggers_pull_request(document) is expected


def test_parity_discovery_handles_absence_non_pr_continue_and_yaml_extension(tmp_path: Path) -> None:
    assert PARITY._discover_merge_blocking_jobs(tmp_path) == set()
    _workflow(tmp_path, "on: push\njobs:\n  ignored:\n    steps: []\n")
    _write(
        tmp_path / ".github/workflows/extra.yaml",
        "on: [pull_request]\njobs:\n  optional:\n    continue-on-error: true\n    steps: []\n  required:\n    steps: []\n",
    )
    assert PARITY._discover_merge_blocking_jobs(tmp_path) == {"required"}


@pytest.mark.parametrize(
    "body",
    [
        "on: pull_request\njobs: []\n",
        "on: pull_request\njobs:\n  '': {}\n",
        "on: pull_request\njobs:\n  verify: scalar\n",
    ],
)
def test_parity_discovery_rejects_invalid_job_shapes(tmp_path: Path, body: str) -> None:
    _workflow(tmp_path, body)
    with pytest.raises(ValueError):
        PARITY._discover_merge_blocking_jobs(tmp_path)


def test_parity_reference_and_entrypoint_confinement(tmp_path: Path) -> None:
    present = _write(tmp_path / "policy.md", "ok")
    assert PARITY._confined_file(tmp_path, "") is None
    assert PARITY._confined_file(tmp_path, "../escape") is None
    assert PARITY._confined_file(tmp_path, "missing.md") is None
    assert PARITY._confined_file(tmp_path, "policy.md#anchor") == present.resolve()

    assert PARITY._entrypoint_path(tmp_path, "") is None
    assert PARITY._entrypoint_path(tmp_path, "python -m package") is None
    assert PARITY._entrypoint_path(tmp_path, "python ../escape.py") is None
    assert PARITY._entrypoint_path(tmp_path, "python 'unterminated") is None
    assert PARITY._entrypoint_path(tmp_path, "python -I scripts/check.py") == (tmp_path / "scripts/check.py").resolve()


def test_parity_local_entrypoint_validation_covers_python_and_shell(tmp_path: Path) -> None:
    _write(tmp_path / "scripts/good.py", "print('ok')\n")
    _write(tmp_path / "scripts/bad.py", "if:\n")
    assert PARITY._valid_local_entrypoint(tmp_path, "python scripts/good.py") is True
    assert PARITY._valid_local_entrypoint(tmp_path, "python scripts/bad.py") is False
    assert PARITY._valid_local_entrypoint(tmp_path, "python scripts/missing.py") is False

    shell = _write(tmp_path / "scripts/check.sh", "#!/bin/sh\nexit 0\n")
    if os.name != "nt":
        shell.chmod(0o755)
        assert PARITY._valid_local_entrypoint(tmp_path, "sh scripts/check.sh") is True
        shell.chmod(0o644)
        assert PARITY._valid_local_entrypoint(tmp_path, "sh scripts/check.sh") is False


@pytest.mark.parametrize(
    "policy",
    [
        {},
        {"schema_version": 1, "policy_revision": "", "gates": [{}]},
        {"schema_version": 1, "policy_revision": "p", "gates": []},
        {"schema_version": 1, "policy_revision": "p", "gates": ["bad"]},
    ],
)
def test_parity_evaluate_rejects_invalid_policy_roots(policy: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        PARITY.evaluate(policy)


def test_parity_evaluate_classifies_duplicate_and_invalid_gate_contracts() -> None:
    policy = {
        "schema_version": 1,
        "policy_revision": "p",
        "gates": [
            {
                "id": "a",
                "merge_blocking": True,
                "local_entrypoint": " ",
                "hosted_only": "yes",
                "policy_ref": None,
            },
            {"id": "a", "merge_blocking": False},
            {
                "id": "b",
                "merge_blocking": True,
                "hosted_only": True,
                "hosted_only_reason": "",
                "local_entrypoint": "python x.py",
                "policy_ref": "policy.md",
            },
            {"id": "c", "merge_blocking": True, "policy_ref": "policy.md"},
        ],
    }
    result = PARITY.evaluate(policy)
    assert result["verdict"] == "fail"
    assert set(result["invalid_gates"]) == {"a", "b"}
    assert result["missing_local_entrypoints"] == ["a", "c"]


def test_parity_evaluate_valid_hosted_only_and_local_gate(tmp_path: Path) -> None:
    policy = _valid_parity_root(tmp_path)
    gates = policy["gates"]
    assert isinstance(gates, list)
    gates.append(
        {
            "id": "provider",
            "merge_blocking": True,
            "hosted_only": True,
            "hosted_only_reason": "provider identity",
            "policy_ref": "policy.md",
        }
    )
    _write(
        tmp_path / ".github/workflows/provider.yml",
        "on: pull_request\njobs:\n  provider:\n    steps: []\n",
    )
    result = PARITY.evaluate(policy, root=tmp_path)
    assert result["verdict"] == "pass"
    assert result["hosted_only_gates"] == ["provider"]
    assert result["discovered_merge_blocking_jobs"] == ["provider", "verify"]


def test_parity_main_success_output_and_input_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    policy = _valid_parity_root(tmp_path)
    policy_path = tmp_path / "parity.yaml"
    policy_path.write_text(yaml.safe_dump(policy), encoding="utf-8")
    output = tmp_path / "result.json"
    monkeypatch.setattr(sys, "argv", ["check_local_ci_parity.py", str(policy_path), "--root", str(tmp_path), "--output", str(output)])
    assert PARITY.main() == 0
    assert json.loads(output.read_text(encoding="utf-8"))["verdict"] == "pass"
    assert json.loads(capsys.readouterr().out)["verdict"] == "pass"

    policy_path.write_text("- not-a-map\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["check_local_ci_parity.py", str(policy_path), "--root", str(tmp_path)])
    assert PARITY.main() == 2
    assert json.loads(capsys.readouterr().out)["verdict"] == "fail"


def _test_file(root: Path, name: str = "test_one.py") -> str:
    relative = f"tests/{name}"
    _write(root / relative, "def test_one():\n    pass\n")
    return relative


def _base_corpus_policy(**overrides: object) -> dict[str, object]:
    policy: dict[str, object] = {
        "schema_version": 1,
        "policy_revision": "corpus-1",
        "mode": "automatic",
        "include": ["tests/test_*.py"],
        "exclusions": [],
    }
    policy.update(overrides)
    return policy


def test_corpus_policy_loader_and_expiry_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(yaml.safe_dump(_base_corpus_policy()), encoding="utf-8")
    assert CORPUS._load_policy(policy_path)["schema_version"] == 1

    with monkeypatch.context() as patch:
        patch.setattr(CORPUS, "MAX_POLICY_BYTES", 1)
        with pytest.raises(ValueError, match="maximum size"):
            CORPUS._load_policy(policy_path)
    policy_path.write_text("- list\n", encoding="utf-8")
    with pytest.raises(ValueError, match="mapping"):
        CORPUS._load_policy(policy_path)
    policy_path.write_text("schema_version: 2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="schema_version"):
        CORPUS._load_policy(policy_path)

    assert CORPUS._expiry(None) is None
    assert CORPUS._expiry("") is None
    assert CORPUS._expiry("2026-09-12T00:00:00Z") == datetime(2026, 9, 12, tzinfo=UTC)
    with pytest.raises(ValueError, match="RFC3339"):
        CORPUS._expiry(7)
    with pytest.raises(ValueError, match="RFC3339"):
        CORPUS._expiry("not-time")
    with pytest.raises(ValueError, match="timezone"):
        CORPUS._expiry("2026-09-12T00:00:00")


def test_corpus_discovery_manifest_and_observed_path_helpers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    one = _test_file(tmp_path)
    _write(tmp_path / "tests/helper.txt", "x")
    assert CORPUS._discover(tmp_path, ["tests/test_*.py"]) == {one}
    assert CORPUS._read_manifest(tmp_path, None) == set()

    manifest = _write(tmp_path / "executed.txt", f"# comment\n\n{one}\n")
    assert CORPUS._read_manifest(tmp_path, manifest.name) == {one}
    assert CORPUS._paths(tmp_path, [one, one]) == {one}
    with pytest.raises(ValueError, match="invalid path"):
        CORPUS._paths(tmp_path, [""])
    with pytest.raises(ValueError):
        CORPUS._paths(tmp_path, ["../escape"])
    with pytest.raises(ValueError, match="regular file"):
        CORPUS._read_manifest(tmp_path, "missing.txt")

    with monkeypatch.context() as patch:
        patch.setattr(CORPUS, "MAX_DISCOVERED", 0)
        with pytest.raises(ValueError, match="maximum supported"):
            CORPUS._discover(tmp_path, ["tests/test_*.py"])


@pytest.mark.parametrize(
    "policy",
    [
        _base_corpus_policy(include=[]),
        _base_corpus_policy(mode="other"),
        _base_corpus_policy(policy_revision=""),
        _base_corpus_policy(exclusions="bad"),
    ],
)
def test_corpus_evaluate_rejects_invalid_top_level_policy(tmp_path: Path, policy: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        CORPUS.evaluate(tmp_path, policy, observed_executed=[])


def test_corpus_evaluate_rejects_bad_exclusions_and_manifest_contract(tmp_path: Path) -> None:
    _test_file(tmp_path)
    for exclusions in (
        ["bad"],
        [{"path": "", "reason": "x"}],
        [{"path": "tests/test_one.py", "reason": ""}],
        [
            {"path": "tests/test_one.py", "reason": "x"},
            {"path": "tests/test_one.py", "reason": "y"},
        ],
    ):
        with pytest.raises(ValueError):
            CORPUS.evaluate(tmp_path, _base_corpus_policy(exclusions=exclusions), observed_executed=[])

    with pytest.raises(ValueError, match="execution_manifest"):
        CORPUS.evaluate(tmp_path, _base_corpus_policy(mode="manifest"), observed_executed=[])


def test_corpus_manifest_selection_and_execution_drift(tmp_path: Path) -> None:
    one = _test_file(tmp_path, "test_one.py")
    two = _test_file(tmp_path, "test_two.py")
    _write(tmp_path / "manifest.txt", one + "\n")
    policy = _base_corpus_policy(mode="manifest", execution_manifest="manifest.txt")
    result = CORPUS.evaluate(tmp_path, policy, observed_executed=[one, "tests/unexpected.py"])
    assert result["verdict"] == "fail"
    assert result["missing_from_selection"] == [two]
    assert result["missing_from_execution"] == [two]
    assert result["unexpected_in_execution"] == ["tests/unexpected.py"]


def test_corpus_stale_exclusion_and_unknown_execution_are_non_pass(tmp_path: Path) -> None:
    one = _test_file(tmp_path)
    policy = _base_corpus_policy(
        exclusions=[{"path": "tests/missing.py", "reason": "temporary"}],
    )
    result = CORPUS.evaluate(tmp_path, policy, observed_executed=None)
    assert result["verdict"] == "fail"
    assert result["stale_exclusions"] == ["tests/missing.py"]

    clean = CORPUS.evaluate(tmp_path, _base_corpus_policy(), observed_executed=None)
    assert clean["verdict"] == "incomplete"
    assert clean["execution_evidence"] == "unknown"
    assert clean["selected_files"] == 1
    assert one not in clean["missing_from_execution"]


def test_corpus_active_exclusion_metadata_is_reported(tmp_path: Path) -> None:
    one = _test_file(tmp_path)
    policy = _base_corpus_policy(
        exclusions=[
            {
                "path": one,
                "reason": "hosted-only",
                "owner": "ci",
                "expires_at": "2026-09-12T00:00:00Z",
            }
        ]
    )
    result = CORPUS.evaluate(
        tmp_path,
        policy,
        observed_executed=[],
        now=datetime(2026, 9, 11, tzinfo=UTC),
    )
    assert result["verdict"] == "pass"
    assert result["excluded_files"] == [
        {
            "path": one,
            "reason": "hosted-only",
            "owner": "ci",
            "expires_at": "2026-09-12T00:00:00Z",
        }
    ]


def test_corpus_main_pass_incomplete_and_error_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    one = _test_file(tmp_path)
    policy_path = tmp_path / "corpus.yaml"
    policy_path.write_text(yaml.safe_dump(_base_corpus_policy()), encoding="utf-8")
    executed = _write(tmp_path / "executed.txt", one + "\n")
    output = tmp_path / "out.json"

    monkeypatch.setattr(
        sys,
        "argv",
        ["check_test_corpus.py", str(policy_path), "--root", str(tmp_path), "--executed-manifest", str(executed), "--output", str(output)],
    )
    assert CORPUS.main() == 0
    assert json.loads(output.read_text(encoding="utf-8"))["verdict"] == "pass"
    capsys.readouterr()

    monkeypatch.setattr(sys, "argv", ["check_test_corpus.py", str(policy_path), "--root", str(tmp_path)])
    assert CORPUS.main() == 2
    assert json.loads(capsys.readouterr().out)["verdict"] == "incomplete"

    outside = tmp_path.parent / "outside-executed.txt"
    outside.write_text(one + "\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["check_test_corpus.py", str(policy_path), "--root", str(tmp_path), "--executed-manifest", str(outside)],
    )
    assert CORPUS.main() == 2
    assert json.loads(capsys.readouterr().out)["verdict"] == "fail"


def test_gate_source_bounded_reader_and_executable_shebang_edges(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = _write(tmp_path / "scripts/run.sh", "#!/bin/sh\nexit 0\n")
    assert GATES._is_executable_shebang_script(tmp_path, "tools/run.sh") is False
    if os.name != "nt":
        assert GATES._is_executable_shebang_script(tmp_path, "scripts/run.sh") is False
        script.chmod(0o755)
        assert GATES._is_executable_shebang_script(tmp_path, "scripts/run.sh") is True
        script.write_text("echo no-shebang\n", encoding="utf-8")
        assert GATES._is_executable_shebang_script(tmp_path, "scripts/run.sh") is False

    with monkeypatch.context() as patch:
        patch.setattr(GATES, "MAX_CLASSIFIER_FILE_BYTES", 1)
        with pytest.raises(ValueError, match="exceeds"):
            GATES._read_bounded(tmp_path, "scripts/run.sh")


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink support required")
def test_gate_source_reader_rejects_symlink(tmp_path: Path) -> None:
    target = _write(tmp_path / "target.py", "print('x')\n")
    link = tmp_path / "scripts/link.py"
    link.parent.mkdir(parents=True)
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ValueError, match="symlink"):
        GATES._read_bounded(tmp_path, "scripts/link.py")


def test_gate_source_main_covers_pass_and_budget_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    _write(tmp_path / "scripts/task.py", "if __name__ == '__main__':\n    print('ok')\n")
    monkeypatch.setattr(sys, "argv", ["agents_md_gate_sources.py", str(tmp_path), "--limit", "1"])
    assert GATES.main() == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "pass"

    monkeypatch.setattr(sys, "argv", ["agents_md_gate_sources.py", str(tmp_path), "--limit", "0"])
    assert GATES.main() == 1
    assert json.loads(capsys.readouterr().out)["verdict"] == "fail"
