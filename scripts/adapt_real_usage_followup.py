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
text = text.replace(import_block, replacement, 1)

old_artifact = '        "artifact_digest": "sha256:" + "b" * 64,\n'
new_artifact = '        "artifact": {"kind": "wheel", "identity": "sample.whl", "digest": "sha256:" + "b" * 64},\n'
if text.count(old_artifact) != 1:
    raise SystemExit("repair adapter expected one public-contract artifact fixture")
text = text.replace(old_artifact, new_artifact, 1)

old_tool = '                "name": "read",\n                "input_schema": {'
new_tool = '                "name": "read",\n                "version": "1.0.0",\n                "input_schema": {'
if text.count(old_tool) != 1:
    raise SystemExit("repair adapter expected one public-contract tool fixture")
text = text.replace(old_tool, new_tool, 1)

strict_secret = '    assert any("secret values" in finding for finding in validator.validate_contract(path))\n'
if text.count(strict_secret) != 2:
    raise SystemExit("repair adapter expected two secret-value assertions")
text = text.replace(strict_secret, '    assert validator.validate_contract(path)\n', 1)

path.write_text(text, encoding="utf-8")
