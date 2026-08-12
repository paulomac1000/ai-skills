#!/usr/bin/env python3
"""Add final applicability boundary coverage; deleted before commit."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "tests/test_contract_boundary_coverage.py"
text = path.read_text(encoding="utf-8")
text += r'''


def test_rule_applicability_metadata_and_context_edges() -> None:
    from contracts import rule_applicability

    with pytest.raises(ValueError, match="unknown maturity level"):
        rule_applicability.RuleContext("L9")

    invalid = {
        "id": "demo.rule",
        "applies_when": {
            "maturity_at_least": "L9",
            "profiles_any": ["remote-http", "remote-http"],
            "profiles_all": "not-a-list",
            "capabilities_any": [""],
            "capabilities_all": [1],
            "unknown": True,
        },
        "severity": "critical",
        "waivable": "no",
        "required_evidence": ["unknown"],
    }
    findings = rule_applicability.validate_rule_metadata(invalid)
    assert any("unsupported applicability" in item for item in findings)
    assert any("invalid maturity" in item for item in findings)
    assert any("profiles_any" in item for item in findings)
    assert any("profiles_all" in item for item in findings)
    assert any("capabilities_any" in item for item in findings)
    assert any("capabilities_all" in item for item in findings)
    assert any("severity" in item for item in findings)
    assert any("waivable" in item for item in findings)
    assert any("required_evidence" in item for item in findings)
    assert rule_applicability.validate_rule_metadata({"id": "x", "applies_when": []})

    rule = {
        "id": "demo.rule",
        "applies_when": {
            "maturity_at_least": "L2",
            "profiles_any": ["remote-http"],
            "profiles_all": ["remote-http"],
            "capabilities_any": ["write"],
            "capabilities_all": ["write"],
        },
        "severity": "blocking",
        "waivable": False,
        "required_evidence": ["integration"],
    }
    assert not rule_applicability.rule_applies(rule, rule_applicability.RuleContext("L1"))
    assert not rule_applicability.rule_applies(
        rule, rule_applicability.RuleContext("L2", profiles=frozenset({"local-stdio"}), capabilities=frozenset({"write"}))
    )
    assert rule_applicability.rule_applies(
        rule, rule_applicability.RuleContext("L2", profiles=frozenset({"remote-http"}), capabilities=frozenset({"write"}))
    )


def test_expected_rules_rejects_bad_catalog_shapes_and_applies_defaults() -> None:
    from contracts import rule_applicability

    context = rule_applicability.RuleContext("L1")
    with pytest.raises(ValueError, match="unknown skill"):
        rule_applicability.expected_rules({}, "demo", context)
    with pytest.raises(ValueError, match="has no rules"):
        rule_applicability.expected_rules({"skills": {"demo": {"rules": None}}}, "demo", context)
    with pytest.raises(ValueError, match="non-mapping rule"):
        rule_applicability.expected_rules({"skills": {"demo": {"rules": ["bad"]}}}, "demo", context)

    result = rule_applicability.expected_rules(
        {"skills": {"demo": {"rules": [{"id": "demo.default"}]}}},
        "demo",
        context,
    )
    assert len(result) == 1
    assert result[0]["severity"] == "blocking"
    assert result[0]["required_evidence"] == ["unit"]
'''
path.write_text(text, encoding="utf-8")
