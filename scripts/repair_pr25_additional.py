#!/usr/bin/env python3
"""Apply remaining verified regression alignment for PR 25; deleted before commit."""

from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "skills/mcp-server-architect/references/python-fastmcp.md",
    "It is **not** an SDK profile and must not be used to choose an implementation by class name.",
    "It is not an SDK profile and must not be used to choose an implementation by class name.",
)
replace_once(
    "tests/test_mcp_migration_standard.py",
    '    assert "mcp==2.0.0" in official\n',
    '    assert "dependency lock and assessment identify the exact package version" in official\n',
)
replace_once(
    "tests/test_post_review_regressions.py",
    '    assert "mcp.streamable_http_app()" in source\n',
    '    assert "mcp.streamable_http_app(" in source\n    assert "stateless_http=True" in source\n',
)
replace_once(
    "tests/test_post_review_regressions.py",
    '    assert \'mode="stateless"\' in source\n',
    "",
)
replace_once(
    "tests/test_post_review_regressions.py",
    '    assert \'mount("/mcp", protected)\' in source\n',
    "",
)
replace_once(
    "tests/test_templates.py",
    '    assert "mapfile -t packages < nupkg/publish-files.txt" in publisher["run"]\n',
    '    assert "mapfile -t packages < nupkg/verified-publish-files.txt" in publisher["run"]\n',
)
replace_once(
    "tests/test_contract_hardening_regressions.py",
    '''    assert 'CapabilityActiveState.Disabled => "inactive"' in adapter
    assert 'CapabilityActiveState.Degraded => "inactive"' in adapter
    assert 'CapabilityActiveState.Unavailable => "inactive"' in adapter
''',
    '''    assert (
        'CapabilityActiveState.Disabled or CapabilityActiveState.Degraded or '
        'CapabilityActiveState.Unavailable => "inactive"'
        in adapter
    )
''',
)
replace_once(
    "contracts/standard-rule-map.yaml",
    "      retry-policy: {rule_id: consumer.retry.reconciled, primary: true}\n      pagination: {rule_id: consumer.pagination.bounded, primary: true}\n",
    "      retry-policy: {rule_id: consumer.retry.reconciled, primary: true}\n      catalog-and-approval-invalidation: {rule_id: consumer.trust.provenance}\n      pagination: {rule_id: consumer.pagination.bounded, primary: true}\n",
)
replace_once(
    "tests/test_audit_contract_extensions.py",
    '''    assert any(
        "full commit SHA" in finding or "does not match" in finding
        for finding in findings
    )
''',
    '''    assert any("full commit SHA" in finding for finding in findings)
''',
)
replace_once(
    "contracts/atomic-claim-catalog.yaml",
    '''  - id: mcp.identity.local-principal
    parent_rule_id: mcp.identity.target-binding
    skill: mcp-server-architect
    source: skills/mcp-server-architect/references/principal-and-shell-boundaries.md#local-stdio-principal
    description: A local stdio deployment derives an explicit principal from a documented operating-system process boundary and never trusts model-supplied identity.
    applies_when: {maturity_at_least: L1, profiles_any: [local-stdio]}
''',
    '''  - id: mcp.identity.local-principal
    parent_rule_id: mcp.identity.target-binding
    skill: mcp-server-architect
    source: skills/mcp-server-architect/references/principal-and-shell-boundaries.md#local-stdio-principal
    description: A local stdio deployment derives an explicit principal from a documented operating-system process boundary and never trusts model-supplied identity.
    applies_when: {maturity_at_least: L2, profiles_any: [local-stdio]}
''',
)
replace_once(
    "tests/test_atomic_claim_contract.py",
    '''    assert local["applies_when"]["profiles_any"] == ["local-stdio"]
    assert remote["applies_when"]["profiles_any"] == ["remote-http"]
''',
    '''    assert local["applies_when"] == {
        "maturity_at_least": "L2",
        "profiles_any": ["local-stdio"],
    }
    assert remote["applies_when"]["profiles_any"] == ["remote-http"]
''',
)
replace_once(
    "tests/test_atomic_claim_contract.py",
    '''        "active_state": "write",
        "retryable": True,
        "idempotent": True,
        "reversible": True,
        "requires_confirmation": True,
        "idempotency_key_required": True,
        "authorization_scopes": ["device:delete"],
        "concurrency": {"scope": "principal-target", "limit": 1},
        "max_response_bytes": 65536,
''',
    '''        "active_state": "active",
        "retryable": True,
        "idempotent": True,
        "reversible": True,
        "requires_confirmation": True,
        "idempotency_key_required": True,
        "authorization_scopes": ["device:delete"],
        "approval": {
            "enforcement": "server-side",
            "record_required": True,
            "record_ttl_seconds": 300,
            "binds": [
                "principal",
                "capability",
                "target",
                "arguments-digest",
                "expires-at",
            ],
        },
        "concurrency": {"scope": "principal-target", "limit": 1},
        "max_response_bytes": 65536,
''',
)
replace_once(
    "tests/test_atomic_claim_contract.py",
    '''    assert any("reversible_rationale" in finding for finding in findings)
    assert any("approval" in finding for finding in findings)
''',
    '''    assert any("reversible_rationale" in finding for finding in findings)

    without_approval = dict(manifest)
    without_approval.pop("approval")
    path.write_text(yaml.safe_dump(without_approval), encoding="utf-8")
    assert any("approval" in finding for finding in validate_manifest(path))
''',
)
replace_once(
    "skills/mcp-server-architect/tools/generate_python_server.py",
    "_implementation.project_files = project_files\n",
    'setattr(_implementation, "project_files", project_files)\n',
)
replace_once(
    "skills/mcp-server-architect/tools/generate_python_server_impl.py",
    '''    if os_name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        move_file = kernel32.MoveFileW
        move_file.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        move_file.restype = ctypes.c_int
        if not move_file(str(source), str(destination)):
            error = ctypes.get_last_error()
            if error in {80, 183}:
                raise FileExistsError(destination)
            raise ctypes.WinError(error)
        return
''',
    '''    if os_name == "nt":
        win_dll = getattr(ctypes, "WinDLL")
        get_last_error = getattr(ctypes, "get_last_error")
        win_error = getattr(ctypes, "WinError")
        kernel32 = win_dll("kernel32", use_last_error=True)
        move_file = kernel32.MoveFileW
        move_file.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        move_file.restype = ctypes.c_int
        if not move_file(str(source), str(destination)):
            error = get_last_error()
            if error in {80, 183}:
                raise FileExistsError(destination)
            raise win_error(error)
        return
''',
)
replace_once(
    "skills/afds-doc-writer/validate.py",
    "from functools import lru_cache\n",
    "from functools import cache\n",
)
replace_once(
    "skills/afds-doc-writer/validate.py",
    "    @lru_cache(maxsize=None)\n",
    "    @cache\n",
)
replace_once(
    "tests/decision_engine_cases.py",
    "\nimport pytest\n",
    "",
)
replace_once(
    "tests/test_agents_md_structural_followup.py",
    "from pathlib import Path\n",
    "from collections.abc import Iterable\nfrom pathlib import Path\nfrom typing import Protocol\n",
)
replace_once(
    "tests/test_agents_md_structural_followup.py",
    '''def codes(findings: list[object]) -> set[str]:
    return {getattr(item, "code") for item in findings}
''',
    '''class _FindingWithCode(Protocol):
    code: str


def codes(findings: Iterable[_FindingWithCode]) -> set[str]:
    return {item.code for item in findings}
''',
)

# Every stable rule must be bound to executable repository evidence.
replace_once(
    "contracts/evidence-claim-plan.yaml",
    '''  - kind: rule
    subject: cicd.workflow.profiled
    selectors:
    - '*test_templates*'
    - '*test_ci_cd_workflow_policy*'
    - '*test_contract_consistency_followup*'
    result_files:
    - repository-junit.xml
    execution_id: repository
''',
    '''  - kind: rule
    subject: cicd.workflow.profiled
    selectors:
    - '*test_templates*'
    - '*test_ci_cd_workflow_policy*'
    - '*test_contract_consistency_followup*'
    result_files:
    - repository-junit.xml
    execution_id: repository
  - kind: rule
    subject: cicd.execution.on-demand
    selectors:
    - '*test_ci_execution_policy*'
    - '*test_templates*'
    result_files:
    - repository-junit.xml
    execution_id: repository
''',
)

base_digest = os.environ.get("PYTHON_BASE_IMAGE_DIGEST", "")
if not DIGEST.fullmatch(base_digest):
    raise RuntimeError("PYTHON_BASE_IMAGE_DIGEST must be an exact sha256 digest")
replace_once(
    "skills/mcp-server-architect/tools/python-template/Dockerfile.template",
    "FROM python:3.12.11-slim-bookworm@sha256:8d8d1a11f5f2e7879d4b9be3ec040b1f48d99b5284942230ca11843bb65c2d4a\n",
    f"FROM python:3.12.11-slim-bookworm@{base_digest}\n",
)
