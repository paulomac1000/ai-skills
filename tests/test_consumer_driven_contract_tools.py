"""Regression tests promoted from real MCP consumer migrations."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from contracts.mcp_public_contract import compare_contracts, render_comparison, validate_contract
from contracts.validate_deployment_observation import validate_observation

ROOT = Path(__file__).resolve().parents[1]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _contract(*, version: str = "1.0.0", revision: str = "a" * 40) -> dict[str, object]:
    return {
        "format": "ai-skills-mcp-public-contract",
        "schema_version": 1,
        "source_revision": revision,
        "artifact": {
            "kind": "wheel",
            "identity": "sample-1.0.0-py3-none-any.whl",
            "digest": "sha256:" + "1" * 64,
        },
        "server": {"name": "sample", "version": version},
        "sdk": {"profile": "python-official-mcp", "version": "2.0.0"},
        "transports": ["stdio"],
        "authentication": {
            "required": False,
            "mechanism": "local-process",
            "target_selection": "configured-target",
        },
        "tools": [
            {
                "name": "list_items",
                "version": "1.0.0",
                "input_schema": {
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 100}},
                    "required": [],
                    "additionalProperties": False,
                },
                "output_schema": {
                    "type": "object",
                    "properties": {"items": {"type": "array"}},
                    "required": ["items"],
                    "additionalProperties": True,
                },
                "error_contract": ["invalid-input", "upstream-unavailable"],
                "pagination": "bounded limit with no cursor",
                "retry_semantics": "read retries only on explicit transient failures",
                "target_selection": "configured-target",
            }
        ],
    }


def test_public_contract_diff_requires_minor_for_additive_optional_input() -> None:
    baseline = _contract()
    candidate = _contract(version="1.1.0", revision="b" * 40)
    tool = candidate["tools"][0]
    assert isinstance(tool, dict)
    input_schema = tool["input_schema"]
    assert isinstance(input_schema, dict)
    properties = input_schema["properties"]
    assert isinstance(properties, dict)
    properties["query"] = {"type": "string"}

    comparison = compare_contracts(baseline, candidate)
    assert comparison.required_bump == "minor"
    assert comparison.version_satisfies is True
    assert any(change.pointer.endswith("/properties/query") for change in comparison.changes)


def test_public_contract_diff_rejects_minor_for_new_required_input() -> None:
    baseline = _contract()
    candidate = _contract(version="1.1.0", revision="b" * 40)
    tool = candidate["tools"][0]
    assert isinstance(tool, dict)
    input_schema = tool["input_schema"]
    assert isinstance(input_schema, dict)
    properties = input_schema["properties"]
    required = input_schema["required"]
    assert isinstance(properties, dict) and isinstance(required, list)
    properties["account"] = {"type": "string"}
    required.append("account")

    comparison = compare_contracts(baseline, candidate)
    assert comparison.required_bump == "major"
    assert comparison.version_satisfies is False

    candidate["server"] = {"name": "sample", "version": "2.0.0"}
    assert compare_contracts(baseline, candidate).version_satisfies is True


def test_public_contract_diff_treats_policy_semantics_as_breaking() -> None:
    baseline = _contract()
    candidate = _contract(version="1.9.0", revision="b" * 40)
    tool = candidate["tools"][0]
    assert isinstance(tool, dict)
    tool["retry_semantics"] = "blind retry after timeout"
    tool["target_selection"] = "fallback to any available target"

    report = render_comparison(baseline, candidate)
    assert report["required_bump"] == "major"
    assert report["version_satisfies"] is False
    pointers = {change["pointer"] for change in report["changes"]}
    assert "/tools/list_items/retry_semantics" in pointers
    assert "/tools/list_items/target_selection" in pointers


def test_contract_capture_uses_exact_probe_and_strips_provider_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = _load_module(
        "capture_mcp_contract",
        ROOT / "skills/mcp-server-architect/tools/capture_mcp_contract.py",
    )
    snapshot = _contract(revision="c" * 40)
    input_path = tmp_path / "snapshot.json"
    input_path.write_text(json.dumps(snapshot), encoding="utf-8")
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import json, os, pathlib, sys\n"
        "doc=json.loads(pathlib.Path(sys.argv[1]).read_text())\n"
        "if os.environ.get('GITHUB_TOKEN'): doc['server']['name']='credential-leaked'\n"
        "print(json.dumps(doc))\n",
        encoding="utf-8",
    )
    output = tmp_path / "captured.json"
    monkeypatch.setenv("GITHUB_TOKEN", "must-not-reach-probe")

    assert (
        capture.main(
            [
                "--output",
                str(output),
                "--working-directory",
                str(tmp_path),
                "--expected-source-revision",
                "c" * 40,
                "--expected-artifact-digest",
                "sha256:" + "1" * 64,
                "--",
                sys.executable,
                str(probe),
                str(input_path),
            ]
        )
        == 0
    )
    captured = json.loads(output.read_text(encoding="utf-8"))
    assert captured["server"]["name"] == "sample"
    assert validate_contract(captured) == []


def test_read_only_planner_projects_real_consumer_controls(tmp_path: Path) -> None:
    planner = _load_module(
        "plan_existing_project",
        ROOT / "skills/mcp-server-architect/tools/plan_existing_project.py",
    )
    (tmp_path / "pyproject.toml").write_text(
        """[project]\nname='legacy-finance'\nversion='1.2.0'\ndependencies=['mcp>=2,<3','requests==2.34.2']\n[tool.pytest.ini_options]\naddopts='-m \"not external\"'\n""",
        encoding="utf-8",
    )
    (tmp_path / "server.py").write_text(
        "# stdio streamable_http create_record delete_record requests http\n",
        encoding="utf-8",
    )
    (tmp_path / "tests/external").mkdir(parents=True)
    (tmp_path / "tests/external/test_live.py").write_text(
        "import pytest\npytestmark = pytest.mark.external\n",
        encoding="utf-8",
    )

    plan = planner.build_plan(tmp_path, target_level="L2")
    assert set(plan["context"]["profiles"]) >= {
        "mcp",
        "external-upstream",
        "live-backend",
        "local-stdio",
        "remote-http",
    }
    assert set(plan["context"]["capabilities"]) == {"write", "destructive"}
    controls = {item["id"] for item in plan["applicable_controls"]}
    assert "mcp.upstream.contract-observed" in controls
    assert "mcp.testing.live-backend-safety" in controls
    assert "mcp.authorization.transport-parity" in controls
    assert plan["human_decisions"] == {
        "distribution_profile": "needs-human-decision",
        "exposure_profile": "needs-human-decision",
    }
    assert plan["sdk_compatibility_claim"] == {
        "package": "mcp",
        "requirement": ">=2,<3",
        "status": "requires-compatibility-evidence",
    }
    assert any("narrow the SDK claim" in action for action in plan["next_actions"])
    assert plan["next_actions"][0].startswith("observe and validate upstream-contract")


def test_deployment_observation_keeps_unavailable_live_prerequisite_not_executed(tmp_path: Path) -> None:
    observation = {
        "format": "ai-skills-deployment-observation",
        "schema_version": 1,
        "source_revision": "d" * 40,
        "artifact": {"identity": "sha256:artifact", "digest": "sha256:" + "2" * 64},
        "deployment_identity": "home-assistant-test",
        "environment_class": "live-home-assistant",
        "command": {"argv": ["python", "smoke.py"], "working_directory": "."},
        "result": {"status": "not-executed", "reason": "live credential unavailable"},
        "actor": {"kind": "runner", "identity": "local-ci"},
    }
    path = tmp_path / "deployment-observation.yaml"
    import yaml

    path.write_text(yaml.safe_dump(observation), encoding="utf-8")
    assert validate_observation(path) == []

    observation["result"] = {
        "status": "passed",
        "started_at": "2026-08-12T10:01:00Z",
        "completed_at": "2026-08-12T10:00:00Z",
        "result_digest": "sha256:" + "3" * 64,
    }
    path.write_text(yaml.safe_dump(observation), encoding="utf-8")
    assert any("must not precede" in finding for finding in validate_observation(path))
