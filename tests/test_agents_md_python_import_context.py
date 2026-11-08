from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills" / "agents-md-architect" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from agents_md_gate_sources import classify_gate_sources  # noqa: E402
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


@pytest.mark.parametrize(
    ("module", "working_directory", "pythonpath"),
    [
        ("pip", "nested", None),
        ("pip", ".", ".agents"),
        ("json", "nested", None),
    ],
)
def test_known_installed_modules_do_not_look_like_missing_repository_targets(
    module: str,
    working_directory: str,
    pythonpath: str | None,
    tmp_path: Path,
) -> None:
    if working_directory != ".":
        (tmp_path / working_directory).mkdir()
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    pythonpath_env = f"        env:\n          PYTHONPATH: {pythonpath}\n" if pythonpath is not None else ""
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - name: Invoke installed module\n"
        f"        working-directory: {working_directory}\n"
        f"{pythonpath_env}"
        f"        run: python -m {module}\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert not any("not found under declared repository import roots" in issue for issue in inventory.issues)


def test_unknown_module_in_repository_namespace_still_reports_incomplete_inventory(tmp_path: Path) -> None:
    namespace = tmp_path / "tools"
    namespace.mkdir()
    (namespace / "existing.py").write_text("VALUE = 1\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - run: python -m tools.missing\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert any("invoked module 'tools.missing' not found" in issue for issue in inventory.issues)


def test_imported_package_initializer_relative_import_is_included(tmp_path: Path) -> None:
    _write_script(tmp_path, "check.py", "import pkg\n")
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("from . import helper\n", encoding="utf-8")
    (package / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    _write_workflow(tmp_path, "python scripts/check.py")

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    row = next(source for source in inventory.sources if source.path == "pkg/helper.py")
    assert row.classification == "library"
    assert row.counted is False
    assert not inventory.issues


def test_transitive_import_respects_external_checkout_ownership(tmp_path: Path) -> None:
    (tmp_path / "entry.py").write_text("import helper\n", encoding="utf-8")
    external_lookalike = tmp_path / "vendor" / "helper.py"
    external_lookalike.parent.mkdir()
    external_lookalike.write_text("VALUE = 1\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          repository: example/vendor\n"
        "          ref: abcdef0123456789abcdef0123456789abcdef01\n"
        "          path: vendor\n"
        "      - run: PYTHONPATH=vendor python -m entry\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert not any(source.path == "vendor/helper.py" for source in inventory.sources)
    assert any(
        source.path == "external:example/vendor@abcdef0123456789abcdef0123456789abcdef01/helper.py"
        and source.classification == "excluded"
        for source in inventory.sources
    )
    assert not inventory.issues


def test_dotted_import_includes_parent_package_initializers(tmp_path: Path) -> None:
    _write_script(tmp_path, "check.py", "import pkg.mod\n")
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("from . import helper\n", encoding="utf-8")
    (package / "helper.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "mod.py").write_text("VALUE = 2\n", encoding="utf-8")
    _write_workflow(tmp_path, "python scripts/check.py")

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert {"pkg/__init__.py", "pkg/helper.py"} <= {source.path for source in inventory.sources}
    assert all(
        not source.counted for source in inventory.sources if source.path in {"pkg/__init__.py", "pkg/helper.py"}
    )
    assert not inventory.issues


def test_unresolved_pythonpath_does_not_downgrade_direct_entrypoint(tmp_path: Path) -> None:
    module = tmp_path / ".agents" / "tools" / "validator.py"
    module.parent.mkdir(parents=True)
    module.write_text("VALUE = 1\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - run: python .agents/tools/validator.py\n"
        "      - run: PYTHONPATH=$UNKNOWN_ROOT/.agents python -m tools.validator\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    row = next(source for source in inventory.sources if source.path == ".agents/tools/validator.py")
    assert row.classification == "task_entrypoint"
    assert row.counted is True
    assert inventory.count == 2
    assert any("PYTHONPATH" in issue and "unresolved" in issue for issue in inventory.issues)


def test_import_dedup_preserves_distinct_checkout_ownership(tmp_path: Path) -> None:
    (tmp_path / "entry.py").write_text("import helper\n", encoding="utf-8")
    helper = tmp_path / "vendor" / "helper.py"
    helper.parent.mkdir()
    helper.write_text("VALUE = 1\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  owned:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          repository: example/vendor\n"
        "          ref: abcdef0123456789abcdef0123456789abcdef01\n"
        "          path: vendor\n"
        "      - run: PYTHONPATH=vendor python -m entry\n"
        "  local:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - run: PYTHONPATH=vendor python -m entry\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert any(
        source.path == "external:example/vendor@abcdef0123456789abcdef0123456789abcdef01/helper.py"
        and source.classification == "excluded"
        for source in inventory.sources
    )
    assert any(
        source.path == "vendor/helper.py" and source.classification == "library" and not source.counted
        for source in inventory.sources
    )
    assert not inventory.issues


def test_imported_entrypoint_is_traversed_under_importing_context(tmp_path: Path) -> None:
    (tmp_path / "shared.py").write_text("import helper\n", encoding="utf-8")
    (tmp_path / "entry.py").write_text("import shared\n", encoding="utf-8")
    helper = tmp_path / "lib" / "helper.py"
    helper.parent.mkdir()
    helper.write_text("VALUE = 1\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - run: python shared.py\n"
        "      - run: PYTHONPATH=lib python entry.py\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert {row.classification: row.counted for row in inventory.sources if row.path in {"shared.py", "entry.py"}} == {
        "task_entrypoint": True
    }
    row = next(source for source in inventory.sources if source.path == "lib/helper.py")
    assert row.classification == "library"
    assert row.counted is False
    assert not inventory.issues


def test_symlinked_imported_file_reports_incomplete_inventory(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "helper_target.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "entry.py").write_text("import helper\n", encoding="utf-8")
    (tmp_path / "helper.py").symlink_to(outside / "helper_target.py")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  verify:\n    runs-on: ubuntu-24.04\n    steps:\n      - run: python entry.py\n",
        encoding="utf-8",
    )

    discovery = discover(tmp_path)
    inventory = classify_gate_sources(tmp_path, discovery, limit=64)

    assert any("symlink" in issue and "helper" in issue for issue in inventory.issues)
    assert not any(source.path == "helper.py" for source in inventory.sources)


def test_symlinked_package_directory_reports_incomplete_inventory(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "entry.py").write_text("import pkg.mod\n", encoding="utf-8")
    (tmp_path / "pkg").symlink_to(outside, target_is_directory=True)
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  verify:\n    runs-on: ubuntu-24.04\n    steps:\n      - run: python entry.py\n",
        encoding="utf-8",
    )

    discovery = discover(tmp_path)
    inventory = classify_gate_sources(tmp_path, discovery, limit=64)

    assert any("symlink" in issue and "'pkg'" in issue for issue in inventory.issues)
    assert not any(source.path.startswith("pkg/") for source in inventory.sources)


def test_ordinary_missing_module_is_not_reported_as_symlink(tmp_path: Path) -> None:
    (tmp_path / "entry.py").write_text("import json\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  verify:\n    runs-on: ubuntu-24.04\n    steps:\n      - run: python entry.py\n",
        encoding="utf-8",
    )

    discovery = discover(tmp_path)
    inventory = classify_gate_sources(tmp_path, discovery, limit=64)

    assert not any("symlink" in issue for issue in inventory.issues)


def test_workspace_framed_root_inside_candidate_resolves_candidate_relative_files(tmp_path: Path) -> None:
    (tmp_path / "entry.py").write_text("import helper\n", encoding="utf-8")
    helper = tmp_path / "lib" / "helper.py"
    helper.parent.mkdir()
    helper.write_text("VALUE = 1\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          path: candidate\n"
        "      - name: Invoke workspace candidate root\n"
        "        working-directory: candidate\n"
        "        env:\n"
        "          PYTHONPATH: $GITHUB_WORKSPACE/candidate/lib\n"
        "        run: python entry.py\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    row = next(source for source in inventory.sources if source.path == "lib/helper.py")
    assert row.classification == "library"
    assert row.counted is False
    assert not any(source.path == "candidate/lib/helper.py" and source.counted for source in inventory.sources)
    assert not inventory.issues
