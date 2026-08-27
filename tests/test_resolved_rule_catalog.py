"""Tests for deterministic externally consumable rule-source identities."""

from __future__ import annotations

import hashlib
from pathlib import Path

from contracts.render_rule_catalog import render_catalog

ROOT = Path(__file__).resolve().parents[1]


def test_resolved_rule_catalog_uses_full_paths_existing_anchors_and_digests() -> None:
    rendered = render_catalog(repository_root=ROOT)
    for skill, skill_catalog in rendered["skills"].items():
        for rule in skill_catalog["rules"]:
            source_path, anchor = rule["source"].split("#", 1)
            assert source_path.startswith(f"skills/{skill}/")
            assert anchor
            path = ROOT / source_path
            assert path.is_file()
            expected = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            assert rule["source_digest"] == expected


def test_resolved_rule_catalog_is_deterministic_and_bound_to_input() -> None:
    first = render_catalog(repository_root=ROOT)
    second = render_catalog(repository_root=ROOT)
    assert first == second
    catalog = ROOT / "contracts/rule-catalog.yaml"
    assert first["generated_from"] == {
        "path": "contracts/rule-catalog.yaml",
        "digest": "sha256:" + hashlib.sha256(catalog.read_bytes()).hexdigest(),
    }
