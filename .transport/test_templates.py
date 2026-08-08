from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _render_publish() -> str:
    template = (ROOT / "skills/ci-cd-architect/templates/publish.yml.template").read_text(encoding="utf-8")
    replacements = {
        "<DEFAULT_BRANCH>": "main",
        "<BUILD_COMMAND>": "echo build",
        "<TEST_COMMAND>": "echo test",
        "<CONTAINER_SMOKE_COMMAND>": "echo smoke $IMAGE_REF",
        "<QUARANTINE_REGISTRY>": "quarantine.example.invalid",
        "<QUARANTINE_REPOSITORY>": "owner/repo",
        "<QUARANTINE_USERNAME_SECRET>": "QUARANTINE_USERNAME",
        "<QUARANTINE_PASSWORD_SECRET>": "QUARANTINE_PASSWORD",
        "<QUARANTINE_READ_USERNAME_SECRET>": "QUARANTINE_READ_USERNAME",
        "<QUARANTINE_READ_PASSWORD_SECRET>": "QUARANTINE_READ_PASSWORD",
        "<PROTECTED_ENVIRONMENT>": "production",
    }
    for source, target in replacements.items():
        template = template.replace(source, target)
    return template


def test_publish_template_uses_quarantine_digest_promotion() -> None:
    rendered = _render_publish()
    parsed = yaml.safe_load(rendered)
    assert parsed["jobs"]["validate-build"]["permissions"] == {"contents": "read"}
    publish = parsed["jobs"]["publish"]
    assert publish["environment"] == "production"
    assert publish["permissions"]["packages"] == "write"
    assert "docker buildx imagetools create" in rendered
    assert "quarantine" in rendered.lower()
    assert "docker image load" not in rendered
    assert "image.tar" not in rendered
    assert "docker push --all-tags" not in rendered


def test_publish_template_smokes_exact_quarantine_digest() -> None:
    rendered = _render_publish()
    assert "QUARANTINE_DIGEST" in rendered
    assert 'IMAGE_REF="${QUARANTINE_REF%:*}@$QUARANTINE_DIGEST"' in rendered
    assert "test \"$promoted\" = \"$EXPECTED_DIGEST\"" in rendered


def test_publish_template_has_immutable_action_pins() -> None:
    rendered = _render_publish()
    for reference in re.findall(r"uses:\s*([^\s#]+)", rendered):
        assert reference.startswith("./") or re.search(r"@[0-9a-f]{40}$", reference), reference


def test_trusted_audit_template_does_not_execute_candidate_auditor() -> None:
    template = (ROOT / "skills/ci-cd-architect/templates/trusted-workflow-audit.yml.template").read_text(
        encoding="utf-8"
    )
    assert "path: candidate" in template
    assert "path: verifier" in template
    assert "python verifier/" in template
    assert "python candidate/" not in template


def test_migration_template_uses_full_release_version() -> None:
    template = yaml.safe_load(
        (ROOT / "skills/mcp-server-architect/templates/migration-assessment.yaml.template").read_text(encoding="utf-8")
    )
    assert template["skill"]["version"] == "2.0.0"
    assert template["skill"]["maturity"] == "stable"
