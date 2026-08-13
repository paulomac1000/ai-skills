#!/usr/bin/env python3
"""Give the dynamic compatibility result a static structural return type."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "skills/mcp-server-consumer/tools/decision_engine.py"
text = PATH.read_text(encoding="utf-8")

replacements = [
    (
        "from typing import Any\n",
        "from typing import Any, Protocol\n",
    ),
    (
        "DEFAULT_ERROR_STRATEGY = _LEGACY.DEFAULT_ERROR_STRATEGY\n\nchoose_initial_detail_params",
        '''DEFAULT_ERROR_STRATEGY = _LEGACY.DEFAULT_ERROR_STRATEGY\n\n\nclass _CapabilityProfileResult(Protocol):\n    risk: object\n    requires_confirmation: bool\n    sensitive: bool\n    idempotent: bool | None\n    source: str\n\n\nchoose_initial_detail_params''',
    ),
    (
        ") -> CapabilityProfile:\n    \"\"\"Infer a fail-closed profile using exact, identity-bound trusted values.\n",
        ") -> _CapabilityProfileResult:\n    \"\"\"Infer a fail-closed profile using exact, identity-bound trusted values.\n",
    ),
]
for old, new in replacements:
    if text.count(old) != 1:
        raise RuntimeError(f"decision_engine.py: expected one match for {old[:80]!r}")
    text = text.replace(old, new)
PATH.write_text(text, encoding="utf-8", newline="\n")
