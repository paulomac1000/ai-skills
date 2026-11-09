from __future__ import annotations

import os
import subprocess
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
    assert any("directory transition" in issue for issue in inventory.issues)
    assert not any(source.path == "x.py" and source.counted for source in inventory.sources)


def test_composite_action_steps_are_command_sources(tmp_path: Path) -> None:
    """Review r1 F3: local composite action run steps keep entrypoint coverage."""
    action = tmp_path / ".github" / "actions" / "validate"
    action.mkdir(parents=True)
    (action / "action.yml").write_text(
        "name: validate\nruns:\n  using: composite\n  steps:\n    - shell: bash\n      run: python tools/check.py\n",
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


def _composite(tmp_path: Path, action_body: str, workflow_uses: str = "./.github/actions/validate") -> None:
    action = tmp_path / ".github" / "actions" / "validate"
    action.mkdir(parents=True)
    (action / "action.yml").write_text(action_body, encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        f"      - uses: {workflow_uses}\n",
        encoding="utf-8",
    )


def test_composite_action_step_working_directory_is_owned(tmp_path: Path) -> None:
    """R1: composite step working-directory owns command attribution."""
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "check.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "check.py").write_text("VALUE = 2\n", encoding="utf-8")
    _composite(
        tmp_path,
        "runs:\n  using: composite\n  steps:\n    - shell: bash\n      working-directory: tools\n      run: python check.py\n",
    )
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    counted = {source.path for source in inventory.sources if source.counted}
    assert "tools/check.py" in counted
    assert "check.py" not in counted
    assert not inventory.issues


def test_uncalled_function_body_does_not_mutate_scope(tmp_path: Path) -> None:
    """R2: an uncalled function definition body must not change ambient scope."""
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "check.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "check.py").write_text("VALUE = 2\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n"
        "  verify:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - run: |\n"
        "          helper() {\n"
        "              cd tools\n"
        "          }\n"
        "          python check.py\n",
        encoding="utf-8",
    )
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    counted = {source.path for source in inventory.sources if source.counted}
    assert "check.py" in counted
    assert "tools/check.py" not in counted
    assert not inventory.issues


def test_semicolon_transition_applies_at_position(tmp_path: Path) -> None:
    """R3: semicolon-separated transitions apply at their ordered position."""
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "check.py").write_text("VALUE = 1\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  verify:\n    runs-on: ubuntu-24.04\n    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - run: cd tools; python check.py\n",
        encoding="utf-8",
    )
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    assert "tools/check.py" in {source.path for source in inventory.sources if source.counted}
    assert not inventory.issues


def test_chained_transitions_apply_in_order(tmp_path: Path) -> None:
    """R3: chained && transitions apply in execution order, not once per block."""
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("VALUE = 2\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  verify:\n    runs-on: ubuntu-24.04\n    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - run: cd tools && python a.py && cd .. && python b.py\n",
        encoding="utf-8",
    )
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    counted = {source.path for source in inventory.sources if source.counted}
    assert {"tools/a.py", "b.py"} <= counted
    assert not inventory.issues


def test_subshell_transition_is_isolated(tmp_path: Path) -> None:
    """R3: subshell-local directory transitions do not leak into ambient scope."""
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "x.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "root.py").write_text("VALUE = 2\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  verify:\n    runs-on: ubuntu-24.04\n    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - run: |\n"
        "          (cd tools && python x.py)\n"
        "          python root.py\n",
        encoding="utf-8",
    )
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    counted = {source.path for source in inventory.sources if source.counted}
    assert {"tools/x.py", "root.py"} <= counted
    assert not inventory.issues


def test_pushd_popd_stack_restores_scope(tmp_path: Path) -> None:
    """R3: statically provable pushd/popd stack transitions restore scope."""
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "x.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "root.py").write_text("VALUE = 2\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  verify:\n    runs-on: ubuntu-24.04\n    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - run: |\n"
        "          pushd tools\n"
        "          python x.py\n"
        "          popd\n"
        "          python root.py\n",
        encoding="utf-8",
    )
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    counted = {source.path for source in inventory.sources if source.counted}
    assert {"tools/x.py", "root.py"} <= counted
    assert not inventory.issues


def test_popd_without_pushd_fails_closed(tmp_path: Path) -> None:
    """R3: popd without a provable stack entry blocks attribution."""
    (tmp_path / "x.py").write_text("VALUE = 1\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  verify:\n    runs-on: ubuntu-24.04\n    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - run: |\n"
        "          popd\n"
        "          python x.py\n",
        encoding="utf-8",
    )
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    assert any("directory transition" in issue for issue in inventory.issues)
    assert not any(source.path == "x.py" and source.counted for source in inventory.sources)


def test_bare_cd_fails_closed(tmp_path: Path) -> None:
    """R3: bare cd targets HOME and is not statically resolvable."""
    (tmp_path / "x.py").write_text("VALUE = 1\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  verify:\n    runs-on: ubuntu-24.04\n    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - run: |\n"
        "          cd\n"
        "          python x.py\n",
        encoding="utf-8",
    )
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    assert any("directory transition" in issue for issue in inventory.issues)
    assert not any(source.path == "x.py" and source.counted for source in inventory.sources)


def test_cd_option_and_quoted_path_are_supported(tmp_path: Path) -> None:
    """R3: -P/-L options and quoted multiword targets resolve statically."""
    target = tmp_path / "my dir"
    target.mkdir()
    (target / "x.py").write_text("VALUE = 1\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  verify:\n    runs-on: ubuntu-24.04\n    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        '      - run: cd -P "my dir" && python x.py\n',
        encoding="utf-8",
    )
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    assert "my dir/x.py" in {source.path for source in inventory.sources if source.counted}
    assert not inventory.issues


def test_alternative_branch_after_transition_fails_closed(tmp_path: Path) -> None:
    """R3: || reachability after a directory transition is not statically provable."""
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "fallback.py").write_text("VALUE = 2\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  verify:\n    runs-on: ubuntu-24.04\n    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - run: cd tools || python fallback.py\n",
        encoding="utf-8",
    )
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    assert any("reachability" in issue or "directory transition" in issue for issue in inventory.issues)


def test_called_function_with_unresolvable_scope_fails_closed(tmp_path: Path) -> None:
    """R2: invoking a shell function whose scope effects cannot be proven fails closed."""
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "check.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "check.py").write_text("VALUE = 2\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  verify:\n    runs-on: ubuntu-24.04\n    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - run: |\n"
        "          helper() {\n"
        "              cd tools\n"
        "          }\n"
        "          helper\n"
        "          python check.py\n",
        encoding="utf-8",
    )
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    assert any("function" in issue for issue in inventory.issues)
    assert not any(source.path == "check.py" and source.counted for source in inventory.sources)


def test_quoted_commented_and_root_local_uses_resolve(tmp_path: Path) -> None:
    """R4: quoted, commented, and repository-root local action references resolve from YAML."""
    (tmp_path / "actions" / "build").mkdir(parents=True)
    (tmp_path / "actions" / "build" / "action.yml").write_text(
        "runs:\n  using: composite\n  steps:\n    - shell: bash\n      run: python build.py\n",
        encoding="utf-8",
    )
    (tmp_path / "action.yml").write_text(
        "runs:\n  using: composite\n  steps:\n    - shell: bash\n      run: python root_task.py\n",
        encoding="utf-8",
    )
    (tmp_path / "build.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "root_task.py").write_text("VALUE = 2\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  verify:\n    runs-on: ubuntu-24.04\n    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        '      - uses: "./actions/build"\n'
        "      - uses: ./actions/build # trailing comment\n"
        "      - uses: ./\n",
        encoding="utf-8",
    )
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    counted = {source.path for source in inventory.sources if source.counted}
    assert {"build.py", "root_task.py"} <= counted
    assert not inventory.issues


def test_run_block_uses_lookalike_is_not_an_action_reference(tmp_path: Path) -> None:
    """R4: textual uses: lookalikes inside run blocks are not action references."""
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "x.py").write_text("VALUE = 1\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  verify:\n    runs-on: ubuntu-24.04\n    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - run: |\n"
        "          cd tools\n"
        "          python x.py\n"
        "          echo 'uses: ./nonexistent'\n",
        encoding="utf-8",
    )
    inventory = classify_gate_sources(tmp_path, discover(tmp_path), limit=64)
    assert not any("composite action" in issue for issue in inventory.issues)
    assert "tools/x.py" in {source.path for source in inventory.sources if source.counted}


def test_scope_attribution_is_hash_seed_deterministic(tmp_path: Path) -> None:
    """R5: identical inventory and issues under different PYTHONHASHSEED values."""
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "a.py").write_text("import b\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("VALUE = 2\n", encoding="utf-8")
    workflow = tmp_path / ".github" / "workflows" / "ci.yml"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        "jobs:\n  verify:\n    runs-on: ubuntu-24.04\n    steps:\n"
        "      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567\n"
        "      - run: cd tools && python a.py; cd .. && python b.py; python c.py\n",
        encoding="utf-8",
    )
    runner = (
        "import json, sys\n"
        "sys.path.insert(0, 'skills/agents-md-architect/tools')\n"
        "from agents_md_gate_sources import classify_gate_sources\n"
        "from discover_repository import discover\n"
        "from pathlib import Path\n"
        "root = Path(sys.argv[1])\n"
        "inv = classify_gate_sources(root, discover(root), limit=64)\n"
        "print(json.dumps([[s.path, s.classification, s.counted] for s in inv.sources], sort_keys=True))\n"
        "print(json.dumps(sorted(inv.issues)))\n"
    )
    runner_script = tmp_path / "seed-runner.py"
    runner_script.write_text(runner, encoding="utf-8")
    outputs = []
    for seed in ("0", "7"):
        result = subprocess.run(
            [sys.executable, str(runner_script), str(tmp_path)],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
            check=True,
        )
        outputs.append(result.stdout)
    assert outputs[0] == outputs[1]
