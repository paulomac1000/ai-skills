#!/usr/bin/env python3
"""Align the disposable real-usage repair script with the exact current schema layout."""
from pathlib import Path

path = Path("scripts/repair_real_usage_followup.py")
text = path.read_text(encoding="utf-8")
old = '("properties", "results", "items", "properties", "test_case")'
new = '("properties", "checks", "items", "properties", "test_case")'
if text.count(old) != 2:
    raise SystemExit("repair adapter expected two atomic schema paths")
text = text.replace(old, new)
import_block = '''replace_once(
    "contracts/rule_applicability.py",
    "from collections.abc import Mapping, Sequence\\n",
    "from collections.abc import Mapping\\n",
)
'''
replacement = '''replace_once(
    "contracts/rule_applicability.py",
    "from collections.abc import Mapping, Sequence\\n",
    "from collections.abc import Mapping, Sequence\\n",
)
'''
if text.count(import_block) != 1:
    raise SystemExit("repair adapter expected one rule-applicability import replacement")
path.write_text(text.replace(import_block, replacement, 1), encoding="utf-8")
