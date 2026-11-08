from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills" / "agents-md-architect" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from agents_md_gate_sources import classify_gate_sources  # noqa: E402
from agents_md_python_roots import pythonpath_roots  # noqa: E402
from agents_md_source_types import CommandSource, ImportRoot  # noqa: E402
from discover_repository import discover  # noqa: E402


def test_bare_github_workspace_pythonpath_uses_workspace_root_from_nested_directory(tmp_path: Path) -> None:
    module = tmp_path / "tools" / "validator.py"
    module.parent.mkdir()
    module.write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - name: Invoke root module\n"
        "        working-directory: nested\n"
        "        env:\n"
        "          PYTHONPATH: $GITHUB_WORKSPACE\n"
        "        run: python -m tools.validator\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    row = next(source for source in inventory.sources if source.path == "tools/validator.py")
    assert row.classification == "task_entrypoint"
    assert row.counted is True
    assert not inventory.issues


def test_absolute_pythonpath_inside_checkout_resolves_repository_module(tmp_path: Path) -> None:
    module = tmp_path / ".agents" / "tools" / "validator.py"
    module.parent.mkdir(parents=True)
    module.write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - name: Invoke absolute repository root\n"
        "        working-directory: nested\n"
        "        env:\n"
        f"          PYTHONPATH: {tmp_path.resolve() / '.agents'}\n"
        "        run: python -m tools.validator\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    row = next(source for source in inventory.sources if source.path == ".agents/tools/validator.py")
    assert row.classification == "task_entrypoint"
    assert row.counted is True
    assert not inventory.issues


def test_known_external_absolute_pythonpath_is_supported(tmp_path: Path) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    external_root = tmp_path / "external-pythonpath"
    external_root.mkdir()
    (external_root / "pip.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repository_root / "nested").mkdir()
    workflow = repository_root / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - name: Use installed tooling\n"
        "        working-directory: nested\n"
        "        env:\n"
        f"          PYTHONPATH: {external_root.resolve()}\n"
        "        run: python -m pip\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(repository_root, discover(repository_root), limit=64)

    assert not any(source.path == "pip.py" and source.counted for source in inventory.sources)
    assert not inventory.issues


def test_unresolved_absolute_pythonpath_reports_incomplete_inventory(tmp_path: Path) -> None:
    missing_root = (tmp_path / "missing-pythonpath-root").resolve()
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - name: Invoke unresolved absolute root\n"
        "        env:\n"
        f"          PYTHONPATH: {missing_root}\n"
        "        run: python -m tools.validator\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert any("absolute PYTHONPATH" in issue and "unresolved" in issue for issue in inventory.issues)


def test_pythonpath_splits_multiple_windows_absolute_roots(tmp_path: Path) -> None:
    source = CommandSource("workflow.yml", ".", "", "workflow.yml:1")

    roots, issue, unresolved_roots = pythonpath_roots(
        [r"PYTHONPATH=C:\repo\.agents;D:\vendor", "python", "-m", "tools.validator"],
        (".",),
        source,
    )

    assert roots == (
        ImportRoot(r"C:\repo\.agents", True),
        ImportRoot(r"D:\vendor", True),
        ImportRoot("."),
    )
    assert issue is None
    assert not unresolved_roots


def test_module_under_external_root_checkout_is_not_counted_as_local(tmp_path: Path) -> None:
    (tmp_path / "entry.py").write_text("VALUE = 1\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          repository: example/validator\n"
        "          ref: 0123456789abcdef0123456789abcdef01234567\n"
        "      - run: python -m entry\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert not any(source.path == "entry.py" and source.counted for source in inventory.sources)
    assert any(
        source.path == "external:example/validator@0123456789abcdef0123456789abcdef01234567/entry.py"
        and source.classification == "excluded"
        for source in inventory.sources
    )
    assert not inventory.issues


def test_module_from_nested_local_checkout_is_still_counted(tmp_path: Path) -> None:
    module = tmp_path / "tools" / "validator.py"
    module.parent.mkdir()
    module.write_text("VALUE = 1\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          repository: example/authority\n"
        "          ref: 0123456789abcdef0123456789abcdef01234567\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          path: candidate\n"
        "      - name: Invoke candidate module\n"
        "        working-directory: candidate\n"
        "        run: python -m tools.validator\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    row = next(source for source in inventory.sources if source.path == "tools/validator.py")
    assert row.classification == "task_entrypoint"
    assert row.counted is True
    assert not inventory.issues


def test_module_from_external_nested_checkout_preserves_checkout_identity(tmp_path: Path) -> None:
    module = tmp_path / "vendor" / "tools.py"
    module.parent.mkdir()
    module.write_text("VALUE = 1\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          repository: example/authority\n"
        "          ref: 0123456789abcdef0123456789abcdef01234567\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          repository: example/vendor\n"
        "          ref: abcdef0123456789abcdef0123456789abcdef01\n"
        "          path: vendor\n"
        "      - run: PYTHONPATH=vendor python -m tools\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert not any(source.path == "vendor/tools.py" and source.counted for source in inventory.sources)
    assert any(
        source.path == "external:example/vendor@abcdef0123456789abcdef0123456789abcdef01/tools.py"
        and source.classification == "excluded"
        for source in inventory.sources
    )
    assert not inventory.issues
