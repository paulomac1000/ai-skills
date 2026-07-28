"""Contract tests for the AGENTS.md instruction validator."""

from __future__ import annotations

import importlib.util
import json
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


def write_valid_application(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/architecture.md").write_text("# Architecture\n", encoding="utf-8")
    path = tmp_path / "AGENTS.md"
    path.write_text(
        """# AGENTS.md

These instructions apply to the repository.

## Scope

Maintain the service without expanding a read-only audit into implementation.

## Commands and verification

- Focused test: `python -m pytest tests/test_service.py`
- Full gate: `python scripts/ci.py`

## Architecture boundaries

When changing service boundaries, read [the architecture guide](docs/architecture.md) for dependency ownership.

## Definition of done

Report focused and full checks, the exact revision, skipped checks, and residual risk.
""",
        encoding="utf-8",
    )
    return path


def codes(findings: list[Any]) -> set[str]:
    return {item.code for item in findings}


def test_valid_application_profile_passes(tmp_path: Path, validator: Any) -> None:
    path = write_valid_application(tmp_path)
    assert validator.validate_path(path, "application", tmp_path) == []


def test_missing_profile_contracts_fail(tmp_path: Path, validator: Any) -> None:
    path = tmp_path / "AGENTS.md"
    path.write_text("# AGENTS.md\n\nUse this repository.\n", encoding="utf-8")
    result = validator.validate_path(path, "application", tmp_path)
    assert {"profile.missing-commands", "profile.missing-completion"} <= codes(result)


def test_safety_profile_requires_explicit_data_boundary(tmp_path: Path, validator: Any) -> None:
    path = write_valid_application(tmp_path)
    result = validator.validate_path(path, "safety-critical", tmp_path)
    assert {"profile.missing-safety", "profile.missing-data"} <= codes(result)


def test_monorepo_profile_requires_precedence_and_nested_contract(tmp_path: Path, validator: Any) -> None:
    path = write_valid_application(tmp_path)
    result = validator.validate_path(path, "monorepo", tmp_path)
    assert {"profile.missing-precedence", "profile.missing-nested"} <= codes(result)


def test_duplicate_headings_and_changelog_are_rejected(tmp_path: Path, validator: Any) -> None:
    path = write_valid_application(tmp_path)
    text = path.read_text(encoding="utf-8") + "\n## Scope\n\nDuplicate.\n\n## Changelog\n\nHistory.\n"
    path.write_text(text, encoding="utf-8")
    result = validator.validate_path(path, "application", tmp_path)
    assert {"structure.duplicate-heading", "content.changelog"} <= codes(result)


def test_fenced_examples_do_not_create_headings_or_smells(tmp_path: Path, validator: Any) -> None:
    path = write_valid_application(tmp_path)
    text = path.read_text(encoding="utf-8") + """

```markdown
## Scope
- [Blind](missing.md)
CONSENT_KEYWORDS = ["approve"]
```
"""
    path.write_text(text, encoding="utf-8")
    assert validator.validate_path(path, "application", tmp_path) == []


def test_missing_and_escaping_links_fail(tmp_path: Path, validator: Any) -> None:
    path = write_valid_application(tmp_path)
    text = path.read_text(encoding="utf-8")
    text += "\n- When changing release logic, read [missing](docs/missing.md) for release ownership.\n"
    text += "- When changing external policy, read [outside](../outside.md) for authority.\n"
    path.write_text(text, encoding="utf-8")
    result = validator.validate_path(path, "application", tmp_path)
    assert {"links.missing", "links.outside-repository"} <= codes(result)


def test_blind_reference_is_warning(tmp_path: Path, validator: Any) -> None:
    path = write_valid_application(tmp_path)
    text = path.read_text(encoding="utf-8") + "\n- [Architecture](docs/architecture.md)\n"
    path.write_text(text, encoding="utf-8")
    result = validator.validate_path(path, "application", tmp_path)
    finding = next(item for item in result if item.code == "routing.blind-reference")
    assert finding.severity == "warning"


def test_keyword_approval_and_false_ci_guarantee_are_errors(tmp_path: Path, validator: Any) -> None:
    path = write_valid_application(tmp_path)
    text = path.read_text(encoding="utf-8")
    text += "\nCONSENT_KEYWORDS decide whether a change is approved.\n"
    text += "If the local pre-commit hook passes, CI is guaranteed to pass.\n"
    path.write_text(text, encoding="utf-8")
    result = validator.validate_path(path, "application", tmp_path)
    assert {"safety.keyword-approval", "evidence.false-ci-guarantee"} <= codes(result)


def test_versioned_names_counts_paths_and_generic_advice_warn(tmp_path: Path, validator: Any) -> None:
    path = write_valid_application(tmp_path)
    text = path.read_text(encoding="utf-8")
    text += "\nUse implementation-v7 from /var/apps/example and keep 322 tests. Follow best practices.\n"
    path.write_text(text, encoding="utf-8")
    result = validator.validate_path(path, "application", tmp_path)
    assert {
        "ownership.versioned-current-name",
        "portability.absolute-host-path",
        "content.volatile-count",
        "content.generic-advice",
    } <= codes(result)


def test_placeholders_are_rejected(tmp_path: Path, validator: Any) -> None:
    path = write_valid_application(tmp_path)
    path.write_text(path.read_text(encoding="utf-8") + "\nREPLACE_WITH_COMMAND\n", encoding="utf-8")
    assert "content.placeholder" in codes(validator.validate_path(path, "application", tmp_path))


def test_strict_mode_fails_on_warnings(tmp_path: Path, validator: Any, capsys: pytest.CaptureFixture[str]) -> None:
    path = write_valid_application(tmp_path)
    path.write_text(path.read_text(encoding="utf-8") + "\n- [Architecture](docs/architecture.md)\n", encoding="utf-8")
    assert validator.main(["--strict", "--repository-root", str(tmp_path), str(path)]) == 1
    assert "routing.blind-reference" in capsys.readouterr().out


def test_json_output_is_machine_readable(tmp_path: Path, validator: Any, capsys: pytest.CaptureFixture[str]) -> None:
    path = write_valid_application(tmp_path)
    path.write_text(path.read_text(encoding="utf-8") + "\nREPLACE_WITH_COMMAND\n", encoding="utf-8")
    assert validator.main(["--format", "json", "--repository-root", str(tmp_path), str(path)]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["path"] == str(path)
    assert any(item["code"] == "content.placeholder" for item in payload)


def test_context_limits_warn_then_fail(tmp_path: Path, validator: Any) -> None:
    path = write_valid_application(tmp_path)
    base = path.read_text(encoding="utf-8")
    path.write_text(base + "\n".join("Extra guidance." for _ in range(130)), encoding="utf-8")
    assert "context.review-limit" in codes(validator.validate_path(path, "application", tmp_path))
    path.write_text(base + "\n".join("Extra guidance." for _ in range(190)), encoding="utf-8")
    assert "context.hard-limit" in codes(validator.validate_path(path, "application", tmp_path))
