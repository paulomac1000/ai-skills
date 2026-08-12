#!/usr/bin/env python3
"""Adapt the temporary PR 25 repair script to the current exact-head layout."""

from pathlib import Path

path = Path(__file__).with_name("repair_pr25_once.py")
text = path.read_text(encoding="utf-8")

old_profile = '''        'def _profile_for(path: Path, root: Path, governance: Governance) -> GovernanceProfile | None:\\n    relative = _repository_relative(path, root)\\n',
        'def _profile_for(path: Path, root: Path, governance: Governance) -> GovernanceProfile | None:\\n    """Return the last matching governance profile; later entries intentionally win."""\\n    relative = _repository_relative(path, root)\\n',
'''
new_profile = '''        ''' + "'''" + '''def _profile_for(
    path: Path,
    repository_root: Path,
    governance: Governance | None,
) -> Mapping[str, bool]:
    if governance is None:
        return DEFAULT_PROFILES["governed"]
''' + "'''" + ''',
        ''' + "'''" + '''def _profile_for(
    path: Path,
    repository_root: Path,
    governance: Governance | None,
) -> Mapping[str, bool]:
    """Return the last matching governance profile; later entries intentionally win."""
    if governance is None:
        return DEFAULT_PROFILES["governed"]
''' + "'''" + ''',
'''

old_governance = '''        '    governance_path = args.governance or root / "skills/afds-doc-writer/governance.yaml"\\n    governance = DEFAULT_GOVERNANCE\\n    if governance_path.exists():\\n',
        '    governance_path = args.governance or root / "skills/afds-doc-writer/governance.yaml"\\n    governance = DEFAULT_GOVERNANCE\\n    if args.governance is not None and not governance_path.is_file():\\n        print(f"ERROR: governance file does not exist: {governance_path}")\\n        return 1\\n    if governance_path.exists():\\n',
'''
new_governance = '''        ''' + "'''" + '''    governance_path = args.governance or root / "skills/afds-doc-writer/governance.yaml"
    governance: Governance | None = None
    findings: list[Finding] = []
    if governance_path.exists():
''' + "'''" + ''',
        ''' + "'''" + '''    governance_path = args.governance or root / "skills/afds-doc-writer/governance.yaml"
    governance: Governance | None = None
    findings: list[Finding] = []
    if args.governance is not None and not governance_path.is_file():
        findings.append(Finding(governance_path, "governance file does not exist"))
    elif governance_path.exists():
''' + "'''" + ''',
'''

for old, new, label in (
    (old_profile, new_profile, "profile"),
    (old_governance, new_governance, "governance"),
):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"temporary repair {label} adapter expected one match, found {count}")
    text = text.replace(old, new, 1)

old_decision_end = '    end = decision.index("}\\n\\n\\nfor _name", start) + 2\n'
new_decision_end = '    end = decision.index("}\\n\\n\\ndef _load_cases", start) + 2\n'
if text.count(old_decision_end) != 1:
    raise RuntimeError("temporary repair decision adapter expected one match")
text = text.replace(old_decision_end, new_decision_end, 1)

artifact_start = text.index("    # Exact artifact identity must use the revision actually checked out.\n")
artifact_end = text.index("    # Independent lock failures get independent regressions.\n", artifact_start)
artifact_section = '''    # Exact artifact identity must use the revision actually checked out.
    replace_once(
        "skills/mcp-server-architect/tools/python-template/.github/workflows/ci.yml.template",
        ''' + "'''" + '''      - name: Build and smoke the exact-wheel container
        shell: bash
        run: |
          set -euo pipefail
          WHEEL="$(find dist -maxdepth 1 -name '*.whl' -print -quit)"
''' + "'''" + ''',
        ''' + "'''" + '''      - name: Build and smoke the exact-wheel container
        shell: bash
        env:
          EXPECTED_SHA: ${{ github.event.pull_request.head.sha || github.sha }}
        run: |
          set -euo pipefail
          test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"
          WHEEL="$(find dist -maxdepth 1 -name '*.whl' -print -quit)"
''' + "'''" + ''',
    )
    replace_once(
        "skills/mcp-server-architect/tools/python-template/.github/workflows/ci.yml.template",
        '          IMAGE="__DISTRIBUTION__:sha-${GITHUB_SHA}"\\n',
        '          IMAGE="__DISTRIBUTION__:sha-${EXPECTED_SHA}"\\n',
    )

'''
text = text[:artifact_start] + artifact_section + text[artifact_end:]

text = text.replace('"--root",', '"--repository-root",')
path.write_text(text, encoding="utf-8")
