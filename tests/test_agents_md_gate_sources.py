from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills" / "agents-md-architect" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from agents_md_gate_sources import classify_gate_sources  # noqa: E402
from discover_repository import discover  # noqa: E402


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
        "jobs:\n  verify:\n    steps:\n      - run: bash scripts/referenced.sh\n",
        encoding="utf-8",
    )
    discovery = discover(tmp_path)
    inventory = classify_gate_sources(tmp_path, discovery, limit=64)
    counted = {item.path for item in inventory.sources if item.counted}
    assert ".github/workflows/ci.yml" in counted
    assert "scripts/main.py" in counted
    assert "scripts/referenced.sh" in counted
    assert inventory.count == 3


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


def test_executable_script_counts_without_extension_or_main_guard(tmp_path: Path) -> None:
    path = tmp_path / "bin" / "verify"
    path.parent.mkdir()
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    row = next(item for item in inventory.sources if item.path == "bin/verify")
    assert row.counted is True
