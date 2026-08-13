#!/usr/bin/env python3
"""Align the disposable real-usage repair script with the exact current schema layout."""
from pathlib import Path

path = Path("scripts/repair_real_usage_followup.py")
text = path.read_text(encoding="utf-8")
old = '("properties", "results", "items", "properties", "test_case")'
new = '("properties", "checks", "items", "properties", "test_case")'
if text.count(old) != 2:
    raise SystemExit("repair adapter expected two atomic schema paths")
path.write_text(text.replace(old, new), encoding="utf-8")
