#!/usr/bin/env python3
"""Generate an executable durable Steward overlay on the canonical MCP baseline."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
MCP_TOOLS = ROOT / "skills" / "mcp-server-architect" / "tools"
CONTRACTS = ROOT / "contracts"
TEMPLATES = Path(__file__).resolve().with_name("steward-templates")
STEWARD_CONTRACTS = (
    "steward-profile.schema.json",
    "steward-job.schema.json",
    "external-operation-receipt.schema.json",
    "steward-evidence.schema.json",
    "steward-handoff.schema.json",
    "steward-lineage.schema.json",
    "steward-completion.schema.json",
    "upstream-capability.schema.json",
)
PROFILES = {
    "generic",
    "diagnostic",
    "verification",
    "research-evidence",
    "release-ops",
    "change-manager",
}


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load generator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _base_generator(language: str) -> ModuleType:
    if language == "python":
        return _load_module(
            MCP_TOOLS / "generate_python_server.py",
            "ai_skills_mcp_python_generator",
        )
    if language == "dotnet":
        return _load_module(
            MCP_TOOLS / "generate_dotnet_server.py",
            "ai_skills_mcp_dotnet_generator",
        )
    raise ValueError("language must be python or dotnet")


def _profile_document(
    steward_id: str,
    profile: str,
    *,
    durability_profile: str,
) -> dict[str, Any]:
    constrained_file = durability_profile == "constrained-file"
    return {
        "schema_version": 1,
        "steward": {"id": steward_id, "kind": profile, "contract_revision": 1},
        "authority": {
            "owns": ["durable-job-state"],
            "observes": ["seed-provider-result"],
            "may_mutate": [],
            "verifies": [],
            "parent_completion": "none",
            "never_claims": ["implicit-parent-completion"],
        },
        "subject_identity": {
            "required_dimensions": ["target"],
            "freshness_dimensions": ["target"],
        },
        "durability": {
            "profile": durability_profile,
            "crash_model": ["process-restart"],
            "transactional_store_required": not constrained_file,
            "lineage_fencing": True,
            "attempt_fencing": True,
        },
        "external_operations": {
            "receipt_before_stateful_dispatch": True,
            "ambiguous_delivery": "reconcile-before-retry",
        },
        "credentials": {
            "secret_source": "intentional-provider",
            "persist_secret": False,
            "fallback": {
                "enabled": False,
                "preserve_principal_scope": True,
                "preserve_target": True,
            },
        },
        "model": {"authority_ceiling": "advisory"},
        "completion": {
            "obligations": [
                {
                    "id": "provider-result",
                    "required": True,
                    "evidence_class": "provider-observation",
                }
            ],
            "handoff_digest": "sha256",
        },
        "observability": {"durable_timeline": True, "doctor": True},
    }


def _proof_recipe_document(steward_id: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "recipe_id": f"{steward_id}-seed-proof",
        "revision": 1,
        "criteria": [
            {
                "criterion_id": "provider-result",
                "subject_dimensions": ["target"],
                "required_authority": "observed",
                "freshness_seconds": 300,
                "approved_producers": ["seed-provider"],
                "probes": [],
                "sufficiency": "all-required",
            }
        ],
        "completion": {
            "unresolved_required_criterion": "blocked",
            "advisory_model_findings_require_reproduction": True,
        },
    }


def _read_template(relative: str, **replacements: str) -> str:
    text = (TEMPLATES / relative).read_text(encoding="utf-8")
    for key, value in replacements.items():
        text = text.replace(f"__{key}__", value)
    return text


def _python_capability(
    capability_id: str,
    name: str,
    description: str,
    *,
    operation_kind: str,
    risk: str,
    impact: str,
    idempotent: bool,
    idempotency_key_required: bool,
) -> str:
    write = operation_kind != "read"
    value: dict[str, Any] = {
        "schema_version": 2,
        "contract_revision": 2,
        "id": capability_id,
        "name": name,
        "description": description,
        "operation_kind": operation_kind,
        "risk": risk,
        "determinism": "environment-dependent" if write else "deterministic",
        "latency": "interactive",
        "impact": impact,
        "active_state": "active",
        "retryable": False,
        "idempotent": idempotent,
        "reversible": False,
        "requires_confirmation": False,
        "idempotency_key_required": idempotency_key_required,
        "idempotency": {
            "mode": "keyed" if idempotency_key_required else "intrinsic",
            "scope": "principal-target" if write else "invocation",
        },
        "async_model": "task" if capability_id == "steward_submit" else "synchronous",
        "outcome_contract": "layered" if write else "simple",
        "reconciliation": {
            "supported": write,
            "required_after_ambiguous_dispatch": write,
            "method": "operation-status" if write else "none",
        },
        "publication": {"model": "inline", "implies_verification": False},
        "result_bounded": True,
        "runtime_identity": {"supported": True, "level": "artifact-and-generation"},
        "authorization_scopes": ["steward.write"] if write else ["steward.read"],
        "concurrency": {
            "scope": "principal-target" if write else "principal",
            "limit": 1 if write else 8,
            "queue_limit": 16,
        },
        "max_response_bytes": 65536,
        "protocol_revisions": ["2026-07-28", "2025-11-25"],
    }
    if write and idempotent:
        value["extensions"] = {
            "idempotent_rationale": (
                "The operation persists durable intent and never repeats the remote effect inline."
            )
        }
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _apply_python_overlay(
    files: dict[str, str],
    package: str,
    server_name: str,
    profile: dict[str, Any],
    proof: dict[str, Any],
) -> None:
    for path in list(files):
        if path.startswith(f"src/{package}/capabilities/"):
            del files[path]
    files[f"src/{package}/steward_runtime.py"] = _read_template("python/steward_runtime.py.template")
    files[f"src/{package}/kernel.py"] = _read_template("python/kernel.py.template")
    files[f"src/{package}/server.py"] = _read_template(
        "python/server.py.template",
        SERVER_NAME=server_name,
    )
    files["tests/test_steward_runtime.py"] = _read_template(
        "python/test_steward_runtime.py.template",
        PACKAGE=package,
    )
    files[f"src/{package}/steward_profile.json"] = json.dumps(profile, indent=2, sort_keys=True) + "\n"
    files[f"src/{package}/steward_proof_recipe.json"] = json.dumps(proof, indent=2, sort_keys=True) + "\n"
    capabilities = (
        (
            "describe_capabilities",
            "Describe capabilities",
            "Returns the governed Steward capability catalog.",
            "read",
            "low",
            "none",
            True,
            False,
        ),
        (
            "steward_submit",
            "Submit Steward job",
            "Durably admits an idempotent Steward job and returns its stable job ID.",
            "write",
            "medium",
            "local",
            True,
            True,
        ),
        (
            "steward_status",
            "Steward status",
            "Returns bounded operational status for one durable Steward job.",
            "read",
            "low",
            "none",
            True,
            False,
        ),
        (
            "steward_get",
            "Get Steward result",
            "Returns bounded evidence, completion evaluation and terminal handoff for one job.",
            "read",
            "low",
            "none",
            True,
            False,
        ),
        (
            "steward_cancel",
            "Cancel Steward job",
            "Persists cancellation intent for one non-terminal Steward job.",
            "write",
            "medium",
            "local",
            True,
            False,
        ),
        (
            "steward_doctor",
            "Steward doctor",
            "Returns bounded durable diagnostics, ambiguity and recovery state.",
            "read",
            "low",
            "none",
            True,
            False,
        ),
    )
    for capability in capabilities:
        capability_id, name, description, operation_kind, risk, impact, idempotent, keyed = capability
        files[f"src/{package}/capabilities/{capability_id}.json"] = _python_capability(
            capability_id,
            name,
            description,
            operation_kind=operation_kind,
            risk=risk,
            impact=impact,
            idempotent=idempotent,
            idempotency_key_required=keyed,
        )
    pyproject = files["pyproject.toml"]
    marker = f'{package} = ["capabilities/*.json", "contracts/*.json"]'
    replacement = (
        f'{package} = ["capabilities/*.json", "contracts/*.json", "steward_profile.json", "steward_proof_recipe.json"]'
    )
    if marker not in pyproject:
        raise RuntimeError("canonical Python package-data marker changed")
    files["pyproject.toml"] = pyproject.replace(marker, replacement, 1)


def _patch_program(program: str) -> str:
    marker = "    services.AddSingleton<InvocationKernel>();"
    replacement = "\n".join(
        (
            marker,
            "    services.AddSingleton<ISeedClock>(SystemSeedClock.Instance);",
            "    services.AddSingleton<ISeedProvider, FakeSeedProvider>();",
            "    services.AddSingleton<SeedFaultInjector>();",
            "    services.AddSingleton<StewardSeedRuntime>();",
            "    services.AddHostedService<StewardRecoveryService>();",
        )
    )
    if program.count(marker) != 1:
        raise RuntimeError("canonical .NET composition marker changed")
    program = program.replace(marker, replacement, 1)
    program = program.replace("inventory.read", "steward.read")
    program = program.replace("inventory.write", "steward.write")
    tool_chain = ".WithTools<CapabilityTools>()\n        .WithTools<InventoryTools>();"
    if program.count(tool_chain) != 2:
        raise RuntimeError("canonical .NET tool registration marker changed")
    return program.replace(tool_chain, ".WithTools<StewardTools>();")


def _patch_server_project(project: str) -> str:
    marker = "</Project>\n"
    content = """  <ItemGroup>
    <Content Update="steward_profile.json" CopyToOutputDirectory="PreserveNewest" CopyToPublishDirectory="PreserveNewest" />
    <Content Update="steward_proof_recipe.json" CopyToOutputDirectory="PreserveNewest" CopyToPublishDirectory="PreserveNewest" />
  </ItemGroup>
</Project>
"""
    if project.count(marker) != 1:
        raise RuntimeError("canonical .NET project marker changed")
    return project.replace(marker, content, 1)


def _apply_dotnet_overlay(
    files: dict[str, str],
    namespace: str,
    server_name: str,
    profile: dict[str, Any],
    proof: dict[str, Any],
) -> None:
    server_root = f"src/{namespace}.Mcp.Server"
    files[f"{server_root}/StewardSeedRuntime.cs"] = _read_template(
        "dotnet/StewardSeedRuntime.cs.template",
        NAMESPACE=namespace,
    )
    files[f"{server_root}/StewardRecoveryService.cs"] = _read_template(
        "dotnet/StewardRecoveryService.cs.template",
        NAMESPACE=namespace,
    )
    files[f"{server_root}/Tools.cs"] = _read_template(
        "dotnet/Tools.cs.template",
        NAMESPACE=namespace,
    )
    files[f"{server_root}/Program.cs"] = _patch_program(files[f"{server_root}/Program.cs"])
    project_path = f"{server_root}/{namespace}.Mcp.Server.csproj"
    files[project_path] = _patch_server_project(files[project_path])
    files[f"{server_root}/steward_profile.json"] = json.dumps(profile, indent=2, sort_keys=True) + "\n"
    files[f"{server_root}/steward_proof_recipe.json"] = json.dumps(proof, indent=2, sort_keys=True) + "\n"
    files[f"tests/{namespace}.Mcp.Smoke/Program.cs"] = _read_template(
        "dotnet/SmokeProgram.cs.template",
        NAMESPACE=namespace,
        SERVER_NAME=server_name,
    )


def steward_files(
    language: str,
    identity: str,
    server_name: str,
    steward_id: str,
    profile: str,
) -> dict[str, str]:
    if profile not in PROFILES:
        raise ValueError(f"unsupported profile: {profile}")
    base = _base_generator(language)
    files = dict(base.project_files(identity, server_name))
    durability = "single-node-durable" if language == "python" else "constrained-file"
    profile_document = _profile_document(
        steward_id,
        profile,
        durability_profile=durability,
    )
    proof_document = _proof_recipe_document(steward_id)
    if language == "python":
        _apply_python_overlay(
            files,
            identity,
            server_name,
            profile_document,
            proof_document,
        )
    else:
        _apply_dotnet_overlay(
            files,
            identity,
            server_name,
            profile_document,
            proof_document,
        )

    overlay = {
        "steward/steward-profile.yaml": yaml.safe_dump(profile_document, sort_keys=False),
        "steward/proof-recipe.yaml": yaml.safe_dump(proof_document, sort_keys=False),
        "steward/fault-injection.yaml": yaml.safe_dump(
            {
                "schema_version": 1,
                "fault_points": [
                    "after-reservation",
                    "after-dispatch",
                    "before-handle-persist",
                    "before-result-persist",
                    "before-terminal-publication",
                ],
            },
            sort_keys=False,
        ),
        "steward/README.md": (
            "# Steward runtime\n\n"
            "The generated seed exposes only semantic Steward lifecycle tools. It includes durable admission, "
            "scheduler/recovery hooks, fake time/provider/fault injection, operation receipts, evidence resolution, "
            "a mandatory Completion Gate, digest-bound handoff publication, durable audit, and doctor diagnostics.\n"
        ),
    }
    for contract_name in STEWARD_CONTRACTS:
        overlay[f"steward/contracts/{contract_name}"] = (CONTRACTS / contract_name).read_text(encoding="utf-8")
    collisions = sorted(set(files) & set(overlay))
    if collisions:
        raise ValueError("Steward overlay collides with base generator: " + ", ".join(collisions))
    files.update(overlay)
    return files


def _publish_no_replace(language: str, staging: Path, destination: Path) -> None:
    base = _base_generator(language)
    if language == "python":
        implementation = getattr(base, "_implementation", None)
        rename = getattr(implementation, "_rename_noreplace", None)
    else:
        rename = getattr(base, "_rename_noreplace", None)
    if not callable(rename):
        raise RuntimeError("canonical MCP generator no-replace publication primitive is unavailable")
    rename(staging, destination)


def generate_project(
    destination: Path,
    *,
    language: str,
    identity: str,
    server_name: str,
    steward_id: str,
    profile: str,
) -> list[Path]:
    files = steward_files(language, identity, server_name, steward_id, profile)
    expanded = destination.expanduser()
    if os.path.lexists(expanded):
        raise FileExistsError(expanded)
    parent = expanded.parent.resolve(strict=False)
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / expanded.name
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=parent))
    published = False
    try:
        for relative, content in sorted(files.items()):
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
        _publish_no_replace(language, staging, destination)
        published = True
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    return [Path(path) for path in sorted(files)]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--language", choices=["python", "dotnet"], required=True)
    parser.add_argument("--identity", required=True, help="Python package or .NET namespace")
    parser.add_argument("--name", required=True, help="Human-readable MCP server name")
    parser.add_argument("--steward-id", required=True)
    parser.add_argument("--profile", choices=sorted(PROFILES), default="generic")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    generated = generate_project(
        args.destination,
        language=args.language,
        identity=args.identity,
        server_name=args.name,
        steward_id=args.steward_id,
        profile=args.profile,
    )
    print(f"generated {len(generated)} files in {args.destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
