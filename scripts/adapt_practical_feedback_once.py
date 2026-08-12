#!/usr/bin/env python3
"""Repair the one embedded fixture quote in the temporary practical-feedback patch."""

from pathlib import Path

path = Path(__file__).with_name("repair_pr25_practical_feedback.py")
text = path.read_text(encoding="utf-8")
lines = text.splitlines()
changed = 0
for index, line in enumerate(lines):
    if line.lstrip().startswith("'''[project]\\nname = \"sample\"\\nversion = \"3.2.1\""):
        lines[index] = line.replace("'''[project]", '\"\"\"[project]', 1).replace("\\n''',", '\\n\"\"\",', 1)
        changed += 1
if changed != 1:
    raise RuntimeError(f"expected exactly one embedded fixture quote, changed {changed}")
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
