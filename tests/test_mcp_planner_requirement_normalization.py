"""MCP adoption planning normalizes pip requirement syntax before classifying SDK pins."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
PLANNER = ROOT / "skills/mcp-server-architect/tools/plan_existing_project.py"


def _planner() -> ModuleType:
    tools = str(PLANNER.parent)
    if tools not in sys.path:
        sys.path.insert(0, tools)
    spec = importlib.util.spec_from_file_location("planner_requirement_normalization", PLANNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _claim(tmp_path: Path, requirement: str) -> dict[str, object]:
    (tmp_path / "requirements.txt").write_text(requirement + "\n", encoding="utf-8")
    planner = _planner()
    return planner._sdk_claim(
        tmp_path,
        {"facts": {"sdk_profile": "python-official-mcp"}},
    )


def test_bare_trailing_pip_option_does_not_hide_exact_sdk_pin(tmp_path: Path) -> None:
    assert _claim(tmp_path, "mcp==2.0.0 --no-binary") == {
        "package": "mcp",
        "requirement": "==2.0.0",
        "status": "exact-pin",
    }


def test_inline_comment_and_option_argument_do_not_hide_exact_sdk_pin(tmp_path: Path) -> None:
    assert _claim(tmp_path, "mcp==2.0.0 --no-binary mcp  # locked") == {
        "package": "mcp",
        "requirement": "==2.0.0",
        "status": "exact-pin",
    }
