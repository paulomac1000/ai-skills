from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

TOOLS = Path(__file__).resolve().parents[1] / "skills/agents-md-architect/tools"
sys.path.insert(0, str(TOOLS))

import audit_agents_md as audit_module  # noqa: E402
import discover_repository as discovery  # noqa: E402
import validate_agents_md as validator  # noqa: E402


def codes(items: list[Any]) -> set[str]:
    return {item.code for item in items}


def write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def root_text(*, safety: bool = True, polish: bool = False) -> str:
    if polish:
        return """# AGENTS.md

## Zakres i dziedziczenie
<!-- agents-md: contract scope -->
<!-- agents-md: contract precedence -->
<!-- agents-md: contract nested -->
Te instrukcje dotyczą repozytorium. Zagnieżdżone pliki definiują lokalne różnice.

## Komendy i weryfikacja
<!-- agents-md: contract commands -->
- Pełna bramka: `python scripts/ci.py`

## Bezpieczeństwo i dane
<!-- agents-md: contract safety -->
<!-- agents-md: contract data -->
Nie wolno edytować wygenerowanych plików. Dane wrażliwe muszą pozostać poza repozytorium.

## Definicja ukończenia
<!-- agents-md: contract completion -->
Raportuj dokładną rewizję i ryzyko.
"""
    safety_block = (
        """
## Safety and data
<!-- agents-md: contract safety -->
<!-- agents-md: contract data -->
Generated files must not be edited directly. Sensitive data must remain outside the repository.
"""
        if safety
        else ""
    )
    return f"""# AGENTS.md

## Scope and precedence
<!-- agents-md: contract scope -->
<!-- agents-md: contract precedence -->
<!-- agents-md: contract nested -->
These instructions apply to the repository. Nested AGENTS.md files define local differences.

## Commands
<!-- agents-md: contract commands -->
- Full gate: `python scripts/ci.py`
{safety_block}
## Definition of done
<!-- agents-md: contract completion -->
Report the exact revision and residual risk.
"""


def nested_text(*, safety: bool = True, polish: bool = False, conflict: bool = False) -> str:
    if polish:
        conflict_line = (
            "Wygenerowane pliki należy edytować bezpośrednio."
            if conflict
            else "Nie wolno edytować wygenerowanych plików."
        )
        return f"""# Lokalne instrukcje

## Zakres i lokalne różnice
<!-- agents-md: contract scope -->
<!-- agents-md: contract local -->
Te instrukcje dotyczą tylko tego poddrzewa.

## Lokalne komendy
<!-- agents-md: contract commands -->
- Lokalna bramka: `python packages/api/scripts/ci.py`

## Bezpieczeństwo i dane
<!-- agents-md: contract safety -->
<!-- agents-md: contract data -->
{conflict_line} Dane osobowe nie mogą być zapisywane w repozytorium.

## Ukończenie
<!-- agents-md: contract completion -->
Raportuj lokalne testy.
"""
    safety_block = (
        """
## Local safety and data
<!-- agents-md: contract safety -->
<!-- agents-md: contract data -->
Generated files must not be edited directly. Sensitive data must remain outside the repository.
"""
        if safety
        else ""
    )
    return f"""# Local instructions

## Scope and local differences
<!-- agents-md: contract scope -->
<!-- agents-md: contract local -->
These instructions apply only to this subtree.

## Local commands
<!-- agents-md: contract commands -->
- Local gate: `python packages/api/scripts/ci.py`
{safety_block}
## Completion
<!-- agents-md: contract completion -->
Report local checks.
"""


def prepare(root: Path):
    write(root, "scripts/ci.py", "print('ok')\n")
    write(root, "packages/api/scripts/ci.py", "print('ok')\n")


def test_language_contract_and_compositional_cli_are_published() -> None:
    skill_root = Path(__file__).resolve().parents[1] / "skills/agents-md-architect"
    manifest = yaml.safe_load((skill_root / "manifest.yaml").read_text(encoding="utf-8"))
    language_reference = "references/language-and-contract-markers.md"
    assert language_reference in manifest["required"]
    skill = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    assert "--layout <layout> --profile <profile> --language <language>" in skill


@pytest.mark.parametrize("profile,safety", [("application", True), ("mcp-server", True), ("safety-critical", True)])
def test_monorepo_composes_layout_and_domain(tmp_path: Path, profile: str, safety: bool):
    prepare(tmp_path)
    root = write(tmp_path, "AGENTS.md", root_text(safety=safety))
    nested = write(tmp_path, "packages/api/AGENTS.md", nested_text(safety=safety))
    language = "en"
    if profile == "mcp-server":
        for path in (root, nested):
            text = path.read_text(encoding="utf-8")
            text = text.replace("<!-- agents-md: contract data -->", "<!-- agents-md: contract risk -->")
            path.write_text(text, encoding="utf-8")
        language = "other"
    assert validator.validate_many([root, nested], profile, tmp_path, "monorepo", language) == []


def test_polish_safety_monorepo_passes(tmp_path: Path) -> None:
    prepare(tmp_path)
    root = write(tmp_path, "AGENTS.md", root_text(polish=True))
    nested = write(tmp_path, "packages/api/AGENTS.md", nested_text(polish=True))
    assert validator.validate_many([root, nested], "safety-critical", tmp_path, "monorepo", "pl") == []


def test_polish_monorepo_conflict_is_detected(tmp_path: Path) -> None:
    prepare(tmp_path)
    root = write(tmp_path, "AGENTS.md", root_text(polish=True))
    nested = write(tmp_path, "packages/api/AGENTS.md", nested_text(polish=True, conflict=True))
    result = validator.validate_many([root, nested], "safety-critical", tmp_path, "monorepo", "pl")
    assert "tree.conflicting-rule" in codes(result)


def test_other_language_requires_markers_in_strict_mode(tmp_path: Path) -> None:
    path = write(tmp_path, "AGENTS.md", "# AGENTS.md\n\nArbitrary language text.\n")
    result = validator.validate_path(path, "application", tmp_path, "single", "other")
    assert "language.semantic-unverified" in codes(result)
    assert (
        validator.main(
            [
                "--profile",
                "application",
                "--language",
                "other",
                "--strict",
                "--repository-root",
                str(tmp_path),
                str(path),
            ]
        )
        == 1
    )


def test_directory_reference_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    path = write(
        tmp_path,
        "AGENTS.md",
        """# AGENTS.md

<!-- agents-md: contract scope -->
<!-- agents-md: contract commands -->
<!-- agents-md: contract completion -->
## Scope
These instructions apply.
## Commands
- Full gate: `python scripts/ci.py`
## Definition of done
Read `docs/` for architecture.
""",
    )
    assert "links.not-file" in codes(validator.validate_path(path, "application", tmp_path))


def test_invalid_utf8_and_size_are_findings(tmp_path: Path) -> None:
    invalid = tmp_path / "AGENTS.md"
    invalid.write_bytes(b"# AGENTS.md\n\xff")
    assert codes(validator.validate_path(invalid, "application", tmp_path)) == {"input.invalid-utf8"}
    invalid.write_bytes(b"x" * (256 * 1024 + 1))
    assert codes(validator.validate_path(invalid, "application", tmp_path)) == {"input.too-large"}


def test_instruction_tree_limits_fail_closed(tmp_path: Path) -> None:
    paths: list[Path] = []
    payload = "# AGENTS.md\n" + ("x" * 240_000)
    for index in range(9):
        paths.append(write(tmp_path, f"packages/p{index}/AGENTS.md", payload))
    assert "input.tree-too-large" in codes(validator.validate_many(paths, "application", tmp_path, "monorepo", "en"))


def test_all_replace_tokens_are_placeholders(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        "AGENTS.md",
        """# AGENTS.md

<!-- agents-md: contract scope -->
<!-- agents-md: contract commands -->
<!-- agents-md: contract completion -->
## Scope
These instructions apply.
## Commands
- Full gate: `python scripts/ci.py`
## Definition of done
REPLACE_OR_REMOVE_WITH_OTHER_REAL_MODE
""",
    )
    assert "content.placeholder" in codes(validator.validate_path(path, "application", tmp_path))


def test_audit_and_validator_share_blockquote_fence_visibility(tmp_path: Path) -> None:
    prepare(tmp_path)
    text = (
        root_text()
        + """
> ```markdown
> CONSENT_KEYWORDS = ["approve"]
> - Full gate: `python missing.py`
> ```
"""
    )
    path = write(tmp_path, "AGENTS.md", text)
    validation = validator.validate_path(path, "application", tmp_path, "monorepo", "en")
    _, audited = audit_module.audit(tmp_path, "application", "monorepo", "en")
    assert "safety.keyword-approval" not in codes(validation)
    assert "safety.keyword-approval" not in codes(audited)
    assert "commands.unlocated-full-gate" not in codes(audited)


def test_existing_arbitrary_path_is_unverified_not_executed(tmp_path: Path) -> None:
    prepare(tmp_path)
    write(tmp_path, "scripts/helper.py", "print('helper')\n")
    write(tmp_path, "AGENTS.md", root_text().replace("python scripts/ci.py", "python scripts/helper.py --dangerous"))
    _, findings = audit_module.audit(tmp_path, "application", "monorepo", "en")
    assert "commands.unverified-full-gate" in codes(findings)


def test_bin_scripts_and_rust_entrypoints_are_discovered_but_dotnet_outputs_are_ignored(tmp_path: Path) -> None:
    write(tmp_path, "bin/ci", "#!/bin/sh\n")
    write(tmp_path, "bin/setup", "#!/bin/sh\n")
    write(tmp_path, "Cargo.toml", "[package]\nname='x'\n")
    write(tmp_path, "src/bin/tool.rs", "fn main() {}\n")
    write(tmp_path, "Root.csproj", "<Project />\n")
    write(tmp_path, "src/App/App.csproj", "<Project />\n")
    write(tmp_path, "src/App/bin/Debug/app.dll", "binary\n")
    result = discovery.discover(tmp_path)
    assert "bin/ci" in result.files
    assert "bin/setup" in result.files
    assert "src/bin/tool.rs" in result.files
    assert "bin/ci" in result.task_runners
    assert all(not item.startswith("src/App/bin/") for item in result.files)
