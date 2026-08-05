"""Regressions for structural command evidence and platform context budgets."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "skills/agents-md-architect/tools"
sys.path.insert(0, str(TOOLS))

import audit_agents_md as audit_module  # noqa: E402
import validate_agents_md as validator  # noqa: E402


def codes(findings: list[object]) -> set[str]:
    return {getattr(item, "code") for item in findings}


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def valid_application(extra: str = "") -> str:
    return f"""# AGENTS.md

## Scope

These instructions apply to the repository.

## Commands and verification

- Full gate: `python scripts/ci.py`

## Safety boundaries

Secrets must not be committed. Destructive writes require explicit authorization and rollback.

## Definition of done

Report the exact revision, skipped checks, and residual risk.
{extra}"""


def test_multiline_quoted_yaml_scalar_cannot_fabricate_run_node() -> None:
    text = '''name: CI
note: "first line
jobs:
  fake:
    steps:
      - run: python scripts/ghost.py
last line"
jobs:
  real:
    runs-on: ubuntu-latest
    steps:
      - run: echo real
'''
    commands = audit_module._extract_yaml_invocations(".github/workflows/ci.yml", text)
    assert "python scripts/ghost.py" not in commands
    assert "echo real" in commands


def test_yaml_indentation_indicators_preserve_executable_scalars() -> None:
    literal = '''jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: |2
          python scripts/ci.py
'''
    folded = '''jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: >-2
          python -m
          pytest
'''
    assert "python scripts/ci.py" in audit_module._extract_yaml_invocations(
        ".github/workflows/ci.yml", literal
    )
    assert "python -m pytest" in audit_module._extract_yaml_invocations(
        ".github/workflows/ci.yml", folded
    )


def test_quoted_shell_separators_do_not_create_phantom_commands() -> None:
    commands = audit_module._extract_shell_invocations(
        "echo '; python scripts/ghost.py ;' && python scripts/ci.py"
    )
    assert "python scripts/ghost.py" not in commands
    assert "python scripts/ci.py" in commands


def test_python_process_evidence_respects_lexical_scope() -> None:
    text = '''
class Fake:
    def run(self, *_args: object, **_kwargs: object) -> None:
        return None

subprocess = Fake()
subprocess.run(["python", "scripts/ghost.py"])

def real() -> None:
    import subprocess as sp
    sp.run(["python", "scripts/ci.py"], check=True)

def shadowed(subprocess: object) -> None:
    subprocess.run(["python", "scripts/shadowed.py"])
'''
    commands = audit_module._extract_python_invocations(text)
    assert "python scripts/ghost.py" not in commands
    assert "python scripts/shadowed.py" not in commands
    assert "python scripts/ci.py" in commands


def test_fenced_context_waiver_does_not_suppress_budget_warning(tmp_path: Path) -> None:
    padding = "x" * 13000
    path = write(
        tmp_path / "AGENTS.md",
        valid_application(
            f'''\n```markdown
<!-- agents-md: waive context-budget reason="This fenced example is not active policy." -->
```

{padding}
'''
        ),
    )
    findings = validator.validate_path(path, "application", tmp_path)
    assert "context.review-budget" in codes(findings)


def test_exactly_one_active_reasoned_waiver_suppresses_budget_warning(tmp_path: Path) -> None:
    padding = "x" * 13000
    path = write(
        tmp_path / "AGENTS.md",
        valid_application(
            f'''\n<!-- agents-md: waive context-budget reason="The generated command matrix is intentionally reviewed here." -->

{padding}
'''
        ),
    )
    findings = validator.validate_path(path, "application", tmp_path)
    assert "context.review-budget" not in codes(findings)
    assert "context.invalid-waiver" not in codes(findings)


def test_multiple_active_waivers_are_invalid_and_do_not_suppress_budget(tmp_path: Path) -> None:
    padding = "x" * 13000
    path = write(
        tmp_path / "AGENTS.md",
        valid_application(
            f'''\n<!-- agents-md: waive context-budget reason="First reason is intentionally long enough for review." -->
<!-- agents-md: waive context-budget reason="Second reason is intentionally long enough for review." -->

{padding}
'''
        ),
    )
    findings = validator.validate_path(path, "application", tmp_path)
    assert "context.invalid-waiver" in codes(findings)
    assert "context.review-budget" in codes(findings)


def test_codex_effective_root_to_leaf_chain_enforces_default_budget(tmp_path: Path) -> None:
    write(tmp_path / "AGENTS.md", "r" * 17000)
    write(tmp_path / "packages/AGENTS.md", "n" * 17000)
    findings = validator._validate_codex_context(
        tmp_path, (), validator.CODEX_DEFAULT_PROJECT_DOC_MAX_BYTES
    )
    assert "platform.codex-context-budget" in codes(findings)


def test_codex_override_replaces_same_directory_agents_file(tmp_path: Path) -> None:
    write(tmp_path / "AGENTS.md", "ignored" * 1000)
    write(tmp_path / "AGENTS.override.md", "root override")
    write(tmp_path / "packages/AGENTS.md", "nested")
    findings = validator._validate_codex_context(tmp_path, (), 100)
    assert "platform.codex-context-budget" not in codes(findings)


def test_codex_configured_fallback_participates_in_effective_chain(tmp_path: Path) -> None:
    write(tmp_path / "AGENTS.md", "root")
    write(tmp_path / "packages/PROJECT_GUIDE.md", "nested fallback content")
    findings = validator._validate_codex_context(tmp_path, ("PROJECT_GUIDE.md",), 20)
    assert "platform.codex-context-budget" in codes(findings)
