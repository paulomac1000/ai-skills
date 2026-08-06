"""Regression tests for AFDS document schema v2 and controlled v1 migration."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def load_validator():
    path = ROOT / "skills/afds-doc-writer/validate.py"
    spec = importlib.util.spec_from_file_location("afds_v2_validator", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def messages(findings) -> list[str]:
    return [finding.message for finding in findings]


def document(
    *,
    schema: str = "afds_schema_version: 2\n",
    verification: str = "verification:\n  kind: command\n  value: Run `pytest`.\n",
    rigor: str = "normative",
) -> str:
    return f"""---
{schema}description: Test document
doc_id: reference.test-document
type: reference
status: active
rigor: {rigor}
owners: [maintainers]
{verification}---

# Test document
"""


def test_v2_accepts_each_typed_verification_kind(tmp_path: Path) -> None:
    validator = load_validator()
    for kind in ("command", "ci-job", "manual-review", "observable"):
        path = write(
            tmp_path / f"{kind}.md",
            document(
                verification=(
                    "verification:\n"
                    f"  kind: {kind}\n"
                    "  value: Concrete acceptance method.\n"
                )
            ),
        )
        assert validator.validate(path, tmp_path) == []


def test_v2_rejects_legacy_string_and_body_only_verification(tmp_path: Path) -> None:
    validator = load_validator()
    string_path = write(
        tmp_path / "string.md",
        document(verification="verification: Run tests.\n"),
    )
    assert "verification must be an object with exactly kind and value" in messages(
        validator.validate(string_path, tmp_path)
    )

    body_only = write(
        tmp_path / "body.md",
        document(verification="") + "\n## Verification\n\nRun tests.\n",
    )
    assert "missing typed verification metadata" in messages(
        validator.validate(body_only, tmp_path)
    )


def test_v2_rejects_unknown_kind_extra_fields_and_empty_value(tmp_path: Path) -> None:
    validator = load_validator()
    cases = {
        "kind.md": (
            "verification:\n  kind: magic\n  value: Test.\n",
            "verification.kind must be command, ci-job, manual-review, or observable",
        ),
        "extra.md": (
            "verification:\n  kind: command\n  value: Test.\n  result: passed\n",
            "verification must contain exactly kind and value",
        ),
        "empty.md": (
            "verification:\n  kind: command\n  value: ''\n",
            "verification.value must be a non-empty string",
        ),
    }
    for filename, (verification, expected) in cases.items():
        path = write(tmp_path / filename, document(verification=verification))
        assert expected in messages(validator.validate(path, tmp_path))


def test_v1_remains_readable_but_strict_migration_fails_closed(tmp_path: Path) -> None:
    validator = load_validator()
    path = write(
        tmp_path / "legacy.md",
        document(
            schema="",
            verification="verification: Run tests.\n",
        ),
    )
    assert validator.validate(path, tmp_path) == []
    strict = messages(
        validator.validate(
            path,
            tmp_path,
            minimum_schema_version=2,
        )
    )
    assert strict == [
        "afds_schema_version 1 is below required minimum 2; migrate verification "
        "to an object with kind and value"
    ]


def test_unknown_schema_and_singular_owner_are_deterministic_findings(
    tmp_path: Path,
) -> None:
    validator = load_validator()
    unknown = write(
        tmp_path / "unknown.md",
        document(schema="afds_schema_version: 99\n"),
    )
    assert "unsupported afds_schema_version: 99" in messages(
        validator.validate(unknown, tmp_path)
    )

    singular = write(
        tmp_path / "owner.md",
        document().replace("owners: [maintainers]\n", "owner: maintainers\n"),
    )
    result = messages(validator.validate(singular, tmp_path))
    assert 'unknown field "owner"; use "owners" as a non-empty list' in result
    assert "missing required fields: owners" in result


def test_informative_v2_may_omit_verification_but_validates_it_when_present(
    tmp_path: Path,
) -> None:
    validator = load_validator()
    omitted = write(
        tmp_path / "informative.md",
        document(rigor="informative", verification=""),
    )
    assert validator.validate(omitted, tmp_path) == []

    malformed = write(
        tmp_path / "malformed.md",
        document(rigor="informative", verification="verification: prose\n"),
    )
    assert "verification must be an object with exactly kind and value" in messages(
        validator.validate(malformed, tmp_path)
    )


def test_afds_v2_json_schema_is_valid_and_matches_template() -> None:
    schema_path = ROOT / "contracts/afds-frontmatter.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)

    template = (
        ROOT / "skills/afds-doc-writer/templates/governed-document.md.template"
    ).read_text(encoding="utf-8")
    assert "afds_schema_version: 2" in template
    assert "kind: <command|ci-job|manual-review|observable>" in template
    assert "value: <CONCRETE_VERIFICATION_METHOD>" in template


def test_afds_standard_documents_legacy_and_strict_modes() -> None:
    standard = (ROOT / "skills/afds-doc-writer/STANDARD.md").read_text(
        encoding="utf-8"
    )
    assert "contracts/afds-frontmatter.schema.json" in standard
    assert "--minimum-document-schema 2" in standard
    assert "A `## Verification` section" in standard
    assert "never substitutes for metadata" in standard
