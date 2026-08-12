#!/usr/bin/env python3
"""Align the temporary practical-feedback patch with the exact branch head."""

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
text = "\n".join(lines) + "\n"

old = '''replace_once(
    "scripts/quality_targets.py",
    '    "scripts/select_lock.py",\\n    "skills/afds-doc-writer/validate.py",\\n',
    '    "scripts/select_lock.py",\\n    "scripts/check_release_version.py",\\n    "skills/afds-doc-writer/validate.py",\\n',
)
'''
new = '''replace_once(
    "scripts/quality_targets.py",
    '    "contracts/run_evidence_command.py",\\n    "scripts/ci.py",\\n    "scripts/install_locked.py",\\n    "scripts/quality_targets.py",\\n    "scripts/select_lock.py",\\n    "skills/afds-doc-writer/validate.py",\\n',
    '    "contracts/run_evidence_command.py",\\n    "scripts/ci.py",\\n    "scripts/install_locked.py",\\n    "scripts/quality_targets.py",\\n    "scripts/select_lock.py",\\n    "scripts/check_release_version.py",\\n    "skills/afds-doc-writer/validate.py",\\n',
)
'''
if text.count(old) != 1:
    raise RuntimeError(f"expected one ambiguous quality-target replacement, found {text.count(old)}")
text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
