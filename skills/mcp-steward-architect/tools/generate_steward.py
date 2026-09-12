#!/usr/bin/env python3
"""Generate a durable Steward overlay on the canonical MCP server baseline."""

from __future__ import annotations

import argparse
import importlib.util
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


def _profile(steward_id: str, profile: str, *, durability_profile: str) -> str:
    constrained_file = durability_profile == "constrained-file"
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
        "subject_identity": {
            "required_dimensions": ["target"],
            "freshness_dimensions": [],
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
        "completion": {"obligations": [], "handoff_digest": "sha256"},
        "observability": {"durable_timeline": True, "doctor": True},
    }
    return yaml.safe_dump(value, sort_keys=False)


def _python_runtime() -> str:
    return '''"""Minimal durable Steward state seed; domain code should build on semantic ports."""\n\nfrom __future__ import annotations\n\nimport json\nimport sqlite3\nfrom pathlib import Path\nfrom typing import Any\n\n\nclass StewardStore:\n    def __init__(self, path: Path) -> None:\n        self.path = path\n        self._initialize()\n\n    def _connect(self) -> sqlite3.Connection:\n        connection = sqlite3.connect(self.path)\n        connection.execute("PRAGMA journal_mode=WAL")\n        connection.execute("PRAGMA foreign_keys=ON")\n        return connection\n\n    def _initialize(self) -> None:\n        with self._connect() as db:\n            db.executescript(\n                """\n                CREATE TABLE IF NOT EXISTS steward_jobs (\n                    job_id TEXT PRIMARY KEY, lineage_id TEXT NOT NULL, generation INTEGER NOT NULL,\n                    attempt_id TEXT NOT NULL, version INTEGER NOT NULL, status TEXT NOT NULL,\n                    subject_json TEXT NOT NULL, heartbeat_at TEXT NOT NULL, progress_at TEXT NOT NULL\n                );\n                CREATE TABLE IF NOT EXISTS external_operations (\n                    operation_id TEXT PRIMARY KEY, job_id TEXT NOT NULL, generation INTEGER NOT NULL,\n                    attempt_id TEXT NOT NULL, request_digest TEXT NOT NULL, delivery TEXT NOT NULL,\n                    retry_disposition TEXT NOT NULL, credential_slot_id TEXT NOT NULL, remote_handle TEXT NULL,\n                    FOREIGN KEY(job_id) REFERENCES steward_jobs(job_id)\n                );\n                """\n            )\n\n    def admit(\n        self,\n        *,\n        job_id: str,\n        lineage_id: str,\n        generation: int,\n        attempt_id: str,\n        subject: dict[str, Any],\n        now: str,\n    ) -> None:\n        with self._connect() as db:\n            db.execute(\n                "INSERT INTO steward_jobs VALUES (?, ?, ?, ?, 0, 'queued', ?, ?, ?)",\n                (\n                    job_id,\n                    lineage_id,\n                    generation,\n                    attempt_id,\n                    json.dumps(subject, sort_keys=True),\n                    now,\n                    now,\n                ),\n            )\n\n    def reserve_external(\n        self,\n        *,\n        operation_id: str,\n        job_id: str,\n        generation: int,\n        attempt_id: str,\n        request_digest: str,\n        credential_slot_id: str,\n    ) -> None:\n        with self._connect() as db:\n            current = db.execute(\n                "SELECT generation, attempt_id FROM steward_jobs WHERE job_id = ?",\n                (job_id,),\n            ).fetchone()\n            if current != (generation, attempt_id):\n                raise RuntimeError("stale generation/attempt")\n            db.execute(\n                "INSERT INTO external_operations VALUES "\n                "(?, ?, ?, ?, ?, 'not-delivered', 'forbidden', ?, NULL)",\n                (\n                    operation_id,\n                    job_id,\n                    generation,\n                    attempt_id,\n                    request_digest,\n                    credential_slot_id,\n                ),\n            )\n\n    def mark_delivery_unknown(self, operation_id: str) -> None:\n        with self._connect() as db:\n            db.execute(\n                "UPDATE external_operations "\n                "SET delivery='delivery-unknown', retry_disposition='reconcile-first' "\n                "WHERE operation_id=?",\n                (operation_id,),\n            )\n\n    def receipt(self, operation_id: str) -> tuple[str, str] | None:\n        with self._connect() as db:\n            row = db.execute(\n                "SELECT delivery, retry_disposition FROM external_operations "\n                "WHERE operation_id=?",\n                (operation_id,),\n            ).fetchone()\n            return None if row is None else (str(row[0]), str(row[1]))\n'''


def _python_test(package: str) -> str:
    return f"""from pathlib import Path\n\nfrom {package}.steward_runtime import StewardStore\n\n\ndef test_receipt_is_durable_and_unknown_delivery_requires_reconciliation(\n    tmp_path: Path,\n) -> None:\n    path = tmp_path / "steward.db"\n    store = StewardStore(path)\n    store.admit(\n        job_id="j1",\n        lineage_id="l1",\n        generation=1,\n        attempt_id="a1",\n        subject={{"type": "repo", "id": "x"}},\n        now="2026-01-01T00:00:00Z",\n    )\n    store.reserve_external(\n        operation_id="op1",\n        job_id="j1",\n        generation=1,\n        attempt_id="a1",\n        request_digest="sha256:" + "0" * 64,\n        credential_slot_id="primary",\n    )\n    store.mark_delivery_unknown("op1")\n    assert StewardStore(path).receipt("op1") == (\n        "delivery-unknown",\n        "reconcile-first",\n    )\n\n\ndef test_stale_attempt_cannot_reserve_external_work(tmp_path: Path) -> None:\n    store = StewardStore(tmp_path / "steward.db")\n    store.admit(\n        job_id="j1",\n        lineage_id="l1",\n        generation=2,\n        attempt_id="a2",\n        subject={{"type": "repo", "id": "x"}},\n        now="2026-01-01T00:00:00Z",\n    )\n    try:\n        store.reserve_external(\n            operation_id="op1",\n            job_id="j1",\n            generation=1,\n            attempt_id="a1",\n            request_digest="sha256:" + "0" * 64,\n            credential_slot_id="primary",\n        )\n    except RuntimeError as exc:\n        assert "stale" in str(exc)\n    else:\n        raise AssertionError("stale attempt was admitted")\n"""


def _dotnet_contracts(namespace: str) -> str:
    return f"""using System;\n\nnamespace {namespace}.Mcp.Domain;\n\npublic enum StewardDeliveryState {{ NotDelivered, Delivered, DeliveryUnknown }}\npublic enum StewardRetryDisposition {{ Forbidden, Eligible, ReconcileFirst }}\n\npublic sealed record StewardAttemptIdentity(\n    string JobId,\n    string LineageId,\n    long Generation,\n    string AttemptId,\n    long Version);\n\npublic sealed record StewardStoredJob(\n    string JobId,\n    string LineageId,\n    long Generation,\n    string AttemptId,\n    long Version,\n    string Status);\n\npublic sealed record ExternalOperationReceipt(\n    string OperationId,\n    StewardAttemptIdentity Attempt,\n    string CapabilityIdentity,\n    string TargetIdentity,\n    string RequestDigest,\n    StewardDeliveryState Delivery,\n    StewardRetryDisposition RetryDisposition,\n    string CredentialSlotId,\n    string? RemoteHandle);\n\npublic static class StewardGuards\n{{\n    public static void RequireCurrent(\n        StewardAttemptIdentity expected,\n        StewardAttemptIdentity actual)\n    {{\n        if (expected.JobId != actual.JobId ||\n            expected.LineageId != actual.LineageId ||\n            expected.Generation != actual.Generation ||\n            expected.AttemptId != actual.AttemptId ||\n            expected.Version != actual.Version)\n        {{\n            throw new InvalidOperationException(\n                "stale Steward generation/attempt/version");\n        }}\n    }}\n\n    public static void RequireSafeRetry(ExternalOperationReceipt receipt)\n    {{\n        if (receipt.Delivery == StewardDeliveryState.DeliveryUnknown &&\n            receipt.RetryDisposition != StewardRetryDisposition.ReconcileFirst)\n        {{\n            throw new InvalidOperationException(\n                "delivery-unknown requires reconciliation before retry");\n        }}\n    }}\n}}\n"""


def _dotnet_store(namespace: str) -> str:
    return f"""using System.Text.Json;\nusing {namespace}.Mcp.Domain;\n\nnamespace {namespace}.Mcp.Server;\n\npublic sealed class StewardFileStore : IDisposable\n{{\n    private readonly string _snapshotPath;\n    private readonly FileStream _ownerLock;\n    private StewardFileSnapshot _state;\n\n    public StewardFileStore(string directory)\n    {{\n        Directory.CreateDirectory(directory);\n        _snapshotPath = Path.Combine(directory, "steward-state.json");\n        _ownerLock = new FileStream(\n            Path.Combine(directory, "steward-state.lock"),\n            FileMode.OpenOrCreate,\n            FileAccess.ReadWrite,\n            FileShare.None);\n        _state = LoadOrQuarantine();\n    }}\n\n    public void Admit(StewardStoredJob job)\n    {{\n        if (!_state.Jobs.TryAdd(job.JobId, job))\n            throw new InvalidOperationException("job already exists");\n        Save();\n    }}\n\n    public void ReserveExternal(ExternalOperationReceipt receipt)\n    {{\n        if (!_state.Jobs.TryGetValue(receipt.Attempt.JobId, out var current))\n            throw new InvalidOperationException("job not found");\n        var actual = new StewardAttemptIdentity(\n            current.JobId,\n            current.LineageId,\n            current.Generation,\n            current.AttemptId,\n            current.Version);\n        StewardGuards.RequireCurrent(receipt.Attempt, actual);\n        if (!_state.Operations.TryAdd(receipt.OperationId, receipt))\n            throw new InvalidOperationException("operation already exists");\n        Save();\n    }}\n\n    public void MarkDeliveryUnknown(string operationId)\n    {{\n        if (!_state.Operations.TryGetValue(operationId, out var receipt))\n            throw new InvalidOperationException("operation not found");\n        _state.Operations[operationId] = receipt with\n        {{\n            Delivery = StewardDeliveryState.DeliveryUnknown,\n            RetryDisposition = StewardRetryDisposition.ReconcileFirst,\n        }};\n        Save();\n    }}\n\n    public ExternalOperationReceipt? Receipt(string operationId) =>\n        _state.Operations.TryGetValue(operationId, out var receipt) ? receipt : null;\n\n    public void Dispose() => _ownerLock.Dispose();\n\n    private StewardFileSnapshot LoadOrQuarantine()\n    {{\n        if (!File.Exists(_snapshotPath))\n            return new StewardFileSnapshot();\n\n        try\n        {{\n            var value = JsonSerializer.Deserialize<StewardFileSnapshot>(\n                File.ReadAllText(_snapshotPath));\n            return value ?? throw new JsonException("null Steward snapshot");\n        }}\n        catch (JsonException)\n        {{\n            var quarantine = _snapshotPath +\n                $".corrupt-{{DateTimeOffset.UtcNow:yyyyMMddHHmmssfff}}";\n            File.Move(_snapshotPath, quarantine);\n            return new StewardFileSnapshot();\n        }}\n    }}\n\n    private void Save()\n    {{\n        var temp = _snapshotPath + $".tmp-{{Guid.NewGuid():N}}";\n        try\n        {{\n            using (var stream = new FileStream(\n                temp,\n                FileMode.CreateNew,\n                FileAccess.Write,\n                FileShare.None,\n                4096,\n                FileOptions.WriteThrough))\n            {{\n                JsonSerializer.Serialize(stream, _state);\n                stream.Flush(flushToDisk: true);\n            }}\n            File.Move(temp, _snapshotPath, overwrite: true);\n        }}\n        finally\n        {{\n            if (File.Exists(temp))\n                File.Delete(temp);\n        }}\n    }}\n\n    public sealed class StewardFileSnapshot\n    {{\n        public Dictionary<string, StewardStoredJob> Jobs {{ get; init; }} = new();\n        public Dictionary<string, ExternalOperationReceipt> Operations {{ get; init; }} = new();\n    }}\n}}\n"""


def _dotnet_smoke_regression(namespace: str) -> str:
    return f"""using {namespace}.Mcp.Domain;\nusing {namespace}.Mcp.Server;\n\ninternal static class StewardRuntimeRegressions\n{{\n    public static void Verify()\n    {{\n        var directory = Path.Combine(\n            Path.GetTempPath(),\n            "{namespace}.steward-" + Guid.NewGuid().ToString("N"));\n        Directory.CreateDirectory(directory);\n        try\n        {{\n            using (var store = new StewardFileStore(directory))\n            {{\n                store.Admit(new StewardStoredJob(\n                    "j1", "l1", 2, "a2", 0, "queued"));\n                var current = new StewardAttemptIdentity("j1", "l1", 2, "a2", 0);\n                store.ReserveExternal(new ExternalOperationReceipt(\n                    "op1",\n                    current,\n                    "reasoning:v1",\n                    "target:1",\n                    "sha256:" + new string('0', 64),\n                    StewardDeliveryState.NotDelivered,\n                    StewardRetryDisposition.Forbidden,\n                    "primary",\n                    null));\n                store.MarkDeliveryUnknown("op1");\n                var receipt = store.Receipt("op1") ??\n                    throw new InvalidOperationException("receipt not persisted");\n                if (receipt.Delivery != StewardDeliveryState.DeliveryUnknown ||\n                    receipt.RetryDisposition != StewardRetryDisposition.ReconcileFirst)\n                {{\n                    throw new InvalidOperationException(\n                        "ambiguous delivery did not fence retry");\n                }}\n\n                try\n                {{\n                    using var duplicateOwner = new StewardFileStore(directory);\n                    throw new InvalidOperationException(\n                        "constrained file store admitted a second owner");\n                }}\n                catch (IOException)\n                {{\n                    // Expected: this generated durability profile is single-owner.\n                }}\n\n                try\n                {{\n                    store.ReserveExternal(new ExternalOperationReceipt(\n                        "stale",\n                        new StewardAttemptIdentity("j1", "l1", 1, "a1", 0),\n                        "reasoning:v1",\n                        "target:1",\n                        "sha256:" + new string('1', 64),\n                        StewardDeliveryState.NotDelivered,\n                        StewardRetryDisposition.Forbidden,\n                        "primary",\n                        null));\n                    throw new InvalidOperationException("stale attempt was admitted");\n                }}\n                catch (InvalidOperationException error)\n                    when (error.Message.Contains("stale", StringComparison.Ordinal))\n                {{\n                    // Expected fencing failure.\n                }}\n            }}\n\n            using (var reopened = new StewardFileStore(directory))\n            {{\n                var recovered = reopened.Receipt("op1") ??\n                    throw new InvalidOperationException("receipt did not survive restart");\n                if (recovered.Delivery != StewardDeliveryState.DeliveryUnknown ||\n                    recovered.RetryDisposition != StewardRetryDisposition.ReconcileFirst)\n                {{\n                    throw new InvalidOperationException(\n                        "recovered receipt lost reconciliation state");\n                }}\n            }}\n        }}\n        finally\n        {{\n            if (Directory.Exists(directory))\n                Directory.Delete(directory, recursive: true);\n        }}\n    }}\n}}\n"""


def _inject_dotnet_smoke(files: dict[str, str], namespace: str) -> None:
    program_path = f"tests/{namespace}.Mcp.Smoke/Program.cs"
    marker = "await VerifyConcurrencyContractAsync();\n"
    program = files.get(program_path)
    if program is None or marker not in program:
        raise RuntimeError(
            "canonical .NET smoke entrypoint changed; Steward overlay must be reviewed"
        )
    files[program_path] = program.replace(
        marker,
        marker + "StewardRuntimeRegressions.Verify();\n",
        1,
    )
    files[f"tests/{namespace}.Mcp.Smoke/StewardRuntimeRegressions.cs"] = (
        _dotnet_smoke_regression(namespace)
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
    if language == "python":
        durability_profile = "single-node-durable"
        files[f"src/{identity}/steward_runtime.py"] = _python_runtime()
        files["tests/test_steward_runtime.py"] = _python_test(identity)
    else:
        durability_profile = "constrained-file"
        files[f"src/{identity}.Mcp.Domain/StewardContracts.cs"] = _dotnet_contracts(
            identity
        )
        files[f"src/{identity}.Mcp.Server/StewardFileStore.cs"] = _dotnet_store(
            identity
        )
        _inject_dotnet_smoke(files, identity)

    overlay = {
        "steward/steward-profile.yaml": _profile(
            steward_id,
            profile,
            durability_profile=durability_profile,
        ),
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
            "This directory is the durable control-plane overlay. Keep MCP transport "
            "policy in the canonical server kernel and domain workflow policy behind "
            "semantic ports. Test restart, delivery ambiguity, stale generations, and "
            "exact-artifact behavior before acceptance.\n"
        ),
    }
    for contract_name in STEWARD_CONTRACTS:
        overlay[f"steward/contracts/{contract_name}"] = (
            CONTRACTS / contract_name
        ).read_text(encoding="utf-8")
    collisions = sorted(set(files) & set(overlay))
    if collisions:
        raise ValueError(
            "Steward overlay collides with base generator: " + ", ".join(collisions)
        )
    files.update(overlay)
    return files


def _publish_no_replace(
    language: str,
    staging: Path,
    destination: Path,
) -> None:
    base = _base_generator(language)
    if language == "python":
        implementation = getattr(base, "_implementation", None)
        rename = getattr(implementation, "_rename_noreplace", None)
    else:
        rename = getattr(base, "_rename_noreplace", None)
    if not callable(rename):
        raise RuntimeError(
            "canonical MCP generator no-replace publication primitive is unavailable"
        )
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
    parser.add_argument(
        "--identity",
        required=True,
        help="Python package or .NET namespace",
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Human-readable MCP server name",
    )
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
