"""Consumer-facing MCP templates stay aligned with the published skill version."""

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
