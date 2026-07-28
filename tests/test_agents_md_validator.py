"""Contract tests for the AGENTS.md instruction validator."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = ROOT / "skills/agents-md-architect/tools/validate_agents_md.py"


def load_validator() -> Any:
    spec = importlib.util.spec_from_file_location("agents_md_validator", VALIDATOR_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def validator() -> Any:
    return load_validator()


def codes(findings: list[Any]) -> set[str]:
    return {item.code for item in findings}


def prepare_refs(root: Path) -> None:
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs/architecture.md").write_text("# Architecture\n", encoding="utf-8")
    (root / "scripts").mkdir(exist_ok=True)
    (root / "scripts/ci.py").write_text("print('ok')\n", encoding="utf-8")


def application_text() -> str:
    return """# AGENTS.md

## Scope

These instructions apply to the repository. A read-only audit does not permit implementation.

## Commands and verification

- Focused check: `python -m pytest tests/test_service.py`
- Full gate: `python scripts/ci.py`

## Architecture boundaries

When changing service boundaries, read [the architecture guide](docs/architecture.md) for dependency ownership.

## Definition of done

Report focused and full checks, the exact revision, skipped checks, and residual risk.
"""


def router_text() -> str:
    return """# AGENTS.md

## Scope

These instructions apply to the repository.

## Task routing

When changing architecture, read [the architecture guide](docs/architecture.md) for dependency ownership.

## Definition of done

Report the exact revision and unresolved risks before completion.
"""


def mcp_text() -> str:
    return """# AGENTS.md

## Scope

These instructions apply to the MCP server.

## Commands and verification

- Focused check: `python -m pytest tests/test_mcp.py`
- Full gate: `python scripts/ci.py`

## Safety and risk

Read-only diagnosis is the default. Write operations require trusted approval, and destructive side effects are forbidden without confirmation.

## Definition of done

Report the exact revision, protocol checks, and residual risk before completion.
"""


def safety_text() -> str:
    return """# AGENTS.md

## Scope

These instructions apply to the safety-critical service.

## Commands and verification

- Focused check: `python -m pytest tests/test_safety.py`
- Full gate: `python scripts/ci.py`

## Safety and data boundaries

Secrets and sensitive data must not be committed. Destructive operations require trusted approval and rollback evidence.

## Definition of done

Report the exact revision, protected-data checks, and residual risk before completion.
"""


def monorepo_root_text() -> str:
    return """# AGENTS.md

## Scope and precedence

These instructions apply to the repository. Nested AGENTS.md files define inherited subtree differences.

## Commands and verification

- Focused check: `python -m pytest tests/test_root.py`
- Full gate: `python scripts/ci.py`

## Architecture boundaries

Generated files must not be edited directly.

## Definition of done

Report root and nested completion checks, the exact revision, and residual risk.
"""


def monorepo_nested_text() -> str:
    return """# Local agent instructions

## Scope and local differences

These instructions apply only to this subtree. Use the package-specific build graph.

## Local commands and completion

- Local focused check: `python -m pytest packages/example/tests`
- Local completion check: `python packages/example/scripts/ci.py`

## Local references

When changing package architecture, read [the local guide](docs/local.md) for package ownership.
"""


def write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("profile", "text"),
    [
        ("router", router_text()),
        ("application", application_text()),
        ("mcp-server", mcp_text()),
        ("safety-critical", safety_text()),
    ],
)
def test_positive_single_file_profiles_pass(tmp_path: Path, validator: Any, profile: str, text: str) -> None:
    prepare_refs(tmp_path)
    path = write(tmp_path, "AGENTS.md", text)
    assert validator.validate_path(path, profile, tmp_path) == []
    assert validator.main(["--profile", profile, "--repository-root", str(tmp_path), str(path)]) == 0


def test_positive_monorepo_tree_passes(tmp_path: Path, validator: Any) -> None:
    prepare_refs(tmp_path)
    root = write(tmp_path, "AGENTS.md", monorepo_root_text())
    nested = write(tmp_path, "packages/example/AGENTS.md", monorepo_nested_text())
    write(tmp_path, "packages/example/docs/local.md", "# Local\n")
    write(tmp_path, "packages/example/scripts/ci.py", "print('ok')\n")
    assert validator.validate_many([root, nested], "monorepo", tmp_path) == []
    assert (
        validator.main(
            [
                "--profile",
                "monorepo",
                "--repository-root",
                str(tmp_path),
                str(root),
                str(nested),
            ]
        )
        == 0
    )


def test_missing_profile_contracts_fail(tmp_path: Path, validator: Any) -> None:
    path = write(tmp_path, "AGENTS.md", "# AGENTS.md\n\nUse this repository.\n")
    result = validator.validate_path(path, "application", tmp_path)
    assert {"profile.missing-commands", "profile.missing-completion"} <= codes(result)


def test_template_style_code_span_path_is_validated(tmp_path: Path, validator: Any) -> None:
    prepare_refs(tmp_path)
    text = application_text().replace(
        "[the architecture guide](docs/architecture.md)", "`docs/does-not-exist.md`"
    )
    path = write(tmp_path, "AGENTS.md", text)
    assert "links.missing" in codes(validator.validate_path(path, "application", tmp_path))


def test_reference_definition_inside_fence_is_ignored(tmp_path: Path, validator: Any) -> None:
    prepare_refs(tmp_path)
    text = application_text() + """

```markdown
[ghost]: docs/ghost.md
```

This explanatory sentence mentions [ghost][ghost] but does not create an active definition.
"""
    path = write(tmp_path, "AGENTS.md", text)
    assert "links.missing" not in codes(validator.validate_path(path, "application", tmp_path))


def test_unclosed_fence_is_rejected(tmp_path: Path, validator: Any) -> None:
    prepare_refs(tmp_path)
    path = write(tmp_path, "AGENTS.md", application_text() + "\n```markdown\nHidden remainder\n")
    assert "structure.unclosed-fence" in codes(validator.validate_path(path, "application", tmp_path))


def test_blockquoted_fence_content_is_ignored(tmp_path: Path, validator: Any) -> None:
    prepare_refs(tmp_path)
    text = application_text() + """

> ```markdown
> CONSENT_KEYWORDS = ["approve"]
> [Missing](docs/missing.md)
> ```
"""
    path = write(tmp_path, "AGENTS.md", text)
    result = validator.validate_path(path, "application", tmp_path)
    assert "safety.keyword-approval" not in codes(result)
    assert "links.missing" not in codes(result)


def test_negated_bad_practices_are_not_flagged(tmp_path: Path, validator: Any) -> None:
    prepare_refs(tmp_path)
    text = application_text() + """

Do not use keyword-based approval; it is not proof of human approval.
If the local hook passes, CI is not guaranteed to pass.
"""
    path = write(tmp_path, "AGENTS.md", text)
    result = validator.validate_path(path, "application", tmp_path)
    assert "safety.keyword-approval" not in codes(result)
    assert "evidence.false-ci-guarantee" not in codes(result)


def test_positive_bad_practices_are_rejected(tmp_path: Path, validator: Any) -> None:
    prepare_refs(tmp_path)
    text = application_text() + """

CONSENT_KEYWORDS decide whether a change is approved.
If the local pre-commit hook passes, CI is guaranteed to pass.
"""
    path = write(tmp_path, "AGENTS.md", text)
    result = validator.validate_path(path, "application", tmp_path)
    assert {"safety.keyword-approval", "evidence.false-ci-guarantee"} <= codes(result)


def test_input_outside_repository_is_rejected_before_read(tmp_path: Path, validator: Any) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    outside = write(tmp_path, "outside/AGENTS.md", application_text())
    result = validator.validate_path(outside, "application", root)
    assert codes(result) == {"input.outside-repository"}


@pytest.mark.skipif(os.name == "nt", reason="symlink privileges vary on Windows")
def test_repository_root_with_symlink_component_is_rejected(tmp_path: Path, validator: Any) -> None:
    real = tmp_path / "real"
    real.mkdir()
    write(real, "AGENTS.md", application_text())
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    result = validator.validate_path(alias / "AGENTS.md", "application", alias)
    assert "input.repository-root-symlink" in codes(result)


@pytest.mark.skipif(os.name == "nt", reason="symlink privileges vary on Windows")
def test_input_symlink_is_rejected(tmp_path: Path, validator: Any) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    outside = write(tmp_path, "outside/AGENTS.md", application_text())
    link = root / "AGENTS.md"
    link.symlink_to(outside)
    assert codes(validator.validate_path(link, "application", root)) == {"input.symlink"}


@pytest.mark.skipif(os.name == "nt", reason="symlink privileges vary on Windows")
def test_reference_symlink_is_rejected(tmp_path: Path, validator: Any) -> None:
    prepare_refs(tmp_path)
    outside = write(tmp_path.parent, "outside-reference.md", "# Outside\n")
    (tmp_path / "docs/link.md").symlink_to(outside)
    text = application_text().replace("docs/architecture.md", "docs/link.md")
    path = write(tmp_path, "AGENTS.md", text)
    assert "links.symlink" in codes(validator.validate_path(path, "application", tmp_path))


def test_context_budget_warns_and_reasoned_waiver_suppresses(tmp_path: Path, validator: Any) -> None:
    prepare_refs(tmp_path)
    path = write(tmp_path, "AGENTS.md", application_text() + "\n".join("Extra guidance." for _ in range(130)))
    assert "context.review-budget" in codes(validator.validate_path(path, "application", tmp_path))
    waived = (
        '<!-- agents-md: waive context-budget '
        'reason="Safety boundary must remain visible during emergency response." -->\n'
    )
    path.write_text(waived + path.read_text(encoding="utf-8"), encoding="utf-8")
    assert "context.review-budget" not in codes(validator.validate_path(path, "application", tmp_path))


def test_short_context_waiver_is_rejected(tmp_path: Path, validator: Any) -> None:
    prepare_refs(tmp_path)
    path = write(
        tmp_path,
        "AGENTS.md",
        '<!-- agents-md: waive context-budget reason="too long" -->\n' + application_text(),
    )
    assert "context.invalid-waiver" in codes(validator.validate_path(path, "application", tmp_path))


def test_monorepo_detects_conflicting_generated_file_rule(tmp_path: Path, validator: Any) -> None:
    prepare_refs(tmp_path)
    root = write(tmp_path, "AGENTS.md", monorepo_root_text())
    nested_text = monorepo_nested_text() + "\nGenerated files must be edited directly.\n"
    nested = write(tmp_path, "packages/example/AGENTS.md", nested_text)
    write(tmp_path, "packages/example/docs/local.md", "# Local\n")
    write(tmp_path, "packages/example/scripts/ci.py", "print('ok')\n")
    assert "tree.conflicting-rule" in codes(validator.validate_many([root, nested], "monorepo", tmp_path))


def test_monorepo_detects_conflicting_command(tmp_path: Path, validator: Any) -> None:
    prepare_refs(tmp_path)
    root = write(tmp_path, "AGENTS.md", monorepo_root_text())
    nested_text = monorepo_nested_text().replace("## Local commands and completion", "## Commands and completion")
    nested_text = nested_text.replace(
        "- Local focused check: `python -m pytest packages/example/tests`",
        "- Focused check: `python -m pytest packages/other/tests`",
    )
    nested = write(tmp_path, "packages/example/AGENTS.md", nested_text)
    write(tmp_path, "packages/example/docs/local.md", "# Local\n")
    write(tmp_path, "packages/example/scripts/ci.py", "print('ok')\n")
    assert "tree.conflicting-command" in codes(validator.validate_many([root, nested], "monorepo", tmp_path))


def test_monorepo_detects_conflicting_owner(tmp_path: Path, validator: Any) -> None:
    prepare_refs(tmp_path)
    write(tmp_path, "docs/root-standard.md", "# Root\n")
    write(tmp_path, "packages/example/docs/local-standard.md", "# Local\n")
    root_text = monorepo_root_text() + """

## Sources of truth

- [Normative contract](docs/root-standard.md) — accepted behavior.
"""
    nested_text = monorepo_nested_text() + """

## Sources of truth

- [Normative contract](docs/local-standard.md) — accepted behavior.
"""
    root = write(tmp_path, "AGENTS.md", root_text)
    nested = write(tmp_path, "packages/example/AGENTS.md", nested_text)
    write(tmp_path, "packages/example/docs/local.md", "# Local\n")
    write(tmp_path, "packages/example/scripts/ci.py", "print('ok')\n")
    result = validator.validate_many([root, nested], "monorepo", tmp_path)
    assert "tree.conflicting-owner" in codes(result)


def test_monorepo_detects_duplicated_section_and_empty_local_file(tmp_path: Path, validator: Any) -> None:
    prepare_refs(tmp_path)
    root_text = monorepo_root_text()
    root = write(tmp_path, "AGENTS.md", root_text)
    nested = write(tmp_path, "packages/example/AGENTS.md", root_text)
    result = validator.validate_many([root, nested], "monorepo", tmp_path)
    assert {"tree.duplicated-section", "tree.no-local-difference"} <= codes(result)


def test_strict_cli_fails_on_warning_and_json_is_machine_readable(
    tmp_path: Path, validator: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    prepare_refs(tmp_path)
    text = application_text() + "\n- [Architecture](docs/architecture.md)\n"
    path = write(tmp_path, "AGENTS.md", text)
    assert validator.main(["--strict", "--repository-root", str(tmp_path), str(path)]) == 1
    assert "routing.blind-reference" in capsys.readouterr().out
    assert validator.main(["--format", "json", "--repository-root", str(tmp_path), str(path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert any(item["code"] == "routing.blind-reference" for item in payload)
