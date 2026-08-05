#!/usr/bin/env python3
"""Repair escaping in the generated regression before static validation."""

from pathlib import Path

path = Path("tests/test_final_audit_regressions.py")
text = path.read_text(encoding="utf-8")
old = '    text = "jobs: &jobs\n  loop: *jobs\n"\n'
new = '    text = "jobs: &jobs\\n  loop: *jobs\\n"\n'
if text.count(old) != 1:
    raise SystemExit("expected one generated recursive-YAML string to repair")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
