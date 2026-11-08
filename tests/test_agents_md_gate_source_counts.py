from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills" / "agents-md-architect" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from agents_md_gate_sources import classify_gate_sources  # noqa: E402
from discover_repository import discover  # noqa: E402


def test_unresolved_module_candidate_keeps_bin_entrypoint_count(tmp_path: Path) -> None:
    module = tmp_path / "bin" / "validator.py"
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
        "      - run: PYTHONPATH=$UNKNOWN_ROOT/bin python -m validator\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    row = next(source for source in inventory.sources if source.path == "bin/validator.py")
    assert row.classification == "task_entrypoint"
    assert row.counted is True
    assert inventory.count == 2
    assert any("PYTHONPATH" in issue and "unresolved" in issue for issue in inventory.issues)


@pytest.mark.skipif(os.name == "nt", reason="executable mode is not portable on Windows")
def test_unresolved_module_candidate_keeps_shebang_entrypoint_count(tmp_path: Path) -> None:
    module = tmp_path / "scripts" / "validator.py"
    module.parent.mkdir()
    module.write_text("#!/usr/bin/env python3\nVALUE = 1\n", encoding="utf-8")
    module.chmod(0o755)
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - run: PYTHONPATH=$UNKNOWN_ROOT/scripts python -m validator\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    row = next(source for source in inventory.sources if source.path == "scripts/validator.py")
    assert row.classification == "task_entrypoint"
    assert row.counted is True
    assert inventory.count == 2
    assert any("PYTHONPATH" in issue and "unresolved" in issue for issue in inventory.issues)
