from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills" / "agents-md-architect" / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from agents_md_gate_sources import classify_gate_sources  # noqa: E402
from audit_agents_md import _known_gate_commands_with_inventory  # noqa: E402
from discover_repository import discover  # noqa: E402


def _write_script(root: Path, name: str, text: str = "VALUE = 1\n") -> Path:
    path = root / "scripts" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_discovery_issues_make_source_inventory_incomplete(tmp_path: Path) -> None:
    discovery = replace(discover(tmp_path), issues=("discovery entry budget exhausted",))

    inventory = classify_gate_sources(tmp_path, discovery, limit=64)
    _known, audit_inventory, findings = _known_gate_commands_with_inventory(tmp_path, discovery)

    assert inventory.issues == ("discovery entry budget exhausted",)
    assert audit_inventory.issues == inventory.issues
    assert any(finding.code == "evidence.incomplete-gate-source-inventory" for finding in findings)


def test_local_checkout_working_directory_is_not_overridden_by_external_workspace_checkout(
    tmp_path: Path,
) -> None:
    _write_script(tmp_path, "check.py")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          repository: example/authority\n"
        "          ref: 0123456789abcdef0123456789abcdef01234567\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          path: candidate\n"
        "      - name: Run local candidate source\n"
        "        working-directory: candidate\n"
        "        run: python scripts/check.py\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    row = next(source for source in inventory.sources if source.path == "scripts/check.py")
    assert row.classification == "task_entrypoint"
    assert row.counted is True
    assert row.origins == (".github/workflows/ci.yml:14",)
    assert not any(source.path.endswith("/scripts/check.py") for source in inventory.sources)
    assert not inventory.issues


def test_explicit_checkout_alias_is_not_stripped_inside_its_own_working_directory(tmp_path: Path) -> None:
    _write_script(tmp_path, "check.py")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          path: candidate\n"
        "      - name: Run from candidate checkout\n"
        "        working-directory: candidate\n"
        "        run: python candidate/scripts/check.py\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    row = next(source for source in inventory.sources if source.path == "scripts/check.py")
    assert row.classification == "helper"
    assert row.counted is False
    assert any("referenced task path not found" in issue for issue in inventory.issues)


def test_workspace_escape_is_not_attributed_to_external_checkout_alias(tmp_path: Path) -> None:
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        "          repository: example/authority\n"
        "          ref: 0123456789abcdef0123456789abcdef01234567\n"
        "          path: upstream\n"
        "      - run: python ../upstream/tools/audit.py\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert any("escapes" in issue for issue in inventory.issues)
    assert not any(source.path.startswith("external:example/authority@") for source in inventory.sources)


@pytest.mark.parametrize(
    ("repository", "reference"),
    [
        (None, None),
        ("example/validator", "0123456789abcdef0123456789abcdef01234567"),
    ],
)
def test_dynamic_checkout_path_is_incomplete_for_local_and_external_repositories(
    tmp_path: Path,
    repository: str | None,
    reference: str | None,
) -> None:
    _write_script(tmp_path, "check.py")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    repository_option = f"          repository: {repository}\n" if repository is not None else ""
    reference_option = f"          ref: {reference}\n" if reference is not None else ""
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "        with:\n"
        f"{repository_option}"
        f"{reference_option}"
        "          path: ${{ env.CHECKOUT_PATH }}\n"
        "      - run: python scripts/check.py\n",
        encoding="utf-8",
    )

    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)

    assert any("checkout path is dynamic" in issue for issue in inventory.issues)


def test_cd_transition_updates_command_scope(tmp_path: Path) -> None:
    """Review r1 F2: multiline cd transitions update subsequent command ownership."""
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "x.py").write_text("VALUE = 1\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - run: |\n"
        "          cd tools\n"
        "          python x.py\n",
        encoding="utf-8",
    )
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    row = next(source for source in inventory.sources if source.path == "tools/x.py")
    assert row.classification == "task_entrypoint"
    assert row.counted is True
    assert not inventory.issues


def test_inline_cd_transition_updates_command_scope(tmp_path: Path) -> None:
    """Review r1 F2: inline cd && command keeps the transitioned working directory."""
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "x.py").write_text("VALUE = 1\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - run: cd tools && python x.py\n",
        encoding="utf-8",
    )
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    row = next(source for source in inventory.sources if source.path == "tools/x.py")
    assert row.classification == "task_entrypoint"
    assert row.counted is True
    assert not inventory.issues


def test_unresolvable_cd_transition_fails_closed(tmp_path: Path) -> None:
    """Review r1 F2: a variable cd target blocks complete inventory instead of silent root attribution."""
    (tmp_path / "x.py").write_text("VALUE = 1\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - run: |\n"
        "          cd $BUILD_DIR\n"
        "          python x.py\n",
        encoding="utf-8",
    )
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    assert any("unresolved" in issue for issue in inventory.issues)
    assert not any(source.path == "x.py" and source.counted for source in inventory.sources)


def test_composite_action_steps_are_command_sources(tmp_path: Path) -> None:
    """Review r1 F3: local composite action run steps keep entrypoint coverage."""
    action = tmp_path / ".github" / "actions" / "validate"
    action.mkdir(parents=True)
    (action / "action.yml").write_text(
        "name: validate\n"
        "runs:\n"
        "  using: composite\n"
        "  steps:\n"
        "    - shell: bash\n"
        "      run: python tools/check.py\n",
        encoding="utf-8",
    )
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "check.py").write_text("VALUE = 1\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - uses: ./.github/actions/validate\n",
        encoding="utf-8",
    )
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    row = next(source for source in inventory.sources if source.path == "tools/check.py")
    assert row.classification == "task_entrypoint"
    assert row.counted is True
    assert not inventory.issues


def test_unresolved_composite_action_reference_fails_closed(tmp_path: Path) -> None:
    """Review r1 F3: a local composite action reference without a tree target blocks completeness."""
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - uses: ./.github/actions/missing\n",
        encoding="utf-8",
    )
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    assert any("composite" in issue or "unresolved" in issue for issue in inventory.issues)
