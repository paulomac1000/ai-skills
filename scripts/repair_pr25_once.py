#!/usr/bin/env python3
"""One-shot exact-head repair for PR 25; deleted by the resulting commit."""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(
            f"{path}: expected one replacement, found {count}: {old[:120]!r}"
        )
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_all(path: str, old: str, new: str, *, minimum: int = 1) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count < minimum:
        raise RuntimeError(
            f"{path}: expected at least {minimum} replacements, found {count}: {old!r}"
        )
    target.write_text(text.replace(old, new), encoding="utf-8")


def remove_functions(path: str, names: set[str]) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    module = ast.parse(text)
    ranges = [
        (node.lineno - 1, node.end_lineno)
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in names
    ]
    if len(ranges) != len(names):
        found = {
            node.name
            for node in module.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in names
        }
        raise RuntimeError(f"{path}: missing functions {sorted(names - found)}")
    lines = text.splitlines(keepends=True)
    for start, end in sorted(ranges, reverse=True):
        del lines[start:end]
    target.write_text("".join(lines), encoding="utf-8")


def migrate_afds_frontmatter(path: str, kind: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise RuntimeError(f"{path}: expected YAML frontmatter")
    end = text.index("\n---\n", 4)
    lines = text[4:end].splitlines()
    if not any(line.startswith("afds_schema_version:") for line in lines):
        lines.insert(0, "afds_schema_version: 2")
    index = next(i for i, line in enumerate(lines) if line.startswith("verification:"))
    if lines[index] != "verification:":
        value = lines[index].split(":", 1)[1].strip()
        lines[index : index + 1] = [
            "verification:",
            f"  kind: {kind}",
            f"  value: {value}",
        ]
    target.write_text(
        "---\n" + "\n".join(lines) + text[end:],
        encoding="utf-8",
    )


def main() -> None:
    # Fail closed on malformed schema shapes before semantic processing.
    replace_once(
        "contracts/validate_atomic_claims.py",
        '    findings = _schema_findings(report, schema)\n    skill = report.get("skill")\n',
        '    findings = _schema_findings(report, schema)\n    if findings:\n        return findings\n    skill = report.get("skill")\n',
    )
    replace_once(
        "contracts/validate_capability_manifest.py",
        "    findings.extend(_semantic_findings(manifest, require_active=require_active))\n    return findings\n",
        "    if findings:\n        return findings\n    findings.extend(_semantic_findings(manifest, require_active=require_active))\n    return findings\n",
    )

    # Keep facade and implementation write-permission semantics identical.
    replace_once(
        "skills/ci-cd-architect/tools/check_github_actions_policy.py",
        'def _permissions_write(value: object) -> bool:\n    return isinstance(value, Mapping) and any(\n        isinstance(scope, str) and scope.casefold() == "write"\n        for scope in value.values()\n    )\n',
        "def _permissions_write(value: object) -> bool:\n    return _impl._permission_has_write(\n        dict(value) if isinstance(value, Mapping) else value\n    )\n",
    )

    # Conformance cannot accept two missing versions as equal.
    replace_once(
        "contracts/validate_conformance.py",
        '    if skill.get("version") != manifest.get("version"):\n        errors.append("skill.version: must equal the local skill manifest")\n',
        '    reported_version = skill.get("version")\n    manifest_version = manifest.get("version")\n    if not isinstance(reported_version, str) or not reported_version:\n        errors.append("skill.version: must be a non-empty string")\n    elif not isinstance(manifest_version, str) or reported_version != manifest_version:\n        errors.append("skill.version: must equal the local skill manifest")\n',
    )

    # Only the public module owns identity-bound trust types.
    replace_all(
        "skills/mcp-server-consumer/tools/decision_engine_legacy.py",
        "TrustedCapabilityPolicy",
        "_LegacyTrustedCapabilityPolicy",
        minimum=3,
    )
    replace_all(
        "skills/mcp-server-consumer/tools/decision_engine_legacy.py",
        "TrustedCapabilityContract",
        "_LegacyTrustedCapabilityContract",
        minimum=3,
    )
    legacy_path = ROOT / "skills/mcp-server-consumer/tools/decision_engine_legacy.py"
    legacy = legacy_path.read_text(encoding="utf-8")
    legacy = legacy.replace(
        "trusted_policy must be _LegacyTrustedCapabilityPolicy or None",
        "trusted_policy must be TrustedCapabilityPolicy or None",
    ).replace(
        "trusted_contract must be _LegacyTrustedCapabilityContract or None",
        "trusted_contract must be TrustedCapabilityContract or None",
    )
    legacy_path.write_text(legacy, encoding="utf-8")

    obsolete = {
        "test_tools_package_public_entry_point_imports",
        "test_untrusted_signals_can_only_increase_risk_and_preserve_confidentiality",
        "test_typed_trust_channels_reject_boolean_upgrade_switches",
        "test_annotations_require_consumer_controlled_server_trust",
        "test_positive_idempotency_comes_only_from_typed_external_values",
    }
    remove_functions("tests/decision_engine_cases.py", obsolete)
    decision_path = ROOT / "tests/test_decision_engine.py"
    decision = decision_path.read_text(encoding="utf-8")
    start = decision.index("LEGACY_TRUST_CASES = {")
    end = decision.index("}\n\n\nfor _name", start) + 2
    decision = decision[:start] + decision[end:]
    decision = decision.replace(
        'if _name.startswith("test_") and _name not in LEGACY_TRUST_CASES:',
        'if _name.startswith("test_"): ',
    )
    decision_path.write_text(decision, encoding="utf-8")

    # AFDS metadata dialect and local-link parsing.
    replace_once(
        "skills/afds-doc-writer/validate.py",
        'def _is_afds_metadata(metadata: Mapping[str, Any]) -> bool:\n    """Distinguish AFDS metadata from foreign portable frontmatter such as SKILL.md."""\n    if "afds_schema_version" in metadata or "doc_id" in metadata:\n        return True\n    strong_keys = {"type", "status", "rigor", "owners", "verification"}\n    return len(strong_keys.intersection(metadata)) >= 2\n',
        'def _is_afds_metadata(metadata: Mapping[str, Any]) -> bool:\n    """Distinguish AFDS metadata from foreign portable frontmatter such as SKILL.md."""\n    dialect_keys = {"afds_schema_version", "doc_id", "rigor", "owners", "verification"}\n    return bool(dialect_keys.intersection(metadata))\n',
    )
    replace_once(
        "skills/afds-doc-writer/validate.py",
        'def _profile_for(path: Path, root: Path, governance: Governance) -> GovernanceProfile | None:\n    relative = _repository_relative(path, root)\n',
        'def _profile_for(path: Path, root: Path, governance: Governance) -> GovernanceProfile | None:\n    """Return the last matching governance profile; later entries intentionally win."""\n    relative = _repository_relative(path, root)\n',
    )
    replace_once(
        "skills/afds-doc-writer/validate.py",
        '''    for destination in iter_link_destinations(body):
        decoded = unquote(destination)
        if re.match(r"^[a-z][a-z0-9+.-]*:", decoded, re.I) or decoded.startswith("//"):
            continue
        raw_path, separator, fragment = decoded.partition("#")
        display = decoded
        resolved_target: Path
        if not raw_path:
            resolved_target = path
        else:
            linked_target, unsafe = _safe_link_target(path, raw_path, repository_root)
            if unsafe:
                findings.append(Finding(path, f"unsafe relative link: {raw_path}: {unsafe}"))
                continue
            if linked_target is None:
                findings.append(Finding(path, f"broken relative link: {raw_path}"))
                continue
            resolved_target = linked_target
        if separator and fragment and check_anchors:
            try:
                anchors = anchor_cache.setdefault(
                    resolved_target,
                    _anchors(resolved_target.read_text(encoding="utf-8")),
                )
            except (OSError, UnicodeDecodeError):
                findings.append(Finding(path, f"cannot inspect relative anchor: {display}"))
                continue
            normalized_fragment = _github_anchor(fragment)
            if normalized_fragment not in anchors:
                findings.append(Finding(path, f"broken relative anchor: {display}"))
''',
        '''    for destination in iter_link_destinations(body):
        raw_path, separator, raw_fragment = destination.partition("#")
        decoded_path = unquote(raw_path)
        fragment = unquote(raw_fragment) if separator else ""
        if re.match(r"^[a-z][a-z0-9+.-]*:", decoded_path, re.I) or decoded_path.startswith("//"):
            continue
        display = unquote(destination)
        resolved_target: Path
        if not decoded_path:
            resolved_target = path
        else:
            linked_target, unsafe = _safe_link_target(path, decoded_path, repository_root)
            if unsafe:
                findings.append(Finding(path, f"unsafe relative link: {decoded_path}: {unsafe}"))
                continue
            if linked_target is None:
                findings.append(Finding(path, f"broken relative link: {decoded_path}"))
                continue
            resolved_target = linked_target
        if separator and fragment and check_anchors:
            try:
                anchors = anchor_cache.setdefault(
                    resolved_target,
                    _anchors(resolved_target.read_text(encoding="utf-8")),
                )
            except (OSError, UnicodeDecodeError):
                findings.append(Finding(path, f"cannot inspect relative anchor: {display}"))
                continue
            normalized_fragment = _github_anchor(fragment)
            if normalized_fragment not in anchors:
                findings.append(Finding(path, f"broken relative anchor: {display}"))
''',
    )
    replace_once(
        "skills/afds-doc-writer/validate.py",
        '    governance_path = args.governance or root / "skills/afds-doc-writer/governance.yaml"\n    governance = DEFAULT_GOVERNANCE\n    if governance_path.exists():\n',
        '    governance_path = args.governance or root / "skills/afds-doc-writer/governance.yaml"\n    governance = DEFAULT_GOVERNANCE\n    if args.governance is not None and not governance_path.is_file():\n        print(f"ERROR: governance file does not exist: {governance_path}")\n        return 1\n    if governance_path.exists():\n',
    )

    # MCP applicability is derived from catalog metadata and adoption context.
    replace_once(
        "contracts/validate_adoption.py",
        "from contracts.evidence import EvidenceVerifier, GitHubEvidenceVerifier  # noqa: E402\nfrom contracts.semver import is_semver  # noqa: E402\n",
        "from contracts.evidence import EvidenceVerifier, GitHubEvidenceVerifier  # noqa: E402\nfrom contracts.rule_applicability import RuleContext, expected_rules  # noqa: E402\nfrom contracts.semver import is_semver  # noqa: E402\n",
    )
    replace_once(
        "contracts/validate_adoption.py",
        '''def _validate_applicability(
    assessment: Mapping[str, Any],
    catalog_rules: set[str],
    findings: list[Finding],
    *,
    as_of: date,
''',
        '''def _validate_applicability(
    assessment: Mapping[str, Any],
    catalog_rules: set[str],
    findings: list[Finding],
    *,
    machine_applicable_rules: set[str] | None = None,
    as_of: date,
''',
    )
    replace_once(
        "contracts/validate_adoption.py",
        '''        status_value = entry.get("status")
        if status_value not in ALLOWED_STATUSES:
            findings.append(Finding(f"{location}.status", f"must be one of {sorted(ALLOWED_STATUSES)}"))
''',
        '''        status_value = entry.get("status")
        if status_value not in ALLOWED_STATUSES:
            findings.append(Finding(f"{location}.status", f"must be one of {sorted(ALLOWED_STATUSES)}"))
        if machine_applicable_rules is not None and rule_id in catalog_rules:
            machine_applies = rule_id in machine_applicable_rules
            if machine_applies and status_value == "not-applicable":
                findings.append(
                    Finding(
                        f"{location}.status",
                        "catalog applicability requires this rule to be applicable or explicitly deferred",
                    )
                )
            elif not machine_applies and status_value != "not-applicable":
                findings.append(
                    Finding(
                        f"{location}.status",
                        "catalog applicability requires this rule to be not-applicable",
                    )
                )
''',
    )
    replace_once(
        "contracts/validate_adoption.py",
        '''        elif status_value == "not-applicable":
            if waiver_id is not None:
                findings.append(Finding(f"{location}.waiver_id", "not-applicable rule must not use a waiver"))
''',
        '''        elif status_value == "not-applicable":
            if waiver_id is not None:
                findings.append(Finding(f"{location}.waiver_id", "not-applicable rule must not use a waiver"))
            if entry.get("implementation"):
                findings.append(
                    Finding(
                        f"{location}.implementation",
                        "not-applicable rule must not claim implementation evidence",
                    )
                )
            if entry.get("verification"):
                findings.append(
                    Finding(
                        f"{location}.verification",
                        "not-applicable rule must not claim verification evidence",
                    )
                )
''',
    )
    replace_once(
        "contracts/validate_adoption.py",
        '    _text_list(mcp.get("profiles"), "extensions.mcp.profiles", findings, nonempty=True)\n    advertised = set(\n',
        '    _text_list(mcp.get("profiles"), "extensions.mcp.profiles", findings, nonempty=True)\n    _text_list(mcp.get("capabilities"), "extensions.mcp.capabilities", findings)\n    advertised = set(\n',
    )
    replace_once(
        "contracts/validate_adoption.py",
        '''    catalog_rules = _catalog_rules(catalog, skill_name, findings) if skill_name else set()
    _validate_applicability(
        assessment,
        catalog_rules,
        findings,
        as_of=as_of,
''',
        '''    catalog_rules = _catalog_rules(catalog, skill_name, findings) if skill_name else set()
    machine_applicable_rules: set[str] | None = None
    if skill_name == "mcp-server-architect":
        raw_extensions = assessment.get("extensions")
        raw_mcp = raw_extensions.get("mcp") if isinstance(raw_extensions, Mapping) else None
        if isinstance(raw_mcp, Mapping):
            level = raw_mcp.get("target_level")
            profiles = raw_mcp.get("profiles")
            capabilities = raw_mcp.get("capabilities", [])
            if (
                isinstance(level, str)
                and isinstance(profiles, list)
                and all(isinstance(item, str) for item in profiles)
                and isinstance(capabilities, list)
                and all(isinstance(item, str) for item in capabilities)
            ):
                try:
                    context = RuleContext(
                        target_level=level,
                        profiles=frozenset(profiles),
                        capabilities=frozenset(capabilities),
                    )
                    machine_applicable_rules = {
                        str(rule["id"])
                        for rule in expected_rules(catalog, skill_name, context)
                    }
                except (KeyError, TypeError, ValueError) as exc:
                    findings.append(
                        Finding(
                            "extensions.mcp",
                            f"cannot derive catalog applicability: {exc}",
                        )
                    )
    _validate_applicability(
        assessment,
        catalog_rules,
        findings,
        machine_applicable_rules=machine_applicable_rules,
        as_of=as_of,
''',
    )

    schema_path = ROOT / "contracts/adoption-assessment.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    mcp_schema = schema["properties"]["extensions"]["properties"]["mcp"]
    mcp_schema["properties"]["capabilities"] = {
        "type": "array",
        "items": {"$ref": "#/$defs/text"},
        "uniqueItems": True,
    }
    required = mcp_schema["required"]
    if "capabilities" not in required:
        required.insert(required.index("advertised_transports"), "capabilities")
    schema_path.write_text(
        json.dumps(schema, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    replace_once(
        "skills/mcp-server-architect/templates/migration-assessment.yaml.template",
        "    profiles: [REPLACE_WITH_IMPLEMENTED_PROFILE]\n    advertised_transports: [REPLACE_WITH_ADVERTISED_TRANSPORT]\n",
        "    profiles: [REPLACE_WITH_IMPLEMENTED_PROFILE]\n    capabilities: []\n    advertised_transports: [REPLACE_WITH_ADVERTISED_TRANSPORT]\n",
    )
    replace_once(
        "tests/test_adoption_contract.py",
        '                "profiles": ["python"],\n                "advertised_transports": ["stdio"],\n',
        '                "profiles": ["python"],\n                "capabilities": [],\n                "advertised_transports": ["stdio"],\n',
    )

    # Map the new execution-policy heading to its own stable rule.
    replace_once(
        "contracts/rule-catalog.yaml",
        "    - id: cicd.workflow.profiled\n      source: STANDARD.md#workflow-policy-profiles\n      description: Pull request, trusted CI, and protected release workflows are audited under explicit fail-closed profiles.\n",
        "    - id: cicd.workflow.profiled\n      source: STANDARD.md#workflow-policy-profiles\n      description: Pull request, trusted CI, and protected release workflows are audited under explicit fail-closed profiles.\n    - id: cicd.execution.on-demand\n      source: STANDARD.md#execution-policy-and-hosted-runner-budget\n      description: Cost-aware workflows remain manually dispatchable on development refs while preserving exact-SHA full acceptance gates.\n",
    )
    replace_once(
        "contracts/standard-rule-map.yaml",
        "      workflow-policy-profiles: {rule_id: cicd.workflow.profiled, primary: true}\n      python-quality: {rule_id: cicd.quality.language, primary: true}\n",
        "      workflow-policy-profiles: {rule_id: cicd.workflow.profiled, primary: true}\n      execution-policy-and-hosted-runner-budget: {rule_id: cicd.execution.on-demand, primary: true}\n      python-quality: {rule_id: cicd.quality.language, primary: true}\n",
    )

    for path, kind in (
        ("skills/ci-cd-architect/STANDARD.md", "command"),
        ("skills/ci-cd-architect/references/finding-triage.md", "ci-job"),
        ("skills/ci-cd-architect/references/on-demand-ci.md", "command"),
        ("skills/ci-cd-architect/references/protected-release-workflows.md", "command"),
    ):
        migrate_afds_frontmatter(path, kind)

    # Test renderer uses one interpreter/lock pair.
    replace_all(
        "tests/test_templates.py",
        "requirements-dev-linux-x64-py312.lock",
        "requirements-dev-linux-x64-py313.lock",
        minimum=3,
    )

    # Exact artifact identity must use the revision actually checked out.
    replace_once(
        "skills/mcp-server-architect/tools/python-template/.github/workflows/ci.yml.template",
        '''      - name: Build image from the tested wheel
        shell: bash
        run: |
          set -euo pipefail
          IMAGE="__DISTRIBUTION__:sha-${GITHUB_SHA}"
          docker build --build-arg WHEEL_FILE="$(basename "$WHEEL_FILE")" --build-arg WHEEL_SHA256="$WHEEL_SHA256" -t "$IMAGE" .
          echo "IMAGE=$IMAGE" >> "$GITHUB_ENV"
''',
        '''      - name: Build image from the tested wheel
        shell: bash
        env:
          EXPECTED_SHA: ${{ github.event.pull_request.head.sha || github.sha }}
        run: |
          set -euo pipefail
          test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"
          IMAGE="__DISTRIBUTION__:sha-${EXPECTED_SHA}"
          docker build --build-arg WHEEL_FILE="$(basename "$WHEEL_FILE")" --build-arg WHEEL_SHA256="$WHEEL_SHA256" -t "$IMAGE" .
          echo "IMAGE=$IMAGE" >> "$GITHUB_ENV"
''',
    )

    # Independent lock failures get independent regressions.
    replace_once(
        "tests/test_audit_contract_extensions.py",
        '''def test_skill_lock_rejects_moving_revision_and_cross_skill_entrypoint(tmp_path: Path) -> None:
    lock = _write_yaml(
        tmp_path / "ai-skills.lock.yaml",
        {
            "schema_version": 1,
            "repository": "paulomac1000/ai-skills",
            "revision": "main",
            "skills": {
                "example": {
                    "version": "1.2.0",
                    "revision": FULL_SHA,
                    "normative_entrypoint": "skills/other/STANDARD.md",
                }
            },
        },
    )
    findings = validate_lock(lock)
    assert any(
        "full commit SHA" in finding or "does not match" in finding
        for finding in findings
    )
    assert any("locked skill" in finding for finding in findings)
''',
        '''def test_skill_lock_rejects_moving_repository_revision(tmp_path: Path) -> None:
    lock = _write_yaml(
        tmp_path / "ai-skills.lock.yaml",
        {
            "schema_version": 1,
            "repository": "paulomac1000/ai-skills",
            "revision": "main",
            "skills": {
                "example": {
                    "version": "1.2.0",
                    "revision": FULL_SHA,
                    "normative_entrypoint": "skills/example/STANDARD.md",
                }
            },
        },
    )
    findings = validate_lock(lock)
    assert any(
        "full commit SHA" in finding or "does not match" in finding
        for finding in findings
    )


def test_skill_lock_rejects_cross_skill_entrypoint(tmp_path: Path) -> None:
    lock = _write_yaml(
        tmp_path / "ai-skills.lock.yaml",
        {
            "schema_version": 1,
            "repository": "paulomac1000/ai-skills",
            "revision": FULL_SHA,
            "skills": {
                "example": {
                    "version": "1.2.0",
                    "revision": FULL_SHA,
                    "normative_entrypoint": "skills/other/STANDARD.md",
                }
            },
        },
    )
    findings = validate_lock(lock)
    assert any("locked skill" in finding for finding in findings)
''',
    )

    # Missing/conflicting CLI identity must prove a failing exit code.
    replace_once(
        "tests/test_python_generator_cli.py",
        '''    with pytest.raises(SystemExit):
        generator.main([str(tmp_path / "missing")])
    with pytest.raises(SystemExit):
        generator.main(
''',
        '''    with pytest.raises(SystemExit) as missing:
        generator.main([str(tmp_path / "missing")])
    assert missing.value.code != 0
    with pytest.raises(SystemExit) as conflict:
        generator.main(
''',
    )
    replace_once(
        "tests/test_python_generator_cli.py",
        '''        )
    assert not (tmp_path / "missing").exists()
''',
        '''        )
    assert conflict.value.code != 0
    assert not (tmp_path / "missing").exists()
''',
    )

    # Behavior-based regression name and exact lifecycle mapping assertions.
    old_test = ROOT / "tests/test_coderabbit_followup.py"
    new_test = ROOT / "tests/test_contract_hardening_regressions.py"
    if new_test.exists():
        raise RuntimeError(f"target already exists: {new_test}")
    old_test.rename(new_test)
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if "test_coderabbit_followup.py" in text:
            path.write_text(
                text.replace(
                    "test_coderabbit_followup.py",
                    "test_contract_hardening_regressions.py",
                ),
                encoding="utf-8",
            )
    replace_once(
        "tests/test_contract_hardening_regressions.py",
        '    assert "CapabilityActiveState.Disabled" in adapter\n    assert "CapabilityActiveState.Degraded" in adapter\n    assert "CapabilityActiveState.Unavailable" in adapter\n',
        '    assert \'CapabilityActiveState.Disabled => "inactive"\' in adapter\n    assert \'CapabilityActiveState.Degraded => "inactive"\' in adapter\n    assert \'CapabilityActiveState.Unavailable => "inactive"\' in adapter\n',
    )

    regressions = ROOT / "tests/test_latest_bot_followup.py"
    text = regressions.read_text(encoding="utf-8")
    text += r'''


def test_capability_manifest_schema_error_stops_unhashable_semantics(tmp_path: Path) -> None:
    import json

    from contracts.validate_capability_manifest import validate_manifest

    manifest = {
        "schema_version": 1,
        "id": "dangerous.write",
        "name": "Dangerous write",
        "description": "Malformed approval binds produce findings, not a traceback.",
        "operation_kind": "write",
        "risk": "high",
        "determinism": "deterministic",
        "latency": "interactive",
        "impact": "external",
        "active_state": "active",
        "retryable": False,
        "idempotent": False,
        "reversible": False,
        "requires_confirmation": True,
        "idempotency_key_required": False,
        "authorization_scopes": ["write"],
        "concurrency": {"scope": "principal", "limit": 1, "queue_limit": 1},
        "max_response_bytes": 1024,
        "protocol_revisions": ["2026-07-28"],
        "approval": {"binds": [{}]},
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    assert validate_manifest(path)


def test_atomic_claim_schema_error_stops_semantics(tmp_path: Path) -> None:
    import json

    from contracts.validate_atomic_claims import validate_report

    report = tmp_path / "report.json"
    report.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "skill": "mcp-server-architect",
                "context": {
                    "target_level": "L1",
                    "profiles": [],
                    "capabilities": [],
                },
                "checks": [
                    {
                        "control_id": "mcp.architecture.separation.domain-adapter",
                        "status": "passed",
                        "evidence_types": [{}],
                        "implementation": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert validate_report(report)


def test_afds_percent_encoded_hash_remains_part_of_local_path(tmp_path: Path) -> None:
    import importlib.util
    import sys

    module_path = ROOT / "skills/afds-doc-writer/validate.py"
    spec = importlib.util.spec_from_file_location("afds_encoded_hash", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    target = tmp_path / "guide#part.md"
    target.write_text("# Guide\n", encoding="utf-8")
    source = tmp_path / "README.md"
    source.write_text("[guide](guide%23part.md)\n", encoding="utf-8")
    assert module._validate_links(
        source,
        source.read_text(encoding="utf-8"),
        tmp_path,
        check_anchors=True,
    ) == []


def test_explicit_missing_afds_governance_fails_closed(tmp_path: Path) -> None:
    import importlib.util
    import sys

    module_path = ROOT / "skills/afds-doc-writer/validate.py"
    spec = importlib.util.spec_from_file_location("afds_missing_governance", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    readme = tmp_path / "README.md"
    readme.write_text("# Example\n", encoding="utf-8")
    assert module.main(
        [
            "--root",
            str(tmp_path),
            "--governance",
            str(tmp_path / "missing.yaml"),
            str(readme),
        ]
    ) == 1


def test_hyphenated_write_permission_is_privileged() -> None:
    assert workflow_policy._permissions_write({"contents": "read-write"}) is True


def test_generated_python_image_uses_exact_checked_out_sha() -> None:
    template = (
        ROOT
        / "skills/mcp-server-architect/tools/python-template/.github/workflows/ci.yml.template"
    ).read_text(encoding="utf-8")
    expression = "${" + "{ github.event.pull_request.head.sha || github.sha }}"
    assert f"EXPECTED_SHA: {expression}" in template
    assert 'test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"' in template
    assert "sha-${EXPECTED_SHA}" in template
    assert "sha-${GITHUB_SHA}" not in template
'''
    regressions.write_text(text, encoding="utf-8")

    adoption_tests = ROOT / "tests/test_adoption_contract.py"
    text = adoption_tests.read_text(encoding="utf-8")
    text += r'''


def test_mcp_applicability_is_derived_from_catalog_context(tmp_path: Path) -> None:
    document, catalog, skills = assessment_for(
        tmp_path,
        skill_name="mcp-server-architect",
        mcp=True,
    )
    catalog["skills"]["mcp-server-architect"]["rules"][0]["applies_when"] = {
        "maturity_at_least": "L4"
    }
    result = "\n".join(findings(document, catalog, skills, tmp_path))
    assert "catalog applicability requires this rule to be not-applicable" in result
'''
    adoption_tests.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
