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

old = '''replace_once(
    "CHANGELOG.md",
    "### Added\\n\\n",
    "### Added\\n\\n- Added consumer-driven adoption discovery, immutable external consumer canaries, observed upstream-contract validation, and live-backend mutation-safety contracts derived from real MCP migrations.\\n- Added transport-by-capability authorization parity, profile-specific FastMCP consumer evidence, and a stable-version drift gate so changed stable skill contents cannot continue to identify as the previous release.\\n",
)
'''
new = '''replace_once(
    "CHANGELOG.md",
    "## 1.3.0 - 2026-08-12\\n\\n### Added\\n\\n",
    "## 1.3.0 - 2026-08-12\\n\\n### Added\\n\\n- Added consumer-driven adoption discovery, immutable external consumer canaries, observed upstream-contract validation, and live-backend mutation-safety contracts derived from real MCP migrations.\\n- Added transport-by-capability authorization parity, profile-specific FastMCP consumer evidence, and a stable-version drift gate so changed stable skill contents cannot continue to identify as the previous release.\\n",
)
'''
if text.count(old) != 1:
    raise RuntimeError(f"expected one generic changelog replacement, found {text.count(old)}")
text = text.replace(old, new, 1)

text += r'''

replace_once(
    "tests/test_mcp_migration_standard.py",
    '''def test_migration_and_testing_references_are_linked_from_skill() -> None:
    skill = text("SKILL.md")
    for required in (
        "references/migration-assessment.md",
        "references/testing-strategy.md",
        "references/security-and-operations.md",
        "references/python-official-mcp-sdk.md",
        "references/python-fastmcp-package.md",
    ):
        assert required in skill
''',
    '''def test_migration_entrypoint_is_small_and_specialist_references_remain_routable() -> None:
    skill = text("SKILL.md")
    manifest = text("manifest.yaml")
    for required in (
        "references/testing-strategy.md",
        "references/upstream-contract-discovery.md",
    ):
        assert required in skill
    for routed in (
        "references/migration-assessment.md",
        "references/security-and-operations.md",
        "references/python-official-mcp-sdk.md",
        "references/python-fastmcp-package.md",
    ):
        assert routed in manifest
    assert "load other references only when" in skill
''',
)
'''
path.write_text(text, encoding="utf-8")
