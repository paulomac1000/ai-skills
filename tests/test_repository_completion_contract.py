"""Final repository-level regressions for audit completion and cleanup."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_temporary_workflows_and_sdk_profile_routing_are_clean() -> None:
    workflows = ROOT / ".github/workflows"
    assert not (workflows / "export-source-temp.yml").exists()
    assert not (workflows / "regenerate-locks-temp.yml").exists()
    assert not (workflows / "apply-mcp-audit-followup-phase1.yml").exists()

    references = ROOT / "skills/mcp-server-architect/references"
    pointer = references / "python-fastmcp.md"
    assert pointer.is_file()
    assert (references / "python-official-mcp-sdk.md").is_file()
    assert (references / "python-fastmcp-package.md").is_file()
    assert (references / "dotnet-mcp-sdk.md").is_file()
    pointer_text = pointer.read_text(encoding="utf-8")
    assert "not an SDK profile" in pointer_text
    assert "python-fastmcp-package.md" in pointer_text

    manifest = (ROOT / "skills/mcp-server-architect/manifest.yaml").read_text(
        encoding="utf-8"
    )
    assert "- references/python-fastmcp.md" not in manifest
    assert "- references/python-fastmcp-package.md" in manifest


def test_python_generator_has_one_public_cli_and_no_string_patching() -> None:
    tools = ROOT / "skills/mcp-server-architect/tools"
    public = (tools / "generate_python_server.py").read_text(encoding="utf-8")
    implementation = (tools / "generate_python_server_impl.py").read_text(
        encoding="utf-8"
    )

    assert "def generate_project" in public
    assert "def main" in public
    assert "def generate_project" not in implementation
    assert "def main" not in implementation
    assert "_replace_required" not in public
    assert "_replace_required" not in implementation
    assert "python-template" in implementation


def test_consumer_public_signature_has_no_boolean_trust_upgrade() -> None:
    path = ROOT / "skills/mcp-server-consumer/tools/decision_engine.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "infer_capability_profile"
    )
    arguments = {
        argument.arg
        for argument in (
            *function.args.posonlyargs,
            *function.args.args,
            *function.args.kwonlyargs,
        )
    }
    assert "trusted_server" not in arguments
    assert {"identity", "trusted_policy", "trusted_contract"} <= arguments


def test_identity_binding_is_exact_and_immutable() -> None:
    import importlib.util
    import sys

    path = ROOT / "skills/mcp-server-consumer/tools/decision_engine.py"
    spec = importlib.util.spec_from_file_location(
        "completion_decision_engine",
        path,
    )
    assert spec and spec.loader
    engine = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = engine
    spec.loader.exec_module(engine)

    identity = engine.CapabilityIdentity(
        server_identity="server:example",
        tool_name="inventory.list",
        tool_schema_hash="sha256:" + "1" * 64,
        manifest_version="1",
    )
    binding = engine.TrustedPolicyBinding(
        identity=identity,
        source="reviewed-contract:sha256:" + "2" * 64,
    )
    assert binding.identity == identity
    assert "trusted_server" not in inspect.signature(
        engine.infer_capability_profile
    ).parameters
