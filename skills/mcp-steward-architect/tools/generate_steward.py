#!/usr/bin/env python3
"""Generate an executable MCP Steward v3 overlay on the canonical MCP baseline."""

from __future__ import annotations

import argparse
import hashlib
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
DESIGN_TEMPLATES = Path(__file__).resolve().parents[1] / "templates"
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
    "steward-state-machine.schema.json",
    "steward-mutation-policy.schema.json",
    "steward-proof-recipe.schema.json",
    "steward-acceptance.schema.json",
)
PROFILES = {"generic", "diagnostic", "verification", "research-evidence", "release-ops", "change-manager"}


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _sha256(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load generator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _base_generator(language: str) -> ModuleType:
    if language == "python":
        return _load_module(MCP_TOOLS / "generate_python_server.py", "ai_skills_mcp_python_generator")
    if language == "dotnet":
        return _load_module(MCP_TOOLS / "generate_dotnet_server.py", "ai_skills_mcp_dotnet_generator")
    raise ValueError("language must be python or dotnet")


def _upstream_document(steward_id: str) -> dict[str, Any]:
    capability_id = f"{steward_id}:seed-provider-result"
    identity = {"source": "pinned-trusted", "id": capability_id, "revision": "1"}
    contract = {**identity, "digest": _sha256(identity)}
    return {
        "schema_version": 2,
        "capability_id": capability_id,
        "contract": contract,
        "subject_types": ["target"],
        "target_types": ["target"],
        "identity_dimensions_observed": ["target"],
        "evidence_classes_produced": ["provider-observation"],
        "interaction": "stateful",
        "delivery": "durable-async",
        "idempotency": "provider-key",
        "recovery": "status-by-handle",
        "cancellation": {
            "mode": "confirmed",
            "delivery_model": "stateful",
            "idempotency": "provider-key",
            "reconciliation": "lookup-by-idempotency-key",
            "handle_affinity": "operation",
            "local_terminal_requires_remote_resolution": True,
        },
        "progress": {
            "kind": "state-revision",
            "stable_revision": True,
            "wait_hint": "retry-after",
            "worker_wait_policy": "external-maintenance",
        },
        "reconciliation": {"ambiguous_delivery": "lookup-by-idempotency-key"},
        "deadline": {"application_owned": True, "transport_may_shorten": False},
        "credential_affinity": "operation",
        "bounds": {
            "max_request_bytes": 65536,
            "max_result_bytes": 65536,
            "concurrency_scope": "target",
            "rate_limit_scope": "provider",
        },
        "confidentiality": {"egress_class": "local"},
    }


def _profile_document(steward_id: str, profile: str, *, durability_profile: str) -> dict[str, Any]:
    constrained = durability_profile == "constrained-file"
    return {
        "schema_version": 2,
        "steward": {"id": steward_id, "kind": profile, "contract_revision": 2},
        "contracts": {
            "state_machine": f"{steward_id}-state-machine@1",
            "mutation_policy": f"{steward_id}-mutation-policy@1",
            "proof_recipe": f"{steward_id}-seed-proof@1",
            "acceptance": f"{steward_id}-acceptance@1",
        },
        "features": {
            "durable_external_async": True,
            "causal_claims": True,
            "external_cancellation": True,
            "negative_aggregate_claims": False,
            "proof_producers": True,
            "runtime_binding_required": False,
            "exact_candidate_binding": True,
        },
        "authority": {
            "owns": ["durable-job-state"],
            "observes": ["seed-provider-result"],
            "may_mutate": ["seed-provider-operation"],
            "verifies": [],
            "parent_completion": "none",
            "never_claims": ["implicit-parent-completion", "independent-verification"],
        },
        "subject_identity": {
            "required_dimensions": ["target"],
            "freshness_dimensions": ["target"],
            "candidate_dimensions": ["target-revision"],
            "candidate_required_for_publication": True,
        },
        "durability": {
            "profile": durability_profile,
            "crash_model": ["process-restart"],
            "transactional_store_required": not constrained,
            "lineage_fencing": True,
            "attempt_fencing": True,
            "recovery_equivalence_required": True,
        },
        "external_operations": {
            "receipt_before_stateful_dispatch": True,
            "ambiguous_delivery": "reconcile-before-retry",
            "cancellation_reconciliation_required": True,
            "worker_wait_policy": "external-maintenance",
        },
        "mutation_admission": {
            "authority_values_non_defaultable": True,
            "durable_pre_dispatch_commit": True,
            "budget_reservation_required": True,
        },
        "credentials": {
            "secret_source": "intentional-provider",
            "persist_secret": False,
            "fallback": {"enabled": False, "preserve_principal_scope": True, "preserve_target": True},
        },
        "model": {"authority_ceiling": "advisory"},
        "completion": {
            "obligations": [{"id": "provider-result", "required": True, "evidence_class": "provider-observation"}],
            "handoff_digest": "sha256",
        },
        "observability": {"durable_timeline": True, "doctor": True},
    }


def _state_machine_document(steward_id: str) -> dict[str, Any]:
    text = (DESIGN_TEMPLATES / "steward-state-machine.yaml.template").read_text(encoding="utf-8")
    return yaml.safe_load(text.replace("__STEWARD_ID__", steward_id))


def _mutation_policy_document(steward_id: str, capability: dict[str, Any]) -> dict[str, Any]:
    capability_id = str(capability["capability_id"])
    capability_contract = dict(capability["contract"])
    local_identity = {"source": "local", "id": "local:handoff@1", "revision": "1"}
    local_contract = {**local_identity, "digest": _sha256(local_identity)}
    return {
        "schema_version": 1,
        "policy_id": f"{steward_id}-mutation-policy",
        "revision": 1,
        "effects": [
            {
                "id": "external-dispatch",
                "operation_kind": "submit",
                "transition": "dispatch-start",
                "authority_source": "steward-runtime",
                "lease_required": True,
                "subject_dimensions": ["target"],
                "candidate_required": True,
                "capability_ref": capability_id,
                "capability_contract": capability_contract,
                "durable_operation_required": True,
                "pre_dispatch_commit_required": True,
                "budget_reservation_required": True,
                "minimum_budget_ms": 1000,
                "finalization_reserve_ms": 500,
                "ambiguity_disposition": "reconcile",
                "typed_outcomes": [
                    "Admitted",
                    "LostAuthority",
                    "StaleCandidate",
                    "CapabilityUnavailable",
                    "ReconciliationRequired",
                    "BudgetUnavailable",
                ],
            },
            {
                "id": "cancellation-dispatch",
                "operation_kind": "cancel",
                "transition": "cancel-start",
                "authority_source": "steward-runtime",
                "lease_required": True,
                "subject_dimensions": ["target"],
                "candidate_required": True,
                "capability_ref": capability_id,
                "capability_contract": capability_contract,
                "durable_operation_required": True,
                "pre_dispatch_commit_required": True,
                "budget_reservation_required": True,
                "minimum_budget_ms": 1000,
                "finalization_reserve_ms": 500,
                "ambiguity_disposition": "reconcile",
                "typed_outcomes": [
                    "Admitted",
                    "LostAuthority",
                    "StaleCandidate",
                    "ReconciliationRequired",
                    "BudgetUnavailable",
                ],
            },
            {
                "id": "terminal-publication",
                "operation_kind": "publication",
                "transition": "completion-publish",
                "authority_source": "completion-gate",
                "lease_required": False,
                "subject_dimensions": ["target"],
                "candidate_required": True,
                "capability_ref": "local:handoff@1",
                "capability_contract": local_contract,
                "durable_operation_required": False,
                "pre_dispatch_commit_required": False,
                "budget_reservation_required": True,
                "minimum_budget_ms": 100,
                "finalization_reserve_ms": 100,
                "ambiguity_disposition": "block",
                "typed_outcomes": [
                    "Admitted",
                    "StaleCandidate",
                    "InsufficientEvidence",
                    "ReconciliationRequired",
                    "BudgetUnavailable",
                ],
            },
        ],
    }


def _proof_recipe_document(steward_id: str) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "recipe_id": f"{steward_id}-seed-proof",
        "revision": 1,
        "producers": [
            {
                "producer_id": "seed-provider",
                "trust_class": "external-trusted",
                "observation_kind": "provider-result",
                "subject_dimensions": ["target"],
                "claim_classes": ["provider-result"],
                "binding_requirements": ["target", "candidate"],
                "authority_ceiling": "observed",
                "independence": "external",
            }
        ],
        "criteria": [
            {
                "criterion_id": "provider-result",
                "canonical_claim": "provider-result",
                "subject_dimensions": ["target"],
                "candidate_binding_required": True,
                "binding_requirements": ["target", "candidate"],
                "required_authority": "observed",
                "freshness_seconds": 300,
                "approved_producers": ["seed-provider"],
                "coverage_semantics": "all-required",
                "probes": [],
                "sufficiency": "all-required",
            }
        ],
        "aggregation": {"unobserved_is_negative": False, "unknown_blocks_complete_negative": True},
        "completion": {
            "unresolved_required_criterion": "blocked",
            "advisory_model_findings_require_reproduction": True,
        },
    }


def _acceptance_document(steward_id: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "acceptance_id": f"{steward_id}-acceptance",
        "revision": 1,
        "claim_class": "structural",
        "required_lanes": ["implementer", "canonical-full", "fault-restart", "inherited-mcp", "exact-artifact"],
        "independent_required": False,
        "live_full_path_required": False,
        "exact_artifact": {
            "full_path_required": True,
            "runtime_prerequisites_declared": True,
            "restart_boundary_required": True,
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
            "idempotent_rationale": "The operation persists durable intent and does not replay remote effects inline."
        }
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def _embedded_docs(steward_id: str, profile: str, durability: str) -> dict[str, dict[str, Any]]:
    upstream = _upstream_document(steward_id)
    return {
        "steward_profile": _profile_document(steward_id, profile, durability_profile=durability),
        "steward_state_machine": _state_machine_document(steward_id),
        "steward_mutation_policy": _mutation_policy_document(steward_id, upstream),
        "steward_proof_recipe": _proof_recipe_document(steward_id),
        "steward_upstream_capability": upstream,
        "steward_acceptance": _acceptance_document(steward_id),
    }


def _apply_python_overlay(
    files: dict[str, str], package: str, server_name: str, docs: dict[str, dict[str, Any]]
) -> None:
    for path in list(files):
        if path.startswith(f"src/{package}/capabilities/") or path.startswith("tests/"):
            del files[path]
    files[f"src/{package}/steward_runtime.py"] = _read_template("python/steward_runtime.py.template")
    files[f"src/{package}/kernel.py"] = _read_template("python/kernel.py.template")
    files[f"src/{package}/server.py"] = _read_template("python/server.py.template", SERVER_NAME=server_name)
    files["tests/test_steward_runtime.py"] = _read_template("python/test_steward_runtime.py.template", PACKAGE=package)
    for name, document in docs.items():
        files[f"src/{package}/{name}.json"] = json.dumps(document, indent=2, sort_keys=True) + "\n"
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
            "Persists and reconciles cancellation of one durable Steward job.",
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
    for args in capabilities:
        cid, name, description, kind, risk, impact, idem, keyed = args
        files[f"src/{package}/capabilities/{cid}.json"] = _python_capability(
            cid,
            name,
            description,
            operation_kind=kind,
            risk=risk,
            impact=impact,
            idempotent=idem,
            idempotency_key_required=keyed,
        )
    pyproject = files["pyproject.toml"]
    marker = f'{package} = ["capabilities/*.json", "contracts/*.json"]'
    data = ["capabilities/*.json", "contracts/*.json", *[f"{name}.json" for name in docs]]
    replacement = f"{package} = " + json.dumps(data)
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
    program = (
        program.replace(marker, replacement, 1)
        .replace("inventory.read", "steward.read")
        .replace("inventory.write", "steward.write")
    )
    tool_chain = ".WithTools<CapabilityTools>()\n        .WithTools<InventoryTools>();"
    if program.count(tool_chain) != 2:
        raise RuntimeError("canonical .NET tool registration marker changed")
    return program.replace(tool_chain, ".WithTools<StewardTools>();")


def _patch_server_project(project: str, docs: dict[str, dict[str, Any]]) -> str:
    marker = "</Project>\n"
    entries = "\n".join(
        f'    <Content Update="{name}.json" CopyToOutputDirectory="PreserveNewest" CopyToPublishDirectory="PreserveNewest" />'
        for name in docs
    )
    content = f"  <ItemGroup>\n{entries}\n  </ItemGroup>\n</Project>\n"
    if project.count(marker) != 1:
        raise RuntimeError("canonical .NET project marker changed")
    return project.replace(marker, content, 1)


def _apply_dotnet_overlay(
    files: dict[str, str], namespace: str, server_name: str, docs: dict[str, dict[str, Any]]
) -> None:
    server_root = f"src/{namespace}.Mcp.Server"
    runtime = _read_template("dotnet/StewardSeedRuntime.cs.template", NAMESPACE=namespace)
    files[f"{server_root}/StewardSeedRuntime.cs"] = runtime
    files[f"{server_root}/StewardRecoveryService.cs"] = _read_template(
        "dotnet/StewardRecoveryService.cs.template", NAMESPACE=namespace
    )
    files[f"{server_root}/Tools.cs"] = _read_template("dotnet/Tools.cs.template", NAMESPACE=namespace)
    files[f"{server_root}/Program.cs"] = _patch_program(files[f"{server_root}/Program.cs"])
    project_path = f"{server_root}/{namespace}.Mcp.Server.csproj"
    files[project_path] = _patch_server_project(files[project_path], docs)
    for name, document in docs.items():
        files[f"{server_root}/{name}.json"] = json.dumps(document, indent=2, sort_keys=True) + "\n"
    files[f"tests/{namespace}.Mcp.Smoke/Program.cs"] = _read_template(
        "dotnet/SmokeProgram.cs.template", NAMESPACE=namespace, SERVER_NAME=server_name
    )


def steward_files(language: str, identity: str, server_name: str, steward_id: str, profile: str) -> dict[str, str]:
    if profile not in PROFILES:
        raise ValueError(f"unsupported profile: {profile}")
    base = _base_generator(language)
    files = dict(base.project_files(identity, server_name))
    durability = "single-node-durable" if language == "python" else "constrained-file"
    docs = _embedded_docs(steward_id, profile, durability)
    if language == "python":
        _apply_python_overlay(files, identity, server_name, docs)
    else:
        _apply_dotnet_overlay(files, identity, server_name, docs)
    overlay = {
        "steward/steward-profile.yaml": yaml.safe_dump(docs["steward_profile"], sort_keys=False),
        "steward/steward-state-machine.yaml": yaml.safe_dump(docs["steward_state_machine"], sort_keys=False),
        "steward/mutation-policy.yaml": yaml.safe_dump(docs["steward_mutation_policy"], sort_keys=False),
        "steward/proof-recipe.yaml": yaml.safe_dump(docs["steward_proof_recipe"], sort_keys=False),
        "steward/upstream-capability.yaml": yaml.safe_dump(docs["steward_upstream_capability"], sort_keys=False),
        "steward/acceptance.yaml": yaml.safe_dump(docs["steward_acceptance"], sort_keys=False),
        "steward/fault-injection.yaml": yaml.safe_dump(
            {
                "schema_version": 1,
                "fault_points": [
                    "after-reservation",
                    "after-dispatch-start",
                    "after-dispatch",
                    "before-handle-persist",
                    "before-result-persist",
                    "after-cancel-start",
                    "after-cancel-dispatch",
                    "before-cancel-bind",
                    "before-terminal-publication",
                ],
            },
            sort_keys=False,
        ),
        "steward/README.md": "# Steward runtime v3\n\nGenerated Design Pack plus durable admission, mutation gates, reconciliation, cancellation, evidence promotion, recovery-equivalent completion, audit/doctor, and fault injection. Generated scaffolding is architecture-seed evidence only.\n",
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


def _reject_symlink_components(path: Path) -> None:
    canonical = _base_generator("python")
    guard = getattr(canonical, "_reject_symlink_components", None)
    if not callable(guard):
        raise RuntimeError("canonical MCP generator symlink-confinement primitive is unavailable")
    guard(path)


def generate_project(
    destination: Path, *, language: str, identity: str, server_name: str, steward_id: str, profile: str
) -> list[Path]:
    files = steward_files(language, identity, server_name, steward_id, profile)
    expanded = destination.expanduser()
    if os.path.lexists(expanded):
        raise FileExistsError(expanded)
    _reject_symlink_components(expanded)
    parent = expanded.parent.resolve(strict=False)
    parent.mkdir(parents=True, exist_ok=True)
    _reject_symlink_components(expanded)
    if not parent.is_dir():
        raise ValueError("destination parent must be a regular directory")
    destination = parent / expanded.name
    if os.path.lexists(destination):
        raise FileExistsError(destination)
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
    parser.add_argument("--identity", required=True)
    parser.add_argument("--name", required=True)
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
