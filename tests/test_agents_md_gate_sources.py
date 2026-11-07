from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills" / "agents-md-architect" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from agents_md_gate_sources import (  # noqa: E402
    GATE_SOURCE_POLICY_REVISION,
    classify_gate_sources,
)
from agents_md_source_io import read_bounded  # noqa: E402
from agents_md_source_types import MAX_CLASSIFIER_FILE_BYTES  # noqa: E402
from audit_agents_md import _known_gate_commands_with_inventory  # noqa: E402
from discover_repository import discover  # noqa: E402

STACK_HASSIO_PRE_FIX_REVISION = "414dd5467da6dfc42c537878925eb10246b6fb29"
STACK_HASSIO_FIX_REVISION = "14496ffdfd2f05d81a7d89818e086e5e284c21c6"
STACK_HASSIO_REMOVED_ENTRYPOINT = "scripts/maintenance/finalize_pr10_bot_review.py"


def _write_script(root: Path, name: str, text: str = "VALUE = 1\n", *, executable: bool = False) -> Path:
    path = root / "scripts" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if executable:
        path.chmod(0o755)
    return path


def test_helper_does_not_consume_gate_budget(tmp_path: Path) -> None:
    _write_script(tmp_path, "helper.py")
    discovery = discover(tmp_path)
    inventory = classify_gate_sources(tmp_path, discovery, limit=64)
    helper = next(item for item in inventory.sources if item.path == "scripts/helper.py")
    assert helper.classification == "helper"
    assert helper.counted is False
    assert inventory.count == 0
    assert inventory.headroom == 64


def test_python_main_and_ci_referenced_script_are_entrypoints(tmp_path: Path) -> None:
    _write_script(tmp_path, "main.py", "if __name__ == '__main__':\n    print('run')\n")
    _write_script(tmp_path, "referenced.sh", "echo ok\n")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  verify:\n    runs-on: ubuntu-24.04\n    steps:\n      - run: bash scripts/referenced.sh\n",
        encoding="utf-8",
    )
    discovery = discover(tmp_path)
    inventory = classify_gate_sources(tmp_path, discovery, limit=64)
    counted = {item.path for item in inventory.sources if item.counted}
    assert ".github/workflows/ci.yml" in counted
    assert "scripts/main.py" in counted
    assert "scripts/referenced.sh" in counted
    assert inventory.count == 3


def test_referenced_entrypoint_counts_after_move_outside_scripts_and_bin(tmp_path: Path) -> None:
    entrypoint = tmp_path / "tools" / "release" / "check.sh"
    entrypoint.parent.mkdir(parents=True)
    entrypoint.write_text("echo ok\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  verify:\n    runs-on: ubuntu-24.04\n    steps:\n      - run: bash tools/release/check.sh\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    row = next(item for item in inventory.sources if item.path == "tools/release/check.sh")
    assert row.classification == "task_entrypoint"
    assert row.counted is True
    assert "public repository task surface" in row.reason


@pytest.mark.skipif(os.name == "nt", reason="portable chmod semantics are not available on Windows")
def test_executable_bit_alone_does_not_reclassify_helper(tmp_path: Path) -> None:
    helper = _write_script(tmp_path, "helper.py", executable=True)
    assert os.access(helper, os.X_OK)

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    row = next(item for item in inventory.sources if item.path == "scripts/helper.py")
    assert row.classification == "helper"
    assert row.counted is False


@pytest.mark.skipif(os.name == "nt", reason="portable chmod semantics are not available on Windows")
def test_executable_shebang_script_counts_without_reference(tmp_path: Path) -> None:
    entrypoint = _write_script(tmp_path, "release.sh", "#!/bin/sh\nexit 0\n", executable=True)
    assert os.access(entrypoint, os.X_OK)

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    row = next(item for item in inventory.sources if item.path == "scripts/release.sh")
    assert row.classification == "task_entrypoint"
    assert row.counted is True
    assert "shebang" in row.reason


def test_sixty_four_true_entrypoints_plus_helpers_has_zero_headroom_not_failure(tmp_path: Path) -> None:
    for index in range(64):
        _write_script(
            tmp_path,
            f"task_{index}.py",
            "if __name__ == '__main__':\n    pass\n",
        )
    for index in range(20):
        _write_script(tmp_path, f"helper_{index}.py")
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    assert inventory.count == 64
    assert inventory.headroom == 0


def test_sixty_five_true_entrypoints_exceeds_budget(tmp_path: Path) -> None:
    for index in range(65):
        _write_script(
            tmp_path,
            f"task_{index}.py",
            "if __name__ == '__main__':\n    pass\n",
        )
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    assert inventory.count == 65
    assert inventory.headroom == -1


def test_bin_namespace_is_an_explicit_entrypoint_surface(tmp_path: Path) -> None:
    path = tmp_path / "bin" / "verify"
    path.parent.mkdir()
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    row = next(item for item in inventory.sources if item.path == "bin/verify")
    assert row.counted is True
    assert row.classification == "task_entrypoint"


def test_policy_revision_is_explicit_and_stable(tmp_path: Path) -> None:
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    assert inventory.policy_revision == GATE_SOURCE_POLICY_REVISION
    policy = ROOT / "skills/agents-md-architect/references/gate-source-budget.md"
    text = policy.read_text(encoding="utf-8")
    assert f"`{GATE_SOURCE_POLICY_REVISION}`" in text
    assert "PYTHONPATH=.agents python -m" in text
    assert "classified as `library`" in text


def test_stack_hassio_incident_shape_does_not_count_an_unreferenced_helper(tmp_path: Path) -> None:
    """Regression anchored to the Sep 2026 stack-hassio gate-source incident."""
    for index in range(64):
        _write_script(
            tmp_path,
            f"task_{index}.py",
            "if __name__ == '__main__':\n    pass\n",
        )
    helper = tmp_path / STACK_HASSIO_REMOVED_ENTRYPOINT
    helper.parent.mkdir(parents=True, exist_ok=True)
    helper.write_text("def finalize():\n    return 0\n", encoding="utf-8")

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    row = next(item for item in inventory.sources if item.path == STACK_HASSIO_REMOVED_ENTRYPOINT)
    assert STACK_HASSIO_PRE_FIX_REVISION != STACK_HASSIO_FIX_REVISION
    assert row.counted is False
    assert inventory.count == 64
    assert inventory.headroom == 0


def _write_workflow(root: Path, run_line: str) -> None:
    workflow = root / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text(
        f"jobs:\n  verify:\n    runs-on: ubuntu-24.04\n    steps:\n      - run: {run_line}\n",
        encoding="utf-8",
    )


def test_module_invocation_with_pythonpath_counts_after_relocation(tmp_path: Path) -> None:
    """#212: a module invoked through PYTHONPATH stays covered after relocation."""
    module = tmp_path / ".agents" / "tools" / "validator.py"
    module.parent.mkdir(parents=True)
    sentinel = tmp_path / "candidate-code-was-executed"
    module.write_text(
        f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('executed', encoding='utf-8')\n",
        encoding="utf-8",
    )
    _write_workflow(tmp_path, "PYTHONPATH=.agents python -m tools.validator")

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    row = next(item for item in inventory.sources if item.path == ".agents/tools/validator.py")
    assert row.classification == "task_entrypoint"
    assert row.counted is True
    assert "module" in row.reason
    assert ".github/workflows/ci.yml:5" in row.origins
    assert not sentinel.exists(), "source discovery must never execute candidate code"


def test_candidate_checkout_working_directory_resolves_against_candidate_root(
    tmp_path: Path,
) -> None:
    module = tmp_path / ".agents" / "tools" / "validator.py"
    module.parent.mkdir(parents=True)
    module.write_text("VALUE = 1\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  validate:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          ref: ${{ github.event.pull_request.head.sha }}\n"
        "          path: candidate\n"
        "      - run: PYTHONPATH=.agents python -m tools.validator\n"
        "        working-directory: candidate\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    row = next(item for item in inventory.sources if item.path == ".agents/tools/validator.py")
    assert row.classification == "task_entrypoint"
    assert row.counted is True
    assert any("ci.yml" in origin for origin in row.origins)


def test_candidate_checkout_path_prefix_resolves_to_owned_repository_source(tmp_path: Path) -> None:
    module = tmp_path / ".agents/tools/validator.py"
    module.parent.mkdir(parents=True)
    module.write_text("VALUE = 1\n", encoding="utf-8")
    workflow = tmp_path / ".github/workflows/ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  validate:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          ref: ${{ github.event.pull_request.head.sha }}\n"
        "          path: candidate\n"
        "      - run: python candidate/.agents/tools/validator.py\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    row = next(source for source in inventory.sources if source.path == ".agents/tools/validator.py")
    assert row.classification == "task_entrypoint"
    assert row.counted is True
    assert not inventory.issues


def test_module_invocation_coverage_is_path_independent(tmp_path: Path) -> None:
    """#212 negative: relocating a genuinely invoked module cannot escape coverage."""
    for location, run_line in (
        ("scripts/validator.py", "python scripts/validator.py"),
        (".agents/tools/validator.py", "PYTHONPATH=.agents python -m tools.validator"),
    ):
        repo = tmp_path / location.replace("/", "_")
        module = repo / location
        module.parent.mkdir(parents=True)
        module.write_text("def main() -> None:\n    pass\n", encoding="utf-8")
        _write_workflow(repo, run_line)
        inventory = classify_gate_sources(repo, discover(repo), limit=64)
        row = next(item for item in inventory.sources if item.path == location)
        assert row.counted is True, (location, row.reason)


def test_import_only_helper_stays_uncounted(tmp_path: Path) -> None:
    """#212: an import-only library must not become a false entrypoint."""
    helper = tmp_path / ".agents" / "tools" / "helper.py"
    helper.parent.mkdir(parents=True)
    helper.write_text("VALUE = 1\n", encoding="utf-8")
    entrypoint = tmp_path / ".agents" / "tools" / "validator.py"
    entrypoint.write_text("from tools.helper import VALUE\n", encoding="utf-8")
    _write_workflow(tmp_path, "PYTHONPATH=.agents python -m tools.validator")

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    helper_row = next(item for item in inventory.sources if item.path == ".agents/tools/helper.py")
    assert helper_row.classification == "library"
    assert helper_row.counted is False
    assert "imported" in helper_row.reason
    entrypoint_row = next(item for item in inventory.sources if item.path == ".agents/tools/validator.py")
    assert entrypoint_row.counted is True
    assert inventory.count == 2  # CI workflow + invoked module; helper is evidence, not another entrypoint


def test_audit_receipt_includes_imported_library_without_counting_it(
    tmp_path: Path,
) -> None:
    helper = tmp_path / ".agents" / "tools" / "helper.py"
    helper.parent.mkdir(parents=True)
    helper.write_text("VALUE = 1\n", encoding="utf-8")
    entrypoint = tmp_path / ".agents" / "tools" / "validator.py"
    entrypoint.write_text("from tools.helper import VALUE\n", encoding="utf-8")
    _write_workflow(tmp_path, "PYTHONPATH=.agents python -m tools.validator")

    _known, inventory, findings = _known_gate_commands_with_inventory(tmp_path, discover(tmp_path))

    sources = {item.path: item for item in inventory.sources}
    assert sources[".agents/tools/validator.py"].classification == "task_entrypoint"
    assert sources[".agents/tools/validator.py"].counted is True
    assert sources[".agents/tools/helper.py"].classification == "library"
    assert sources[".agents/tools/helper.py"].counted is False
    assert inventory.count == 2
    assert not any(f.code == "evidence.incomplete-gate-source-inventory" for f in findings)


def test_module_invocation_without_matching_file_is_not_fabricated(tmp_path: Path) -> None:
    _write_workflow(tmp_path, "PYTHONPATH=.agents python -m ghost.module")
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    assert all(not item.path.startswith("ghost") for item in inventory.sources)
    assert inventory.count == 1  # only the CI workflow itself


def test_missing_module_under_explicit_repository_pythonpath_is_incomplete(tmp_path: Path) -> None:
    _write_workflow(tmp_path, "PYTHONPATH=.agents python -m validator")

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert inventory.count == 1
    assert any("not found" in issue and "validator" in issue for issue in inventory.issues)


def test_missing_nested_repository_module_without_pythonpath_is_incomplete(tmp_path: Path) -> None:
    package = tmp_path / "tools"
    package.mkdir()
    (package / "__init__.py").write_text("\n", encoding="utf-8")
    _write_workflow(tmp_path, "python -m tools.missing_validator")

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert inventory.count == 1
    assert any("not found" in issue and "tools.missing_validator" in issue for issue in inventory.issues)


def test_missing_direct_script_path_is_incomplete(tmp_path: Path) -> None:
    _write_workflow(tmp_path, "python tools/missing_validator.py")

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert inventory.count == 1
    assert any("missing_validator.py" in issue and "not found" in issue for issue in inventory.issues)


def test_direct_python_wrapper_discovers_nested_task_script(tmp_path: Path) -> None:
    _write_script(
        tmp_path,
        "wrapper.py",
        "import subprocess\nsubprocess.run(['python3', 'scripts/nested_task.py'], check=True)\n",
    )
    _write_script(tmp_path, "nested_task.py")
    _write_workflow(tmp_path, "python scripts/wrapper.py")

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    row = next(source for source in inventory.sources if source.path == "scripts/nested_task.py")
    assert row.classification == "task_entrypoint"
    assert row.counted is True
    assert row.origins == ("scripts/wrapper.py",)
    assert not inventory.issues


def test_unmatched_absolute_script_path_is_incomplete(tmp_path: Path) -> None:
    _write_workflow(tmp_path, "python /opt/validator.py")

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert inventory.count == 1
    assert any("outside repository" in issue or "escapes repository" in issue for issue in inventory.issues)


@pytest.mark.parametrize(
    "launcher",
    [
        "./.venv/Scripts/python.exe",
        "${{ runner.os == 'Windows' && './.venv/Scripts/python.exe' || 'python' }}",
    ],
)
def test_generated_virtualenv_interpreter_is_not_misclassified_as_missing_source(tmp_path: Path, launcher: str) -> None:
    _write_script(tmp_path, "install_locked.py", "def main() -> None:\n    pass\n")
    _write_workflow(tmp_path, f"{launcher} scripts/install_locked.py")

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert inventory.count == 2
    assert not inventory.issues
    assert any(source.path == "scripts/install_locked.py" and source.counted for source in inventory.sources)


def test_root_module_invocation_without_pythonpath_resolves(tmp_path: Path) -> None:
    (tmp_path / "validator.py").write_text("VALUE = 1\n", encoding="utf-8")
    _write_workflow(tmp_path, "python -m validator")

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    row = next(source for source in inventory.sources if source.path == "validator.py")
    assert row.classification == "task_entrypoint"
    assert row.counted is True
    assert inventory.count == 2


def test_nested_module_invocation_without_pythonpath_resolves(tmp_path: Path) -> None:
    package = tmp_path / "tools"
    package.mkdir()
    (package / "__init__.py").write_text("\n", encoding="utf-8")
    (package / "validator.py").write_text("VALUE = 1\n", encoding="utf-8")
    _write_workflow(tmp_path, "python -m tools.validator")

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    row = next(source for source in inventory.sources if source.path == "tools/validator.py")
    assert row.classification == "task_entrypoint"
    assert row.counted is True
    assert inventory.count == 2


@pytest.mark.skipif(sys.platform == "win32", reason="Windows symlink creation may require elevated privileges")
def test_module_symlink_escape_is_incomplete_without_reading_target(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside-validator.py"
    sentinel = tmp_path.parent / f"{tmp_path.name}-executed"
    outside.write_text(
        f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('executed', encoding='utf-8')\n",
        encoding="utf-8",
    )
    module = tmp_path / ".agents/tools/validator.py"
    module.parent.mkdir(parents=True)
    module.symlink_to(outside)
    _write_workflow(tmp_path, "PYTHONPATH=.agents python -m tools.validator")

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert inventory.count == 1
    assert inventory.issues
    assert not sentinel.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="Windows symlink creation may require elevated privileges")
def test_symlinked_module_namespace_is_incomplete_without_following_it(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside-package"
    outside.mkdir()
    (outside / "__init__.py").write_text("\n", encoding="utf-8")
    (outside / "validator.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "tools").symlink_to(outside, target_is_directory=True)
    _write_workflow(tmp_path, "python -m tools.validator")

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert inventory.count == 1
    assert any("not found" in issue and "tools.validator" in issue for issue in inventory.issues)


def test_oversized_invoked_source_is_incomplete(tmp_path: Path) -> None:
    source = tmp_path / "scripts" / "oversized.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 1\n" * 300_000, encoding="utf-8")
    _write_workflow(tmp_path, "python scripts/oversized.py")

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert inventory.count == 2
    assert any("maximum supported size" in issue and "oversized.py" in issue for issue in inventory.issues)


def test_bounded_reader_never_uses_unbounded_read_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "oversized.py"
    source.write_bytes(b"x" * (MAX_CLASSIFIER_FILE_BYTES + 1))

    def reject_unbounded_read(_path: Path) -> bytes:
        pytest.fail("bounded source reader called Path.read_bytes")

    monkeypatch.setattr(Path, "read_bytes", reject_unbounded_read)
    with pytest.raises(ValueError, match="maximum supported size"):
        read_bounded(tmp_path, "oversized.py")


def test_ambiguous_module_roots_fail_closed(tmp_path: Path) -> None:
    for root in (".agents", "."):
        module = tmp_path / root / "tools" / "validator.py"
        module.parent.mkdir(parents=True, exist_ok=True)
        module.write_text("VALUE = 1\n", encoding="utf-8")
    _write_workflow(tmp_path, "PYTHONPATH=.agents:. python -m tools.validator")

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert any("ambiguous module resolution" in issue and "validator" in issue for issue in inventory.issues)


def test_wrapper_chain_beyond_bound_is_incomplete(tmp_path: Path) -> None:
    for index in range(5):
        wrapper = tmp_path / "scripts" / f"wrapper-{index}.sh"
        wrapper.parent.mkdir(parents=True, exist_ok=True)
        command = f"bash scripts/wrapper-{index + 1}.sh" if index < 4 else "true"
        wrapper.write_text(f"#!/bin/sh\n{command}\n", encoding="utf-8")
    _write_workflow(tmp_path, "bash scripts/wrapper-0.sh")

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert any("wrapper depth exceeds" in issue for issue in inventory.issues)


def test_duplicate_module_references_count_one_entrypoint(tmp_path: Path) -> None:
    module = tmp_path / ".agents/tools/validator.py"
    module.parent.mkdir(parents=True)
    module.write_text("VALUE = 1\n", encoding="utf-8")
    _write_workflow(
        tmp_path,
        "PYTHONPATH=.agents python -m tools.validator && PYTHONPATH=.agents python -m tools.validator",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert inventory.count == 2
    assert sum(source.path == ".agents/tools/validator.py" and source.counted for source in inventory.sources) == 1


def test_actual_auditor_cli_reports_relocated_source_overflow(tmp_path: Path) -> None:
    for index in range(63):
        _write_script(tmp_path, f"task-{index}.py", "if __name__ == '__main__':\n    pass\n")
    module = tmp_path / ".agents/tools/validator.py"
    module.parent.mkdir(parents=True)
    module.write_text("def main() -> None:\n    pass\n", encoding="utf-8")
    _write_workflow(tmp_path, "PYTHONPATH=.agents python -m tools.validator")

    completed = subprocess.run(
        [sys.executable, str(TOOLS / "audit_agents_md.py"), "--format", "json", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 1
    report = json.loads(completed.stdout)
    inventory = report["gate_source_inventory"]
    assert inventory["count"] == 65
    assert inventory["headroom"] == -1
    assert any(finding["code"] == "evidence.too-many-gate-sources" for finding in report["findings"])


def test_module_invocation_through_shell_wrapper_is_traced(tmp_path: Path) -> None:
    module = tmp_path / ".agents" / "tools" / "validator.py"
    module.parent.mkdir(parents=True)
    module.write_text("VALUE = 1\n", encoding="utf-8")
    wrapper = tmp_path / ".agents" / "tools" / "run-validator.sh"
    wrapper.write_text(
        'run afds env PYTHONPATH=.agents "$PY" -m tools.validator\n',
        encoding="utf-8",
    )
    _write_workflow(tmp_path, "bash .agents/tools/run-validator.sh")

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    row = next(item for item in inventory.sources if item.path == ".agents/tools/validator.py")
    assert row.counted is True
    assert any("run-validator.sh" in origin for origin in row.origins)


def test_auditor_budget_cannot_be_evaded_by_relocating_invoked_module(
    tmp_path: Path,
) -> None:
    """The actual AGENTS audit counts relocated task code at the exact 64 cap."""
    for index in range(63):
        _write_script(
            tmp_path,
            f"task_{index}.py",
            "if __name__ == '__main__':\n    pass\n",
        )
    module = tmp_path / ".agents" / "tools" / "validator.py"
    module.parent.mkdir(parents=True)
    module.write_text("def main() -> None:\n    pass\n", encoding="utf-8")
    _write_workflow(tmp_path, "PYTHONPATH=.agents python -m tools.validator")

    discovery = discover(tmp_path)
    _known, inventory, findings = _known_gate_commands_with_inventory(tmp_path, discovery)

    assert inventory.count == 65
    assert inventory.headroom == -1
    module_row = next(item for item in inventory.sources if item.path == ".agents/tools/validator.py")
    assert module_row.counted is True
    assert any(
        finding.code == "evidence.too-many-gate-sources" and "Found 65" in finding.message for finding in findings
    )


def _write_stack_hassio_migration_fixture(root: Path, *, moved: bool) -> str:
    task_dir = root / ".agents" / "tools" if moved else root / "scripts" / "maintenance"
    task_dir.mkdir(parents=True)
    helper = task_dir / "afds_report_output.py"
    helper.write_text("def write_report() -> None:\n    pass\n", encoding="utf-8")
    validator = task_dir / "validate_skill_migration.py"
    validator.write_text(
        "from tools.afds_report_output import write_report\n"
        if moved
        else "from afds_report_output import write_report\n",
        encoding="utf-8",
    )
    if not moved:
        validator.write_text(
            validator.read_text(encoding="utf-8") + "\nif __name__ == '__main__':\n    write_report()\n",
            encoding="utf-8",
        )
    for index in range(63):
        _write_script(
            root,
            f"task_{index}.py",
            "if __name__ == '__main__':\n    pass\n",
        )
    invocation = (
        "PYTHONPATH=.agents python -m tools.validate_skill_migration --require-baseline"
        if moved
        else "python scripts/maintenance/validate_skill_migration.py --require-baseline"
    )
    _write_workflow(root, invocation)
    return ".agents/tools/validate_skill_migration.py" if moved else "scripts/maintenance/validate_skill_migration.py"


def test_stack_hassio_old_and_moved_entrypoints_have_equivalent_coverage(
    tmp_path: Path,
) -> None:
    inventories = []
    for variant in ("baseline", "relocated"):
        root = tmp_path / variant
        moved = variant == "relocated"
        validator_path = _write_stack_hassio_migration_fixture(root, moved=moved)
        inventory = classify_gate_sources(root, discover(root), limit=64)
        validator = next(item for item in inventory.sources if item.path == validator_path)
        helper_path = ".agents/tools/afds_report_output.py" if moved else "scripts/maintenance/afds_report_output.py"
        helper = next(item for item in inventory.sources if item.path == helper_path)
        assert validator.classification == "task_entrypoint"
        assert validator.counted is True
        assert helper.classification == "library"
        assert helper.counted is False
        assert inventory.count == 65
        assert inventory.headroom == -1
        inventories.append(inventory)

    assert inventories[0].count == inventories[1].count
    assert inventories[0].headroom == inventories[1].headroom


def test_stack_hassio_relocation_cannot_turn_overflow_into_pass(
    tmp_path: Path,
) -> None:
    for variant in ("baseline", "relocated"):
        root = tmp_path / variant
        moved = variant == "relocated"
        _write_stack_hassio_migration_fixture(root, moved=moved)
        _known, inventory, findings = _known_gate_commands_with_inventory(root, discover(root))
        assert inventory.count == 65
        assert inventory.headroom == -1
        assert any(
            finding.code == "evidence.too-many-gate-sources" and "Found 65" in finding.message for finding in findings
        )


def test_pinned_external_checkout_is_listed_but_not_counted(tmp_path: Path) -> None:
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          repository: paulomac1000/ai-skills\n"
        "          ref: 9fff7f7cc212a732fa1dc233ac4225e662280015\n"
        "          path: upstream\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          ref: ${{ github.event.pull_request.head.sha }}\n"
        "          path: candidate\n"
        "      - run: python ../upstream/tools/audit.py\n"
        "        working-directory: candidate\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    external = next(item for item in inventory.sources if item.path.startswith("external:paulomac1000/ai-skills@"))
    assert external.classification == "excluded"
    assert external.counted is False
    assert external.path.endswith("/tools/audit.py")
    assert not inventory.issues


def test_checkout_alias_is_scoped_to_each_workflow_job(tmp_path: Path) -> None:
    source = tmp_path / "scripts/check.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 1\n", encoding="utf-8")
    workflow = tmp_path / ".github/workflows/ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  candidate:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          path: candidate\n"
        "      - run: python candidate/scripts/check.py\n"
        "  external:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          repository: example/validator\n"
        "          ref: 0123456789abcdef0123456789abcdef01234567\n"
        "          path: candidate\n"
        "      - run: python candidate/scripts/check.py\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    sources = {source.path: source for source in inventory.sources}
    local = sources["scripts/check.py"]
    external = sources["external:example/validator@0123456789abcdef0123456789abcdef01234567/scripts/check.py"]
    assert local.classification == "task_entrypoint"
    assert local.counted is True
    assert local.origins == (".github/workflows/ci.yml:8",)
    assert external.classification == "excluded"
    assert external.counted is False
    assert external.origins == (".github/workflows/ci.yml:17",)
    assert not inventory.issues
    _, audit_inventory, findings = _known_gate_commands_with_inventory(tmp_path, discover(tmp_path))
    assert audit_inventory.sources == inventory.sources
    assert not any(finding.code == "evidence.incomplete-gate-source-inventory" for finding in findings)


def test_mixed_candidate_and_authority_checkouts_are_scoped_in_one_job(tmp_path: Path) -> None:
    candidate_script = tmp_path / "scripts/check.py"
    candidate_script.parent.mkdir(parents=True)
    candidate_script.write_text("VALUE = 1\n", encoding="utf-8")
    workflow = tmp_path / ".github/workflows/ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          path: candidate\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          repository: example/authority\n"
        "          ref: 0123456789abcdef0123456789abcdef01234567\n"
        "          path: authority\n"
        "      - run: python candidate/scripts/check.py && python authority/tools/audit.py\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    sources = {source.path: source for source in inventory.sources}
    local = sources["scripts/check.py"]
    external = sources["external:example/authority@0123456789abcdef0123456789abcdef01234567/tools/audit.py"]
    assert local.classification == "task_entrypoint"
    assert local.counted is True
    assert external.classification == "excluded"
    assert external.counted is False
    assert not inventory.issues


def test_checkout_alias_replacement_follows_step_order_within_job(tmp_path: Path) -> None:
    for name in ("before.py", "after_external.py", "after_local.py"):
        _write_script(tmp_path, name)
    workflow = tmp_path / ".github/workflows/ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          path: candidate\n"
        "      - run: python candidate/scripts/before.py\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          repository: example/authority\n"
        "          ref: 0123456789abcdef0123456789abcdef01234567\n"
        "          path: candidate\n"
        "      - run: python candidate/scripts/after_external.py\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          path: candidate\n"
        "      - run: python candidate/scripts/after_local.py\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    sources = {source.path: source for source in inventory.sources}
    assert sources["scripts/before.py"].counted is True
    assert (
        sources[
            "external:example/authority@0123456789abcdef0123456789abcdef01234567/scripts/after_external.py"
        ].classification
        == "excluded"
    )
    assert sources["scripts/after_local.py"].counted is True
    assert not inventory.issues


def test_known_same_repository_workflow_revisions_are_local_checkout_sources(tmp_path: Path) -> None:
    _write_script(tmp_path, "check.py")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  pull-request:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          ref: ${{ github.event.pull_request.head.sha || github.sha }}\n"
        "      - run: python scripts/check.py\n"
        "  release:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          ref: ${{ github.event.workflow_run.head_sha }}\n"
        "      - run: python scripts/check.py\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    row = next(source for source in inventory.sources if source.path == "scripts/check.py")
    assert row.classification == "task_entrypoint"
    assert row.counted is True
    assert len(row.origins) == 2
    assert not inventory.issues


def test_matrix_runner_default_shell_preserves_simple_command_source_evidence(tmp_path: Path) -> None:
    _write_script(tmp_path, "check.py")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    strategy:\n"
        "      matrix:\n"
        "        os: [ubuntu-24.04, windows-2025]\n"
        "    runs-on: ${{ matrix.os }}\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          ref: ${{ github.event.pull_request.head.sha || github.sha }}\n"
        "      - run: python scripts/check.py\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    row = next(source for source in inventory.sources if source.path == "scripts/check.py")
    assert row.classification == "task_entrypoint"
    assert row.counted is True
    assert not inventory.issues


def test_workflow_env_alias_resolves_known_same_repository_checkout_revision(tmp_path: Path) -> None:
    _write_script(tmp_path, "check.py")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "env:\n"
        "  CANDIDATE_SHA: ${{ github.event.pull_request.head.sha || github.sha }}\n"
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          ref: ${{ env.CANDIDATE_SHA }}\n"
        "          path: candidate\n"
        "      - run: python candidate/scripts/check.py\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    row = next(source for source in inventory.sources if source.path == "scripts/check.py")
    assert row.classification == "task_entrypoint"
    assert row.counted is True
    assert not inventory.issues


@pytest.mark.parametrize("scope", ["job", "step"])
def test_nearer_job_or_step_environment_resolves_checkout_revision(scope: str, tmp_path: Path) -> None:
    _write_script(tmp_path, "check.py")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    job_binding = (
        "    env:\n      CANDIDATE_SHA: ${{ github.event.pull_request.head.sha || github.sha }}\n"
        if scope == "job"
        else ""
    )
    step_binding = "        env:\n          CANDIDATE_SHA: ${{ github.sha }}\n" if scope == "step" else ""
    workflow.write_text(
        "env:\n"
        "  CANDIDATE_SHA: ${{ inputs.untrusted_sha }}\n"
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        f"{job_binding}"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        f"{step_binding}"
        "        with:\n"
        "          ref: ${{ env.CANDIDATE_SHA }}\n"
        "          path: candidate\n"
        "      - run: python candidate/scripts/check.py\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    row = next(source for source in inventory.sources if source.path == "scripts/check.py")
    assert row.classification == "task_entrypoint"
    assert row.counted is True
    assert not inventory.issues


def test_unknown_nearer_environment_override_does_not_inherit_allowed_checkout_ref(tmp_path: Path) -> None:
    _write_script(tmp_path, "check.py")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "env:\n"
        "  CANDIDATE_SHA: ${{ github.sha }}\n"
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    env:\n"
        "      CANDIDATE_SHA: ${{ steps.resolve.outputs.revision }}\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          ref: ${{ env.CANDIDATE_SHA }}\n"
        "          path: candidate\n"
        "      - run: python candidate/scripts/check.py\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert any("same-repository checkout revision is unresolved" in issue for issue in inventory.issues)
    row = next(source for source in inventory.sources if source.path == "scripts/check.py")
    assert row.classification == "helper"
    assert row.counted is False


def test_explicit_unsupported_workflow_shell_fails_closed_for_source_commands(tmp_path: Path) -> None:
    _write_script(tmp_path, "check.py")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - shell: cmd\n"
        "        run: python scripts/check.py\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert any("workflow shell is unsupported" in issue for issue in inventory.issues)
    row = next(source for source in inventory.sources if source.path == "scripts/check.py")
    assert row.classification == "helper"
    assert row.counted is False


def test_trusted_lock_checkout_is_explicit_external_source(tmp_path: Path) -> None:
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - id: authority\n"
        "        run: resolve-repository-and-revision-from-trusted-lock\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          repository: ${{ steps.authority.outputs.repository }}\n"
        "          ref: ${{ steps.authority.outputs.revision }}\n"
        "          path: trusted-verifier\n"
        "      - run: python trusted-verifier/tools/audit.py\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    external = next(
        item for item in inventory.sources if item.path.startswith("external:trusted-lock:trusted-verifier/")
    )
    assert external.classification == "excluded"
    assert external.counted is False
    assert "tools/audit.py" in external.path
    assert not inventory.issues


def test_reusable_acceptance_workflow_distinguishes_candidate_and_authority_checkouts(
    tmp_path: Path,
) -> None:
    workflow = tmp_path / ".github" / "workflows" / "consumer-acceptance.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "on:\n"
        "  workflow_call:\n"
        "    inputs:\n"
        "      candidate_repository:\n"
        "        required: true\n"
        "        type: string\n"
        "      candidate_sha:\n"
        "        required: true\n"
        "        type: string\n"
        "jobs:\n"
        "  accept:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          repository: ${{ inputs.candidate_repository }}\n"
        "          ref: ${{ inputs.candidate_sha }}\n"
        "          path: candidate\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          repository: ${{ job.workflow_repository }}\n"
        "          ref: ${{ job.workflow_sha }}\n"
        "          path: authority\n"
        "      - run: python authority/contracts/validate_external_adoption.py --candidate-root candidate\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert not inventory.issues
    external = [source.path for source in inventory.sources if source.classification == "excluded"]
    assert any(path.startswith("external:workflow-authority:") for path in external)


def test_unrecognized_dynamic_checkout_fails_closed(tmp_path: Path) -> None:
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          repository: ${{ inputs.repo }}\n"
        "          ref: ${{ inputs.ref }}\n"
        "          path: external-source\n"
        "      - run: python external-source/tools/check.py\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert any("must pin an immutable full commit SHA" in issue for issue in inventory.issues)
