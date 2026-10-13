"""Bounded AFDS architecture-navigation regressions (#116)."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/agents-md-architect/tools"))
import audit_agents_md as auditor  # noqa: E402

MAP = "navigation.md"
ROUTE = (
    '<!-- agents-md: route owner="navigation.md" '
    'when="before scoping a Payments change" purpose="canonical owners" -->'
)


@pytest.fixture
def large_repo(tmp_path: Path) -> Path:
    files = {
        "src/payments/process.py": "def process(): return True\n",
        "contracts/payments/schema.json": "{}\n",
        "tests/payments/test_process.py": "def test_process(): assert True\n",
        "docs/operations/payments.md": "# Payments operations\n",
        "docs/decisions/payment-routing.md": "# Routing decision\n",
        "src/reporting/pipeline.py": "def pipeline(): return True\n",
        "tests/reporting/test_pipeline.py": "def test_pipeline(): assert True\n",
    }
    for relative, body in files.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    for number in range(64):
        target = tmp_path / f"src/unrelated/module_{number:03d}.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"VALUE = {number}\n", encoding="utf-8")
    navigation = tmp_path / MAP
    navigation.parent.mkdir(parents=True, exist_ok=True)
    navigation.write_text(
        """---
afds_schema_version: 2
description: Synthetic architecture navigation map for bounded discovery regression testing.
doc_id: system.architecture-navigation-fixture
type: system
status: active
rigor: informative
owners: [documentation-maintainers]
---

<!-- agents-md: conditional-owner -->

# Architecture navigation

## Stable work units

| Unit | Implementation | Contracts | Tests | Operations | Decisions |
| --- | --- | --- | --- | --- | --- |
| Payments | [processor](src/payments/process.py) | [schema](contracts/payments/schema.json) | [test](tests/payments/test_process.py) | [runbook](docs/operations/payments.md) | [ADR](docs/decisions/payment-routing.md) |
| Reporting | [pipeline](src/reporting/pipeline.py) | not applicable (internal) | [test](tests/reporting/test_pipeline.py) | not applicable (batch) | not applicable (none) |

Payments consumes Reporting output through the Payments schema.
""",
        encoding="utf-8",
    )
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/ci.py").write_text("print('gate')\n", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text(
        """# AGENTS.md

These instructions apply to this repository.

## Scope

These instructions apply to the repository.

## Commands and verification

Full gate: python scripts/ci.py

## Architecture boundaries

Generated output is not canonical.

## Safety boundaries

Secrets are prohibited. Destructive writes require authorization.

## Architecture routing

""" + ROUTE + "\nBefore scoping a Payments change, read [the architecture map]("
        + MAP + ") and the selected owners.\n"
        + "\n## Definition of done\n\nReport exact revision and verification.\n",
        encoding="utf-8",
    )
    return tmp_path


def owners_for(repo: Path, unit: str) -> list[Path]:
    """Synthetic fixture reader, not a public Markdown parsing contract."""
    text = (repo / MAP).read_text(encoding="utf-8")
    row = next((line for line in text.splitlines() if line.startswith(f"| {unit} |")), None)
    if row is None:
        raise ValueError("unknown unit")
    cells = [part.strip() for part in row.strip("|").split("|")]
    if len(cells) != 6:
        raise ValueError("incomplete map")
    targets = []
    for cell in cells[1:]:
        if cell.startswith("not applicable ("):
            continue
        match = re.fullmatch(r"\[[^]]+\]\(([^)]+)\)", cell)
        if match is None:
            raise ValueError("missing owner")
        path = (repo / match.group(1)).resolve()
        if not path.is_relative_to(repo.resolve()) or not path.is_file():
            raise ValueError("invalid owner")
        targets.append(path)
    if not targets:
        raise ValueError("owner-free inventory")
    return targets


def test_rule_catalog_map_points_to_one_normative_owner() -> None:
    catalog = yaml.safe_load((ROOT / "contracts/rule-catalog.yaml").read_text(encoding="utf-8"))
    mapping = yaml.safe_load((ROOT / "contracts/standard-rule-map.yaml").read_text(encoding="utf-8"))
    rules = [r for r in catalog["skills"]["afds-doc-writer"]["rules"] if r["id"] == "afds.system.navigation-bounded"]
    assert len(rules) == 1
    assert rules[0]["source"] == "STANDARD.md#architecture-navigation-specialization"
    assert mapping["skills"]["afds-doc-writer"]["headings"]["architecture-navigation-specialization"] == {
        "rule_id": "afds.system.navigation-bounded", "primary": True,
    }


def test_navigation_regressions_project_into_all_affected_rule_claims() -> None:
    claim_plan = yaml.safe_load((ROOT / "contracts/evidence-claim-plan.yaml").read_text(encoding="utf-8"))
    claims = {
        item["subject"]: item
        for item in claim_plan["profiles"]["repository-rules"]
        if item["kind"] == "rule"
    }
    for rule in (
        "afds.ownership.lifecycle",
        "afds.system.navigation-bounded",
        "agents.scope.precedence",
        "agents.discovery.evidence",
        "agents.ownership.boundaries",
        "agents.context.routed",
        "agents.context.trigger-safe",
    ):
        assert "*test_architecture_navigation_contract*" in claims[rule]["selectors"]


def test_navigation_skill_routing_corpora_cover_positive_and_collision_cases() -> None:
    validator_path = ROOT / "skills/skill-architect/tools/validate_skill_evals.py"
    spec = importlib.util.spec_from_file_location("afds_navigation_eval_validator", validator_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    corpus = ROOT / "evals/skills/afds-doc-writer"
    assert module.validate_path(corpus) == []
    routing = yaml.safe_load((corpus / "routing.yaml").read_text(encoding="utf-8"))
    cases = {item["id"]: item for item in routing["cases"]}
    assert cases["canonical-architecture-navigation-map"]["selected_skills"] == ["afds-doc-writer"]
    assert "agents-md-architect" in cases["architecture-map-vs-agents-instructions"]["rejected_skills"]
    assert cases["agents-only-route-near-miss"]["selected_skills"] == ["agents-md-architect"]
    assert cases["maintain-governed-document-freshness"]["selected_skills"] == ["afds-doc-writer"]

    neighbors = yaml.safe_load(
        (ROOT / "evals/skills/agents-md-architect/routing.yaml").read_text(encoding="utf-8")
    )
    assert any(
        c["kind"] == "negative" and "afds-doc-writer" in c["selected_skills"]
        for c in neighbors["cases"]
    )
    description = (ROOT / "skills/afds-doc-writer/SKILL.md").read_text(encoding="utf-8")
    assert "bounded architecture navigation maps" in description.split("---", 2)[1]
    assert "maintain evidence-based technical documentation" in description.split("---", 2)[1]


def test_reachable_route_scopes_large_repo_to_five_owners(large_repo: Path) -> None:
    instructions = (large_repo / "AGENTS.md").read_text(encoding="utf-8")
    assert ROUTE in instructions
    assert "<!-- agents-md: conditional-owner -->" not in instructions
    _, findings = auditor.audit(large_repo, "application", "single", "en")
    assert not [x.code for x in findings if x.code.startswith("routing.")]
    owners = owners_for(large_repo, "Payments")
    assert len(owners) == 5
    assert len(owners) * 5 < len(list(large_repo.rglob("*.py")))


def _opened_for_task(repo: Path, task: str) -> list[Path]:
    """Exercise conditional route selection over the actual pre-loaded marker."""
    instructions = (repo / "AGENTS.md").read_text(encoding="utf-8")
    opened = [repo / "AGENTS.md"]
    directives = re.findall(
        r'<!-- agents-md: route owner="([^"]+)" when="([^"]+)" purpose="([^"]+)" -->',
        instructions,
    )
    for owner, when, _purpose in directives:
        trigger = re.fullmatch(r"before scoping a ([A-Za-z]+) change", when)
        if trigger is None or trigger.group(1).casefold() not in task.casefold().split():
            continue
        path = (repo / owner).resolve()
        if not path.is_relative_to(repo.resolve()) or not path.is_file():
            raise ValueError("untrusted architecture route")
        opened.append(path)
        opened.extend(owners_for(repo, trigger.group(1)))
    return opened


def test_unrelated_task_does_not_eagerly_load_map(large_repo: Path) -> None:
    unrelated = _opened_for_task(large_repo, "Upgrade unrelated formatter")
    assert unrelated == [large_repo / "AGENTS.md"]
    related = _opened_for_task(large_repo, "Payments change")
    assert related[:2] == [large_repo / "AGENTS.md", large_repo / MAP]
    assert len(related) == 7
    assert len(related) < len(list(large_repo.rglob("*.py")))
    skill = (ROOT / "skills/agents-md-architect/SKILL.md").read_text(encoding="utf-8")
    assert skill.index("Read `references/instruction-precedence-and-platforms.md`") < skill.index(
        "Before running broad repository discovery"
    )
    assert skill.index("Before running broad repository discovery") < skill.index(
        "Run `tools/discover_repository.py`"
    )
    assert "only when no route applies or those owners do not answer the task" in skill
    assert "inspect broader repository evidence only for gaps" in skill
    reference = (ROOT / "skills/agents-md-architect/references/repository-discovery.md").read_text(
        encoding="utf-8"
    )
    assert "When those owners answer the task, do not run the wider discovery sequence" in reference


def test_owner_free_inventory_is_invalid(large_repo: Path) -> None:
    path = large_repo / MAP
    path.write_text(
        path.read_text(encoding="utf-8").replace("[processor](src/payments/process.py)", "all files in src/"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing owner"):
        owners_for(large_repo, "Payments")


def test_stale_owner_and_unreachable_trigger_rejected(large_repo: Path) -> None:
    (large_repo / "src/payments/process.py").unlink()
    with pytest.raises(ValueError, match="invalid owner"):
        owners_for(large_repo, "Payments")
    agents = large_repo / "AGENTS.md"
    agents.write_text(agents.read_text(encoding="utf-8").replace(ROUTE, ""), encoding="utf-8")
    _, findings = auditor.audit(large_repo, "application", "single", "en")
    assert "routing.trigger-unreachable" in {x.code for x in findings}



def test_moved_navigation_owner_requires_map_refresh_and_route_review(large_repo: Path) -> None:
    navigation = large_repo / MAP
    old_owner = large_repo / "src/payments/process.py"
    new_owner = large_repo / "src/payments/core/process.py"
    new_owner.parent.mkdir(parents=True, exist_ok=True)
    old_owner.rename(new_owner)

    # The old map cannot silently pass with a stale implementation owner.
    with pytest.raises(ValueError, match="invalid owner"):
        owners_for(large_repo, "Payments")

    original = navigation.read_text(encoding="utf-8")
    old_link = "[processor](src/payments/process.py)"
    new_link = "[processor](src/payments/core/process.py)"
    assert old_link in original
    navigation.write_text(original.replace(old_link, new_link), encoding="utf-8")

    selected = owners_for(large_repo, "Payments")
    assert new_owner.resolve() in selected
    assert len(selected) == 5
    assert old_link not in navigation.read_text(encoding="utf-8")

    # The canonical map remains at the same routed owner; verify its trigger
    # still works rather than rewriting the always-loaded instruction.
    _, findings = auditor.audit(large_repo, "application", "single", "en")
    assert not [f.code for f in findings if f.code.startswith("routing.")]
    assert large_repo / MAP in _opened_for_task(large_repo, "Payments change")
    lifecycle = (ROOT / "skills/afds-doc-writer/references/lifecycle-and-impact.md").read_text(
        encoding="utf-8"
    )
    assert "update the canonical architecture map" in lifecycle
    assert "review the applicable pre-discovery routes" in lifecycle


def test_navigation_map_is_a_valid_governed_system_document(large_repo: Path) -> None:
    path = ROOT / "skills/afds-doc-writer/validate.py"
    spec = importlib.util.spec_from_file_location("afds_navigation_fixture_validator", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    map_file = large_repo / MAP
    raw = map_file.read_text(encoding="utf-8")
    metadata = yaml.safe_load(raw.split("---", 2)[1])
    assert metadata["type"] == "system"
    assert metadata["afds_schema_version"] == 2
    assert module.validate(map_file, large_repo, minimum_schema_version=2) == []

    map_file.write_text(
        raw.replace("[processor](src/payments/process.py)", "[processor](../outside.py)"),
        encoding="utf-8",
    )
    invalid = module.validate(map_file, large_repo, minimum_schema_version=2)
    assert any("unsafe relative link" in finding.message for finding in invalid)


def test_playbook_example_matches_verified_synthetic_owner_map(large_repo: Path) -> None:
    playbook = ROOT / "skills/afds-doc-writer/references/type-playbooks.md"
    text = playbook.read_text(encoding="utf-8")
    example = (large_repo / MAP).read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if line.startswith(("| Payments |", "| Reporting |"))]
    assert len(rows) == 2
    assert all(row in example for row in rows)
    for row in rows:
        for href in re.findall(r"\[[^]]+\]\(([^)]+)\)", row):
            assert not href.startswith(("/", "http:", "https:"))
            assert ".." not in href.split("/")
            owner = (large_repo / href).resolve(strict=True)
            assert owner.is_relative_to(large_repo.resolve())
            assert owner.is_file()


def test_no_mandatory_layout_or_runtime_snapshot() -> None:
    standard = (ROOT / "skills/afds-doc-writer/STANDARD.md").read_text(encoding="utf-8")
    assert "MAY maintain one bounded, canonical architecture navigation map" in standard
    assert "no mandatory monorepo, vertical slices, directory layout or fixed filename" in standard
    assert "Volatile runtime observations belong to live evidence" in standard
