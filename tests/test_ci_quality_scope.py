"""Local and hosted quality gates share one canonical Python target inventory."""

from __future__ import annotations

import fnmatch
import importlib.util
import json
import subprocess
import sys
import tomllib

import pytest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGETS_PATH = ROOT / "scripts/quality_targets.py"


def load_targets() -> Any:
    spec = importlib.util.spec_from_file_location("quality_targets", TARGETS_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _inventory_covers(relative: str, inventory: tuple[str, ...]) -> bool:
    path = Path(relative)
    for target in inventory:
        if "*" in target:
            if fnmatch.fnmatch(relative, target):
                return True
            continue
        target_path = Path(target)
        if relative == target or target_path in path.parents:
            return True
    return False


def _production_python() -> set[str]:
    contracts = {path.relative_to(ROOT).as_posix() for path in (ROOT / "contracts").glob("*.py")}
    skill_tools = {
        path.relative_to(ROOT).as_posix() for path in (ROOT / "skills").glob("*/tools/*.py") if path.is_file()
    }
    return contracts | skill_tools


def test_agents_tools_are_in_every_policy_critical_target_set() -> None:
    targets = load_targets()
    tools = "skills/agents-md-architect/tools"
    assert tools in targets.QUALITY_PATHS
    assert tools in targets.BANDIT_PATHS
    assert f"{tools}/*.py" in targets.POLICY_COVERAGE_PATHS

    entrypoints = {
        f"{tools}/audit_agents_md.py",
        f"{tools}/discover_repository.py",
        f"{tools}/validate_agents_md.py",
    }
    assert entrypoints <= set(targets.TYPE_PATHS)
    assert tools not in targets.TYPE_PATHS

    for name in (
        "agents_md_parse.py",
        "agents_md_types.py",
        "audit_agents_md.py",
        "discover_repository.py",
        "validate_agents_md.py",
    ):
        assert (ROOT / tools / name).is_file()
    assert not (ROOT / tools / "__init__.py").exists()

    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    mypy_path = config["tool"]["mypy"]["mypy_path"]
    assert tools in mypy_path
    assert "contracts" in mypy_path


def test_production_python_cannot_fall_outside_canonical_quality_inventory() -> None:
    targets = load_targets()
    inventories = (
        targets.QUALITY_PATHS,
        targets.TYPE_PATHS,
        targets.BANDIT_PATHS,
        targets.POLICY_COVERAGE_PATHS,
    )
    production = _production_python()
    assert production
    omitted = [
        relative
        for relative in sorted(production)
        if not any(_inventory_covers(relative, inventory) for inventory in inventories)
    ]
    assert omitted == []


def test_explicit_type_targets_exist() -> None:
    targets = load_targets()
    missing = [target for target in targets.TYPE_PATHS if not (ROOT / target).is_file()]
    assert missing == []


def test_hosted_workflow_consumes_canonical_target_inventory() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "$(python scripts/quality_targets.py quality)" in workflow
    assert "$(python scripts/quality_targets.py typing)" in workflow
    assert "$(python scripts/quality_targets.py bandit)" in workflow
    assert "$(python scripts/quality_targets.py policy-coverage)" in workflow


def test_local_gate_imports_canonical_target_inventory() -> None:
    source = (ROOT / "scripts/ci.py").read_text(encoding="utf-8")
    assert "from quality_targets import" in source
    for token in ("QUALITY_PATHS", "TYPE_PATHS", "BANDIT_PATHS", "POLICY_COVERAGE_PATHS"):
        assert token in source


def test_target_cli_is_deterministic(capsys) -> None:
    targets = load_targets()
    assert targets.main(["quality"]) == 0
    assert capsys.readouterr().out.strip() == " ".join(targets.QUALITY_PATHS)


def test_optional_test_quality_is_disjoint_from_required_production_scope() -> None:
    targets = load_targets()
    test_path = "tests/test_ci_quality_scope.py"
    assert targets.TEST_QUALITY_PATHS == ("tests",)
    assert not _inventory_covers(test_path, targets.QUALITY_PATHS)
    assert _inventory_covers(test_path, targets.TEST_QUALITY_PATHS)
    assert "tests" not in targets.TYPE_PATHS
    assert targets.render_target("test-quality") == "tests"


def test_changed_test_quality_files_are_sorted_and_deduplicated() -> None:
    targets = load_targets()
    assert targets.select_test_quality_files(["tests/test_ci_scripts.py", "tests/test_ci_quality_scope.py", "tests/test_ci_scripts.py"]) == (
        "tests/test_ci_quality_scope.py",
        "tests/test_ci_scripts.py",
    )


@pytest.mark.parametrize(
    "path",
    [
        "../tests/test_ci_scripts.py", "/tmp/test_ci_scripts.py", "tests/../contracts/evidence.py",
        "tests//test_ci_scripts.py", "tests/./test_ci_scripts.py", "tests\\test_ci_scripts.py",
        "tests/test_ci_scripts.py;echo", "tests/test_missing_170.py", "contracts/evidence.py",
    ],
)
def test_test_quality_rejects_escaping_or_missing_sources(path: str) -> None:
    with pytest.raises(ValueError, match="test-quality"):
        load_targets().select_test_quality_files([path])


def test_ruff_violation_in_test_is_excluded_from_production_but_detected_when_selected(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    if importlib.util.find_spec("ruff") is None:
        pytest.skip("Ruff is not installed in this synthetic environment")
    targets = load_targets()
    (tmp_path / "tests").mkdir()
    probe = tmp_path / "tests/test_bad_ruff.py"
    probe.write_text("import os\n\ndef test_example():\n    assert True\n", encoding="utf-8")
    monkeypatch.setattr(targets, "__file__", str(tmp_path / "scripts/quality_targets.py"))
    assert targets.main(["quality"]) == 0
    prod_paths = capsys.readouterr().out.split()
    assert "tests/test_bad_ruff.py" not in prod_paths
    assert targets.main(["test-quality", "--changed-test", "tests/test_bad_ruff.py"]) == 0
    selected_paths = capsys.readouterr().out.split()
    assert selected_paths == ["tests/test_bad_ruff.py"]
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--config", str(ROOT / "pyproject.toml"), str(tmp_path / selected_paths[0])],
        capture_output=True, text=True, check=False, timeout=30,
    )
    assert result.returncode == 1
    assert "F401" in result.stdout
    # Exercise the documented no-shell execution route against the same selected violation.
    assert targets.main(["test-quality", "--changed-test", "tests/test_bad_ruff.py", "--ruff-check"]) == 1



@pytest.mark.parametrize("kind", ["root", "intermediate", "file"])
def test_optional_test_quality_rejects_symlinks_in_any_component(kind: str, tmp_path: Path, monkeypatch) -> None:
    targets = load_targets()
    checkout = tmp_path / "checkout"
    (checkout / "scripts").mkdir(parents=True)
    external = tmp_path / "external"
    external.mkdir()
    (external / "test_bad.py").write_text("pass\\n", encoding="utf-8")
    tests = checkout / "tests"
    if kind == "root":
        link = tests
        target = external
        selected = "tests/test_bad.py"
    elif kind == "intermediate":
        tests.mkdir()
        link = tests / "nested"
        target = external
        selected = "tests/nested/test_bad.py"
    else:
        tests.mkdir()
        link = tests / "test_bad.py"
        target = external / "test_bad.py"
        selected = "tests/test_bad.py"
    try:
        link.symlink_to(target, target_is_directory=kind != "file")
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"Filesystem cannot create symlink: {error}")
    monkeypatch.setattr(targets, "__file__", str(checkout / "scripts/quality_targets.py"))
    with pytest.raises(ValueError, match="test-quality"):
        targets.select_test_quality_files([selected])
    if kind == "root":
        with pytest.raises(ValueError, match="test-quality"):
            targets.select_test_quality_files([])



def test_test_quality_rejected_selection_never_launches_ruff(monkeypatch) -> None:
    """A failed selection cannot become an empty-argument Ruff invocation."""
    targets = load_targets()
    invocations: list[object] = []

    def fake_run(*args, **kwargs):
        invocations.append((args, kwargs))
        raise AssertionError("Ruff must not be invoked for invalid targets")

    monkeypatch.setattr(targets.subprocess, "run", fake_run)
    with pytest.raises(SystemExit) as error:
        targets.main(["test-quality", "--changed-test", "tests/does-not-exist-170.py", "--ruff-check"])
    assert error.value.code == 2
    assert invocations == []


def test_test_quality_ruff_direct_invocation_uses_exact_selection_and_propagates_failure(monkeypatch) -> None:
    """Run only the selected paths and preserve the tool's actual return code."""
    targets = load_targets()
    invocations: list[tuple[object, object]] = []

    def fake_run(command, **kwargs):
        invocations.append((command, kwargs))
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(targets.subprocess, "run", fake_run)
    assert targets.main([
        "test-quality",
        "--changed-test", "tests/test_ci_scripts.py",
        "--changed-test", "tests/test_ci_quality_scope.py",
        "--ruff-check",
    ]) == 1
    assert len(invocations) == 1
    command, kwargs = invocations[0]
    assert command == [
        sys.executable, "-m", "ruff", "check",
        "tests/test_ci_quality_scope.py", "tests/test_ci_scripts.py",
    ]
    assert kwargs == {"cwd": ROOT, "check": False, "timeout": 900}


@pytest.mark.parametrize("argv", [
    ["quality", "--ruff-check"],
    ["typing", "--ruff-check"],
    ["test-quality", "--ruff-check", "--provenance"],
])
def test_test_quality_run_mode_does_not_widen_other_profiles(argv: list[str]) -> None:
    targets = load_targets()
    with pytest.raises(SystemExit) as error:
        targets.main(argv)
    assert error.value.code == 2


def test_test_quality_provenance_is_diagnostic_not_gate_claim() -> None:
    command = [
        sys.executable, str(TARGETS_PATH), "test-quality", "--changed-test",
        "tests/test_ci_quality_scope.py", "--provenance",
    ]
    result = subprocess.run(command, cwd=ROOT, check=True, text=True, capture_output=True, timeout=30)
    metadata = json.loads(result.stdout)
    assert metadata["profile"] == "test-quality"
    assert metadata["targets"] == ["tests/test_ci_quality_scope.py"]
    assert metadata["configPath"] == "pyproject.toml"
    assert len(metadata["configSha256"]) == 64
    assert metadata["lockPath"].endswith(".lock")
    assert len(metadata["lockSha256"]) == 64
    assert isinstance(metadata["ruffVersion"], str)
    assert "no lint PASS" in metadata["evidence"]


def test_test_quality_remains_optional_in_local_and_hosted_ci() -> None:
    assert "test-quality" not in (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "TEST_QUALITY_PATHS" not in (ROOT / "scripts/ci.py").read_text(encoding="utf-8")
