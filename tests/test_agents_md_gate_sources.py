from __future__ import annotations

import os
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


def test_referenced_entrypoint_counts_after_move_outside_scripts_and_bin(tmp_path: Path) -> None:
    entrypoint = tmp_path / "tools" / "release" / "check.sh"
    entrypoint.parent.mkdir(parents=True)
    entrypoint.write_text("echo ok\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  verify:\n    steps:\n      - run: bash tools/release/check.sh\n",
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
