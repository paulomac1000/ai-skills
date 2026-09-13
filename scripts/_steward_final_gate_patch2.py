from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "scripts/_steward_final_gate_patch.py"
text = PATCH.read_text(encoding="utf-8")
old = '''def replace_once(path: str, old: str, new: str, label: str) -> None:\n    target = ROOT / path\n    text = target.read_text(encoding="utf-8")\n    count = text.count(old)\n    if count != 1:\n        raise RuntimeError(f"{label}: expected one match, found {count}")\n    target.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\\n")\n'''
new = '''def replace_once(path: str, old: str, new: str, label: str) -> None:\n    target = ROOT / path\n    text = target.read_text(encoding="utf-8")\n    count = text.count(old)\n    repeated_first = {\n        "template submit capability contract",\n        "template submit finalization reserve",\n        "generator submit contract",\n        "generator submit reserve",\n    }\n    expected = 2 if label in repeated_first else 1\n    if count != expected:\n        raise RuntimeError(f"{label}: expected {expected} match(es), found {count}")\n    target.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\\n")\n'''
if text.count(old) != 1:
    raise RuntimeError("patch helper drift: expected exactly one helper definition")
PATCH.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
runpy.run_path(str(PATCH), run_name="__main__")
for relative in (
    "skills/mcp-steward-architect/tools/steward-templates/python/test_steward_runtime.py.template",
    "tests/test_mcp_steward_runtime_security.py",
    "tests/test_mcp_steward_evidence_selectors.py",
):
    target = ROOT / relative
    target.write_text(target.read_text(encoding="utf-8").rstrip() + "\n", encoding="utf-8", newline="\n")
