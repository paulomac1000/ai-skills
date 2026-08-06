"""Stable rule-catalog coverage and machine-readable applicability contracts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from contracts.rule_applicability import EVIDENCE_TYPES, LEVELS, validate_rule_metadata

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "contracts/rule-catalog.yaml"
MAP_PATH = ROOT / "contracts/standard-rule-map.yaml"
SOURCE = re.compile(r"^STANDARD[.]md#([a-z0-9-]+)$")


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), path
    return value


def heading_anchor(title: str) -> str:
    normalized = title.casefold().replace(".net", "net")
    normalized = re.sub(r"[^a-z0-9 _-]", "", normalized)
    normalized = re.sub(r"[ _]+", "-", normalized)
    return re.sub(r"-+", "-", normalized).strip("-")


def normative_h2_titles(source: str) -> list[str]:
    titles: list[str] = []
    fence: str | None = None
    for line in source.splitlines():
        stripped = line.lstrip()
        marker = None
        if stripped.startswith("```"):
            marker = "```"
        elif stripped.startswith("~~~"):
            marker = "~~~"
        if marker:
            if fence is None:
                fence = marker
            elif marker == fence:
                fence = None
            continue
        if fence is None and line.startswith("## "):
            titles.append(line[3:].strip())
    return titles


def catalog_rules() -> dict[str, dict[str, dict[str, Any]]]:
    catalog = load_yaml(CATALOG_PATH)
    assert catalog["schema_version"] == 1
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for skill_name, skill_contract in catalog["skills"].items():
        rules = skill_contract["rules"]
        ids = [rule["id"] for rule in rules]
        assert len(ids) == len(set(ids)), skill_name
        result[skill_name] = {rule["id"]: rule for rule in rules}
    return result


def mapped_rule_ids(entry: dict[str, Any]) -> list[str]:
    if "rule_id" in entry:
        assert "rule_ids" not in entry
        return [entry["rule_id"]]
    value = entry.get("rule_ids")
    assert isinstance(value, list) and value
    assert all(isinstance(item, str) for item in value)
    assert len(value) == len(set(value))
    return value


def test_every_normative_heading_is_mapped_or_explicitly_excluded() -> None:
    rule_map = load_yaml(MAP_PATH)
    catalog = catalog_rules()
    assert rule_map["schema_version"] == 1
    assert set(rule_map["skills"]) == set(catalog)

    for skill_name, mapping in rule_map["skills"].items():
        standard = ROOT / "skills" / skill_name / "STANDARD.md"
        anchors = {
            heading_anchor(title)
            for title in normative_h2_titles(standard.read_text(encoding="utf-8"))
        }
        mapped = mapping["headings"]
        assert set(mapped) == anchors, skill_name

        used_rules: set[str] = set()
        primary_rules: dict[str, str] = {}
        for anchor, entry in mapped.items():
            assert isinstance(entry, dict), (skill_name, anchor)
            excluded = entry.get("excluded") is True
            has_rules = "rule_id" in entry or "rule_ids" in entry
            assert has_rules != excluded, (skill_name, anchor, entry)
            if excluded:
                rationale = entry.get("rationale")
                assert isinstance(rationale, str) and rationale.strip()
                assert entry.get("primary") is not True
                continue
            for rule_id in mapped_rule_ids(entry):
                assert rule_id in catalog[skill_name], (skill_name, anchor, rule_id)
                used_rules.add(rule_id)
                if entry.get("primary") is True:
                    assert rule_id not in primary_rules, (skill_name, rule_id)
                    primary_rules[rule_id] = anchor

        assert used_rules == set(catalog[skill_name]), skill_name
        assert set(primary_rules) == set(catalog[skill_name]), skill_name
        for rule_id, rule in catalog[skill_name].items():
            source = rule.get("source")
            assert isinstance(source, str)
            match = SOURCE.fullmatch(source)
            assert match, (skill_name, rule_id, source)
            assert match.group(1) in anchors
            assert primary_rules[rule_id] == match.group(1), (skill_name, rule_id)
            description = rule.get("description")
            assert isinstance(description, str) and description.strip()


def test_fenced_h2_examples_do_not_become_normative_sections() -> None:
    source = """## Real rule

```text
## Not a rule
```

~~~markdown
## Also not a rule
~~~
"""
    assert normative_h2_titles(source) == ["Real rule"]


def test_every_skill_manifest_points_to_the_shared_catalog_and_map() -> None:
    for manifest_path in sorted((ROOT / "skills").glob("*/manifest.yaml")):
        manifest = load_yaml(manifest_path)
        adoption = manifest["adoption"]
        assert adoption["rule_catalog"] == "contracts/rule-catalog.yaml"
        assert adoption["rule_map"] == "contracts/standard-rule-map.yaml"
        assert (ROOT / adoption["rule_catalog"]).is_file()
        assert (ROOT / adoption["rule_map"]).is_file()


def test_mcp_rules_declare_machine_readable_applicability() -> None:
    rules = catalog_rules()["mcp-server-architect"]
    assert len(rules) >= 20
    for rule_id, rule in rules.items():
        assert validate_rule_metadata(rule) == [], rule_id
        applies = rule["applies_when"]
        assert applies["maturity_at_least"] in LEVELS
        assert rule["severity"] in {"blocking", "advisory"}
        assert type(rule["waivable"]) is bool
        assert set(rule["required_evidence"]) <= EVIDENCE_TYPES
