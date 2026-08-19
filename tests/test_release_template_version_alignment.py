"""Consumer-facing templates stay aligned with published skill versions."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_mcp_consumer_templates_use_current_skill_version() -> None:
    manifest = yaml.safe_load(
        (ROOT / "skills/mcp-server-architect/manifest.yaml").read_text(encoding="utf-8")
    )
    version = manifest["version"]

    conformance = yaml.safe_load(
        (ROOT / "contracts/conformance-report.yaml.template").read_text(encoding="utf-8")
    )
    lock = yaml.safe_load(
        (ROOT / "contracts/ai-skills.lock.yaml.template").read_text(encoding="utf-8")
    )

    assert conformance["skill"]["name"] == "mcp-server-architect"
    assert conformance["skill"]["version"] == version
    assert lock["skills"]["mcp-server-architect"]["version"] == version


def test_generic_adoption_template_never_hardcodes_a_release_version() -> None:
    adoption = yaml.safe_load(
        (ROOT / "contracts/adoption-assessment.yaml.template").read_text(encoding="utf-8")
    )

    assert adoption["skill"]["version"] == "REPLACE_WITH_SKILL_VERSION"
