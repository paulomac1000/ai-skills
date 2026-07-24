"""Executable coverage contract for normative standard headings and stable rule IDs."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "contracts/rule-catalog.yaml"
MAP_PATH = ROOT / "contracts/standard-rule-map.yaml"
HEADING = re.compile(r"^##\s+(.+?)\s*$")
SOURCE = re.compile(r"^STANDARD\.md#([a-z0-9-]+)$")


def heading_anchor(title: str) -> str:
    """Return the repository's deterministic GitHub-compatible H2 anchor subset."""
    normalized = title.casefold().replace(".net", "net")
    normalized = re.sub(r"[^a-z0-9 _-]", "", normalized)
    normalized = re.sub(r"[ _]+", "-", normalized)
    return re.sub(r"-+", "-", normalized).strip("-")


def normative_h2_titles(text: str) -> list[str]:
    """Return H2 titles outside fenced code blocks."""
    titles: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        stripped = line.lstrip()
        marker = "```" if stripped.startswith("```") else "~~~" if stripped.startswith("~~~") else None
        if marker is not None:
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            continue
        if fence is not None:
            continue
        match = HEADING.fullmatch(line)
        if match is not None:
            titles.append(match.group(1))
    return titles


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a mapping-valued YAML contract."""
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict), path
    return document


def catalog_rules() -> dict[str, dict[str, dict[str, Any]]]:
    """Index the rule catalog by skill and stable rule ID."""
    catalog = load_yaml(CATALOG_PATH)
    assert catalog["schema_version"] == 1
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for skill_name, skill_contract in catalog["skills"].items():
        rules = skill_contract["rules"]
        ids = [rule["id"] for rule in rules]
        assert len(ids) == len(set(ids)), skill_name
        result[skill_name] = {rule["id"]: rule for rule in rules}
    return result


def test_every_normative_h2_is_mapped_or_explicitly_excluded() -> None:
    rule_map = load_yaml(MAP_PATH)
    catalog = catalog_rules()
    assert rule_map["schema_version"] == 1
    assert set(rule_map["skills"]) == set(catalog)

    for skill_name, mapping in rule_map["skills"].items():
        standard = ROOT / "skills" / skill_name / "STANDARD.md"
        anchors = {heading_anchor(title) for title in normative_h2_titles(standard.read_text(encoding="utf-8"))}
        mapped = mapping["headings"]
        assert set(mapped) == anchors, skill_name

        used_rules: set[str] = set()
        primary_rules: dict[str, str] = {}
        for anchor, entry in mapped.items():
            assert isinstance(entry, dict), (skill_name, anchor)
            has_rule = isinstance(entry.get("rule_id"), str)
            excluded = entry.get("excluded") is True
            assert has_rule != excluded, (skill_name, anchor, entry)
            if excluded:
                assert isinstance(entry.get("rationale"), str) and entry["rationale"].strip()
                assert entry.get("primary") is not True
                continue

            rule_id = entry["rule_id"]
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
            assert isinstance(rule.get("description"), str) and rule["description"].strip()


def test_fenced_h2_examples_are_not_normative_rules() -> None:
    source = "## Real rule\n\n```text\n## Not a rule\n```\n\n~~~markdown\n## Also not a rule\n~~~\n"
    assert normative_h2_titles(source) == ["Real rule"]


def test_manifests_pin_the_catalog_and_heading_map() -> None:
    for manifest_path in sorted((ROOT / "skills").glob("*/manifest.yaml")):
        manifest = load_yaml(manifest_path)
        adoption = manifest["adoption"]
        assert adoption["rule_catalog"] == "contracts/rule-catalog.yaml"
        assert adoption["rule_map"] == "contracts/standard-rule-map.yaml"
        for key in ("rule_catalog", "rule_map"):
            assert (ROOT / adoption[key]).is_file()
