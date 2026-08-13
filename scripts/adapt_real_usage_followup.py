#!/usr/bin/env python3
"""Align the disposable real-usage repair script with the exact current schema layout."""
from pathlib import Path

path = Path("scripts/repair_real_usage_followup.py")
text = path.read_text(encoding="utf-8")
old = '("properties", "results", "items", "properties", "test_case")'
new = '("properties", "checks", "items", "properties", "test_case")'
if text.count(old) != 1:
    raise SystemExit("repair adapter expected one atomic schema path")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
