from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills" / "agents-md-architect" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from agents_md_gate_sources import classify_gate_sources  # noqa: E402
from agents_md_python_imports import collect_imported_libraries  # noqa: E402
from agents_md_source_types import MAX_IMPORT_CONTEXTS, ModuleInvocation, TaskSourceScan  # noqa: E402
from discover_repository import discover  # noqa: E402


def _write_script(root: Path, name: str, text: str = "VALUE = 1\n") -> Path:
    path = root / "scripts" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _write_workflow(root: Path, run_line: str) -> None:
    workflow = root / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text(
        f"jobs:\n  verify:\n    runs-on: ubuntu-24.04\n    steps:\n      - run: {run_line}\n",
        encoding="utf-8",
    )


@pytest.mark.parametrize("command", ["python -u -m tools.validator", "python -X dev -m tools.validator"])
def test_python_module_options_before_m_are_resolved(command: str, tmp_path: Path) -> None:
    package = tmp_path / "tools"
    package.mkdir()
    (package / "__init__.py").write_text("\n", encoding="utf-8")
    (package / "validator.py").write_text("VALUE = 1\n", encoding="utf-8")
    _write_workflow(tmp_path, command)

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    row = next(source for source in inventory.sources if source.path == "tools/validator.py")
    assert row.classification == "task_entrypoint"
    assert row.counted is True
    assert not inventory.issues


def test_python_script_arguments_do_not_become_module_invocations(tmp_path: Path) -> None:
    _write_script(tmp_path, "check.py")
    _write_workflow(tmp_path, "python scripts/check.py -m tools.validator")

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    row = next(source for source in inventory.sources if source.path == "scripts/check.py")
    assert row.classification == "task_entrypoint"
    assert row.counted is True
    assert not inventory.issues


@pytest.mark.parametrize("scope", ["workflow", "job", "step"])
def test_declared_pythonpath_environment_resolves_modules_at_each_scope(scope: str, tmp_path: Path) -> None:
    module = tmp_path / ".agents" / "tools" / "validator.py"
    module.parent.mkdir(parents=True)
    module.write_text("VALUE = 1\n", encoding="utf-8")
    workflow_env = "env:\n  PYTHONPATH: .agents\n" if scope == "workflow" else ""
    job_env = "    env:\n      PYTHONPATH: .agents\n" if scope == "job" else ""
    step_env = "        env:\n          PYTHONPATH: .agents\n" if scope == "step" else ""
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        f"{workflow_env}"
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        f"{job_env}"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - name: Invoke repository module\n"
        f"{step_env}"
        "        run: python -m tools.validator\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    row = next(source for source in inventory.sources if source.path == ".agents/tools/validator.py")
    assert row.classification == "task_entrypoint"
    assert row.counted is True
    assert not inventory.issues


def test_pwd_pythonpath_expansion_uses_invocation_working_directory(tmp_path: Path) -> None:
    module = tmp_path / ".agents" / "tools" / "validator.py"
    module.parent.mkdir(parents=True)
    module.write_text("VALUE = 1\n", encoding="utf-8")
    _write_workflow(tmp_path, "PYTHONPATH=$PWD/.agents python -m tools.validator")

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    row = next(source for source in inventory.sources if source.path == ".agents/tools/validator.py")
    assert row.classification == "task_entrypoint"
    assert row.counted is True
    assert not inventory.issues


@pytest.mark.parametrize(("checkout_path", "expected_issue"), [(None, False), ("candidate", True)])
def test_github_workspace_pythonpath_requires_known_root_checkout(
    checkout_path: str | None,
    expected_issue: bool,
    tmp_path: Path,
) -> None:
    module = tmp_path / ".agents" / "tools" / "validator.py"
    module.parent.mkdir(parents=True)
    module.write_text("VALUE = 1\n", encoding="utf-8")
    checkout_options = f"        with:\n          path: {checkout_path}\n" if checkout_path else ""
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "env:\n"
        "  PYTHONPATH: $GITHUB_WORKSPACE/.agents\n"
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        f"{checkout_options}"
        "      - run: python -m tools.validator\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert bool(inventory.issues) is expected_issue
    if expected_issue:
        assert any("PYTHONPATH workspace root is unresolved" in issue for issue in inventory.issues)
    else:
        row = next(source for source in inventory.sources if source.path == ".agents/tools/validator.py")
        assert row.counted is True


def test_unresolved_pythonpath_variable_makes_module_inventory_incomplete(tmp_path: Path) -> None:
    module = tmp_path / ".agents" / "tools" / "validator.py"
    module.parent.mkdir(parents=True)
    module.write_text("VALUE = 1\n", encoding="utf-8")
    _write_workflow(tmp_path, "PYTHONPATH=$UNKNOWN_ROOT/.agents python -m tools.validator")

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert any("PYTHONPATH" in issue and "unresolved" in issue for issue in inventory.issues)
    row = next(source for source in inventory.sources if source.path == ".agents/tools/validator.py")
    assert row.classification == "helper"
    assert row.counted is False


def test_unresolved_pythonpath_variable_for_direct_script_is_incomplete(tmp_path: Path) -> None:
    _write_script(tmp_path, "check.py", "from tools.validator import validate\n")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "env:\n"
        "  PYTHONPATH: $UNKNOWN_ROOT/.agents\n"
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - run: python scripts/check.py\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert any("PYTHONPATH" in issue and "unresolved" in issue for issue in inventory.issues)


@pytest.mark.parametrize("command", ["python3.14 scripts/check.py", "python -u scripts/check.py"])
def test_versioned_or_flagged_python_direct_scripts_are_resolved(command: str, tmp_path: Path) -> None:
    _write_script(tmp_path, "check.py")
    _write_workflow(tmp_path, command)

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    row = next(source for source in inventory.sources if source.path == "scripts/check.py")
    assert row.classification == "task_entrypoint"
    assert row.counted is True
    assert not inventory.issues


def test_direct_script_pythonpath_resolves_from_working_directory(tmp_path: Path) -> None:
    _write_script(tmp_path, "check.py", "from tools.helper import VALUE\n")
    helper = tmp_path / ".agents" / "tools" / "helper.py"
    helper.parent.mkdir(parents=True)
    helper.write_text("VALUE = 1\n", encoding="utf-8")
    _write_workflow(tmp_path, "PYTHONPATH=.agents python scripts/check.py")

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    row = next(source for source in inventory.sources if source.path == ".agents/tools/helper.py")
    assert row.classification == "library"
    assert row.counted is False
    assert not inventory.issues


def test_import_file_budget_counts_unique_paths_across_contexts(tmp_path: Path) -> None:
    entrypoint = tmp_path / "entry.py"
    entrypoint.write_text("import helper\n", encoding="utf-8")
    for relative in ("helper.py", "root-a/helper.py", "root-b/helper.py"):
        helper = tmp_path / relative
        helper.parent.mkdir(parents=True, exist_ok=True)
        helper.write_text("VALUE = 1\n", encoding="utf-8")
    invocations = tuple(
        ModuleInvocation(
            "entry.py",
            f"entry_{index}",
            ("root-a",) if index == 255 else ("root-b",) if index == 256 else (".",),
            f"workflow:{index}",
        )
        for index in range(257)
    )
    task_sources = TaskSourceScan(
        references={"entry.py": ()},
        module_invocations={"entry.py": invocations},
        unresolved_module_candidates={},
        direct_python={},
        package_initializers={},
        external_sources={},
        issues=(),
    )

    imported, issues = collect_imported_libraries(tmp_path, discover(tmp_path), task_sources)

    assert {"helper.py", "root-a/helper.py", "root-b/helper.py"} <= set(imported)
    assert not issues


def test_import_context_budget_fails_closed_after_distinct_file_budget(tmp_path: Path) -> None:
    (tmp_path / "entry.py").write_text("VALUE = 1\n", encoding="utf-8")
    invocations = tuple(
        ModuleInvocation("entry.py", f"entry_{index}", (".",), f"workflow:{index}")
        for index in range(MAX_IMPORT_CONTEXTS + 1)
    )
    task_sources = TaskSourceScan(
        references={"entry.py": ()},
        module_invocations={"entry.py": invocations},
        unresolved_module_candidates={},
        direct_python={},
        package_initializers={},
        external_sources={},
        issues=(),
    )

    _imported, issues = collect_imported_libraries(tmp_path, discover(tmp_path), task_sources)

    assert any(f"{MAX_IMPORT_CONTEXTS} contexts" in issue for issue in issues)


def test_repeated_wrapper_calls_in_equivalent_context_preserve_origins_without_budget_overflow(
    tmp_path: Path,
) -> None:
    _write_script(
        tmp_path, "wrapper.py", "import subprocess\nsubprocess.run(['python', 'scripts/nested.py'], check=True)\n"
    )
    _write_script(tmp_path, "nested.py")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    step_lines = "\n".join("      - run: python scripts/wrapper.py" for _ in range(257))
    workflow.write_text(
        f"jobs:\n  verify:\n    runs-on: ubuntu-24.04\n    steps:\n{step_lines}\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    wrapper = next(source for source in inventory.sources if source.path == "scripts/wrapper.py")
    nested = next(source for source in inventory.sources if source.path == "scripts/nested.py")
    assert wrapper.counted is True
    assert len(wrapper.origins) == 257
    assert nested.counted is True
    assert not any("task-wrapper scan exceeds" in issue for issue in inventory.issues)
