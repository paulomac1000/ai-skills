#!/usr/bin/env python3
"""Tighten malformed approval diagnostics after the main final-review patch."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(relative: str, old: str, new: str) -> None:
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"{relative}: expected one exact post-patch match")
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")


replace_once(
    "contracts/validate_capability_manifest.py",
    '''            if isinstance(raw_binds, list) and all(isinstance(binding, str) for binding in raw_binds):\n                binds = set(raw_binds)\n                missing = sorted(_REQUIRED_APPROVAL_BINDINGS - binds)\n                if missing:\n                    findings.append(f"approval.binds is missing {missing}")\n''',
    '''            if isinstance(raw_binds, list) and all(isinstance(binding, str) for binding in raw_binds):\n                binds = set(raw_binds)\n                missing = sorted(_REQUIRED_APPROVAL_BINDINGS - binds)\n                if missing:\n                    findings.append(f"approval.binds is missing {missing}")\n            else:\n                findings.append("approval.binds must be a list of strings")\n''',
)
replace_once(
    "tests/test_atomic_claim_contract.py",
    '''    assert _semantic_findings(manifest) == []\n''',
    '''    assert _semantic_findings(manifest) == ["approval.binds must be a list of strings"]\n''',
)
