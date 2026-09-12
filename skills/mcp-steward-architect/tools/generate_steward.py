#!/usr/bin/env python3
"""Generate a durable Steward overlay on the canonical MCP server baseline."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import tempfile
from pathlib import Path
from types import ModuleType

import yaml

ROOT = Path(__file__).resolve().parents[3]
MCP_TOOLS = ROOT / "skills" / "mcp-server-architect" / "tools"
CONTRACTS = ROOT / "contracts"
STEWARD_CONTRACTS = (
    "steward-profile.schema.json",
    "steward-job.schema.json",
    "external-operation-receipt.schema.json",
    "steward-handoff.schema.json",
)
PROFILES = {"generic", "diagnostic", "verification", "research-evidence", "release-ops", "change-manager"}


def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load generator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _profile(steward_id: str, profile: str) -> str:
    value = {
        "schema_version": 1,
        "steward": {"id": steward_id, "kind": profile, "contract_revision": 1},
        "authority": {
            "owns": ["durable-job-state"],
            "observes": [],
            "may_mutate": [],
            "verifies": [],
            "parent_completion": "none",
            "never_claims": ["implicit-parent-completion"],
        },
        "subject_identity": {"required_dimensions": ["target"], "freshness_dimensions": []},
        "durability": {
            "profile": "single-node-durable",
            "crash_model": ["process-restart"],
            "transactional_store_required": True,
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
            "fallback": {"enabled": False, "preserve_principal_scope": True, "preserve_target": True},
        },
        "model": {"authority_ceiling": "advisory"},
        "completion": {"obligations": [], "handoff_digest": "sha256"},
        "observability": {"durable_timeline": True, "doctor": True},
    }
    return yaml.safe_dump(value, sort_keys=False)


def _python_runtime(package: str) -> str:
    return '''"""Minimal durable Steward state seed; domain code should build on semantic ports."""\n\nfrom __future__ import annotations\n\nimport json\nimport sqlite3\nfrom pathlib import Path\nfrom typing import Any\n\n\nclass StewardStore:\n    def __init__(self, path: Path) -> None:\n        self.path = path\n        self._initialize()\n\n    def _connect(self) -> sqlite3.Connection:\n        connection = sqlite3.connect(self.path)\n        connection.execute("PRAGMA journal_mode=WAL")\n        connection.execute("PRAGMA foreign_keys=ON")\n        return connection\n\n    def _initialize(self) -> None:\n        with self._connect() as db:\n            db.executescript(\n                """\n                CREATE TABLE IF NOT EXISTS steward_jobs (\n                    job_id TEXT PRIMARY KEY, lineage_id TEXT NOT NULL, generation INTEGER NOT NULL,\n                    attempt_id TEXT NOT NULL, version INTEGER NOT NULL, status TEXT NOT NULL,\n                    subject_json TEXT NOT NULL, heartbeat_at TEXT NOT NULL, progress_at TEXT NOT NULL\n                );\n                CREATE TABLE IF NOT EXISTS external_operations (\n                    operation_id TEXT PRIMARY KEY, job_id TEXT NOT NULL, generation INTEGER NOT NULL,\n                    attempt_id TEXT NOT NULL, request_digest TEXT NOT NULL, delivery TEXT NOT NULL,\n                    retry_disposition TEXT NOT NULL, credential_slot_id TEXT NOT NULL, remote_handle TEXT NULL,\n                    FOREIGN KEY(job_id) REFERENCES steward_jobs(job_id)\n                );\n                """\n            )\n\n    def admit(self, *, job_id: str, lineage_id: str, generation: int, attempt_id: str, subject: dict[str, Any], now: str) -> None:\n        with self._connect() as db:\n            db.execute(\n                "INSERT INTO steward_jobs VALUES (?, ?, ?, ?, 0, 'queued', ?, ?, ?)",\n                (job_id, lineage_id, generation, attempt_id, json.dumps(subject, sort_keys=True), now, now),\n            )\n\n    def reserve_external(self, *, operation_id: str, job_id: str, generation: int, attempt_id: str, request_digest: str, credential_slot_id: str) -> None:\n        with self._connect() as db:\n            current = db.execute("SELECT generation, attempt_id FROM steward_jobs WHERE job_id = ?", (job_id,)).fetchone()\n            if current != (generation, attempt_id):\n                raise RuntimeError("stale generation/attempt")\n            db.execute(\n                "INSERT INTO external_operations VALUES (?, ?, ?, ?, ?, 'not-delivered', 'forbidden', ?, NULL)",\n                (operation_id, job_id, generation, attempt_id, request_digest, credential_slot_id),\n            )\n\n    def mark_delivery_unknown(self, operation_id: str) -> None:\n        with self._connect() as db:\n            db.execute(\n                "UPDATE external_operations SET delivery='delivery-unknown', retry_disposition='reconcile-first' WHERE operation_id=?",\n                (operation_id,),\n            )\n\n    def receipt(self, operation_id: str) -> tuple[str, str] | None:\n        with self._connect() as db:\n            row = db.execute("SELECT delivery, retry_disposition FROM external_operations WHERE operation_id=?", (operation_id,)).fetchone()\n            return None if row is None else (str(row[0]), str(row[1]))\n'''


def _python_test(package: str) -> str:
    return f'''from pathlib import Path\n\nfrom {package}.steward_runtime import StewardStore\n\n\ndef test_receipt_is_durable_and_unknown_delivery_requires_reconciliation(tmp_path: Path) -> None:\n    path = tmp_path / "steward.db"\n    store = StewardStore(path)\n    store.admit(job_id="j1", lineage_id="l1", generation=1, attempt_id="a1", subject={{"type": "repo", "id": "x"}}, now="2026-01-01T00:00:00Z")\n    store.reserve_external(operation_id="op1", job_id="j1", generation=1, attempt_id="a1", request_digest="sha256:" + "0" * 64, credential_slot_id="primary")\n    store.mark_delivery_unknown("op1")\n    assert StewardStore(path).receipt("op1") == ("delivery-unknown", "reconcile-first")\n\n\ndef test_stale_attempt_cannot_reserve_external_work(tmp_path: Path) -> None:\n    store = StewardStore(tmp_path / "steward.db")\n    store.admit(job_id="j1", lineage_id="l1", generation=2, attempt_id="a2", subject={{"type": "repo", "id": "x"}}, now="2026-01-01T00:00:00Z")\n    try:\n        store.reserve_external(operation_id="op1", job_id="j1", generation=1, attempt_id="a1", request_digest="sha256:" + "0" * 64, credential_slot_id="primary")\n    except RuntimeError as exc:\n        assert "stale" in str(exc)\n    else:\n        raise AssertionError("stale attempt was admitted")\n'''


def _dotnet_contracts(namespace: str) -> str:
    return f'''namespace {namespace}.Mcp.Domain;\n\npublic enum StewardDeliveryState {{ NotDelivered, Delivered, DeliveryUnknown }}\npublic enum StewardRetryDisposition {{ Forbidden, Eligible, ReconcileFirst }}\n\npublic sealed record StewardAttemptIdentity(string JobId, string LineageId, long Generation, string AttemptId, long Version);\n\npublic sealed record ExternalOperationReceipt(\n    string OperationId, StewardAttemptIdentity Attempt, string CapabilityIdentity, string TargetIdentity,\n    string RequestDigest, StewardDeliveryState Delivery, StewardRetryDisposition RetryDisposition,\n    string CredentialSlotId, string? RemoteHandle);\n\npublic static class StewardGuards\n{{\n    public static void RequireCurrent(StewardAttemptIdentity expected, StewardAttemptIdentity actual)\n    {{\n        if (expected.JobId != actual.JobId || expected.LineageId != actual.LineageId ||\n            expected.Generation != actual.Generation || expected.AttemptId != actual.AttemptId ||\n            expected.Version != actual.Version)\n            throw new InvalidOperationException("stale Steward generation/attempt/version");\n    }}\n\n    public static void RequireSafeRetry(ExternalOperationReceipt receipt)\n    {{\n        if (receipt.Delivery == StewardDeliveryState.DeliveryUnknown && receipt.RetryDisposition != StewardRetryDisposition.ReconcileFirst)\n            throw new InvalidOperationException("delivery-unknown requires reconciliation before retry");\n    }}\n}}\n'''


def steward_files(language: str, identity: str, server_name: str, steward_id: str, profile: str) -> dict[str, str]:
    if profile not in PROFILES:
        raise ValueError(f"unsupported profile: {profile}")
    if language == "python":
        base = _load_module(MCP_TOOLS / "generate_python_server.py", "ai_skills_mcp_python_generator")
        files = dict(base.project_files(identity, server_name))
        files[f"src/{identity}/steward_runtime.py"] = _python_runtime(identity)
        files["tests/test_steward_runtime.py"] = _python_test(identity)
    elif language == "dotnet":
        base = _load_module(MCP_TOOLS / "generate_dotnet_server.py", "ai_skills_mcp_dotnet_generator")
        files = dict(base.project_files(identity, server_name))
        files[f"src/{identity}.Mcp.Domain/StewardContracts.cs"] = _dotnet_contracts(identity)
    else:
        raise ValueError("language must be python or dotnet")

    overlay = {
        "steward/steward-profile.yaml": _profile(steward_id, profile),
        "steward/fault-injection.yaml": yaml.safe_dump({"schema_version": 1, "fault_points": ["after-reservation", "after-dispatch", "before-handle-persist", "before-result-persist", "before-terminal-publication"]}, sort_keys=False),
        "steward/README.md": "# Steward runtime\n\nThis directory is the durable control-plane overlay. Keep MCP transport policy in the canonical server kernel and domain workflow policy behind semantic ports. Test restart, delivery ambiguity, stale generations, and exact-artifact behavior before acceptance.\n",
    }
    for contract_name in STEWARD_CONTRACTS:
        overlay[f"steward/contracts/{contract_name}"] = (CONTRACTS / contract_name).read_text(encoding="utf-8")
    collisions = sorted(set(files) & set(overlay))
    if collisions:
        raise ValueError("Steward overlay collides with base generator: " + ", ".join(collisions))
    files.update(overlay)
    return files


def generate_project(destination: Path, *, language: str, identity: str, server_name: str, steward_id: str, profile: str) -> list[Path]:
    files = steward_files(language, identity, server_name, steward_id, profile)
    expanded = destination.expanduser()
    if os.path.lexists(expanded):
        raise FileExistsError(expanded)
    parent = expanded.parent.resolve(strict=False)
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / expanded.name
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=parent))
    try:
        for relative, content in sorted(files.items()):
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
        if os.path.lexists(destination):
            raise FileExistsError(destination)
        os.rename(staging, destination)
        staging = None  # type: ignore[assignment]
    finally:
        if staging is not None and staging.exists():
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
    generated = generate_project(args.destination, language=args.language, identity=args.identity, server_name=args.name, steward_id=args.steward_id, profile=args.profile)
    print(f"generated {len(generated)} files in {args.destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
