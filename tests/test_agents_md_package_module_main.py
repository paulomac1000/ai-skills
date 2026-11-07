from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills/agents-md-architect/tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from agents_md_gate_sources import classify_gate_sources  # noqa: E402
from discover_repository import discover  # noqa: E402


def test_python_package_main_invocation_counts_main_module(tmp_path: Path) -> None:
    package = tmp_path / ".agents/validator"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("from .version import VERSION\n", encoding="utf-8")
    (package / "version.py").write_text("VERSION = '1'\n", encoding="utf-8")
    (package / "__main__.py").write_text("print('validator')\n", encoding="utf-8")
    workflow = tmp_path / ".github/workflows/ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  validate:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - run: PYTHONPATH=.agents python -m validator\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    main_module = next(source for source in inventory.sources if source.path == ".agents/validator/__main__.py")
    initializer = next(source for source in inventory.sources if source.path == ".agents/validator/__init__.py")
    version_module = next(source for source in inventory.sources if source.path == ".agents/validator/version.py")
    assert main_module.classification == "task_entrypoint"
    assert main_module.counted is True
    assert any("ci.yml" in origin for origin in main_module.origins)
    assert initializer.classification == "library"
    assert initializer.counted is False
    assert version_module.classification == "library"
    assert version_module.counted is False
    assert not inventory.issues
    assert inventory.count == 2


def test_python_package_without_main_is_not_counted_as_invoked(tmp_path: Path) -> None:
    package = tmp_path / ".agents/validator"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    workflow = tmp_path / ".github/workflows/ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  validate:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - run: PYTHONPATH=.agents python -m validator\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert inventory.count == 1
    assert any("no executable package entrypoint" in issue for issue in inventory.issues)
    assert not any(source.counted for source in inventory.sources if source.path.endswith("/__init__.py"))
