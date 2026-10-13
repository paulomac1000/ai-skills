"""Bounded AFDS architecture-navigation regressions (#116)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/agents-md-architect/tools"))
import audit_agents_md as auditor  # noqa: E402

MAP = "docs/systems/navigation.md"
ROUTE = (
    '<!-- agents-md: route owner="docs/systems/navigation.md" '
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
        """<!-- agents-md: conditional-owner -->

# Architecture navigation

## Stable work units

| Unit | Implementation | Contracts | Tests | Operations | Decisions |
| --- | --- | --- | --- | --- | --- |
| Payments | [processor](../../src/payments/process.py) | [schema](../../contracts/payments/schema.json) | [test](../../tests/payments/test_process.py) | [runbook](../operations/payments.md) | [ADR](../decisions/payment-routing.md) |
| Reporting | [pipeline](../../src/reporting/pipeline.py) | not applicable (internal) | [test](../../tests/reporting/test_pipeline.py) | not applicable (batch) | not applicable (none) |

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
        path = (repo / "docs/systems" / match.group(1)).resolve()
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
    assert skill.index("Before running broad repository discovery") < skill.index(
        "Run `tools/discover_repository.py`"
    )


def test_owner_free_inventory_is_invalid(large_repo: Path) -> None:
    path = large_repo / MAP
    path.write_text(
        path.read_text(encoding="utf-8").replace("[processor](../../src/payments/process.py)", "all files in src/"),
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


def test_no_mandatory_layout_or_runtime_snapshot() -> None:
    standard = (ROOT / "skills/afds-doc-writer/STANDARD.md").read_text(encoding="utf-8")
    assert "MAY maintain one bounded, canonical architecture navigation map" in standard
    assert "no mandatory monorepo, vertical slices, directory layout or fixed filename" in standard
    assert "Volatile runtime observations belong to live evidence" in standard
