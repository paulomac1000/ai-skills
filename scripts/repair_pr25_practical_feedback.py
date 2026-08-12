#!/usr/bin/env python3
"""Apply practical consumer-driven improvements to PR 25; deleted before final commit."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


write(
    "skills/mcp-server-architect/tools/inspect_existing_project.py",
    r'''#!/usr/bin/env python3
"""Inspect an existing repository without executing or modifying consumer code."""

from __future__ import annotations

import argparse
import json
import os
import stat
import tomllib
from pathlib import Path
from typing import Any

MAX_FILES = 600
MAX_FILE_BYTES = 512 * 1024
MAX_TOTAL_BYTES = 12 * 1024 * 1024
IGNORED_PARTS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "bin",
    "obj",
    "__pycache__",
    ".pytest_cache",
}
TEXT_SUFFIXES = {".py", ".toml", ".txt", ".ini", ".yaml", ".yml", ".md", ".json"}
HTTP_DEPENDENCIES = {"requests", "httpx", "aiohttp", "urllib3"}


def _regular_text(path: Path) -> str | None:
    try:
        metadata = path.lstat()
    except OSError:
        return None
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        return None
    if metadata.st_size > MAX_FILE_BYTES:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _source_corpus(root: Path) -> tuple[str, int, int]:
    chunks: list[str] = []
    total = 0
    files = 0
    for path in sorted(root.rglob("*")):
        if files >= MAX_FILES or total >= MAX_TOTAL_BYTES:
            break
        if IGNORED_PARTS.intersection(path.parts) or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = _regular_text(path)
        if text is None:
            continue
        encoded_size = len(text.encode("utf-8"))
        if total + encoded_size > MAX_TOTAL_BYTES:
            break
        chunks.append(text)
        total += encoded_size
        files += 1
    return "\n".join(chunks).casefold(), files, total


def _pyproject(root: Path) -> dict[str, Any]:
    path = root / "pyproject.toml"
    text = _regular_text(path)
    if text is None:
        return {}
    try:
        value = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _dependency_names(project: dict[str, Any], root: Path) -> set[str]:
    names: set[str] = set()
    raw_project = project.get("project")
    if isinstance(raw_project, dict):
        dependencies = raw_project.get("dependencies")
        if isinstance(dependencies, list):
            for raw in dependencies:
                if not isinstance(raw, str):
                    continue
                token = raw.strip().split("[", 1)[0]
                for separator in ("==", ">=", "<=", "~=", "!=", ">", "<", ";", " "):
                    token = token.split(separator, 1)[0]
                if token:
                    names.add(token.casefold().replace("_", "-"))
    for candidate in sorted(root.glob("requirements*.txt")) + sorted(root.glob("requirements*.in")):
        text = _regular_text(candidate)
        if text is None:
            continue
        for line in text.splitlines():
            value = line.strip()
            if not value or value.startswith(("#", "-")):
                continue
            token = value
            for separator in ("==", ">=", "<=", "~=", "!=", ">", "<", ";", " "):
                token = token.split(separator, 1)[0]
            if token:
                names.add(token.casefold().replace("_", "-"))
    return names


def _project_version(project: dict[str, Any]) -> str | None:
    raw_project = project.get("project")
    if not isinstance(raw_project, dict):
        return None
    value = raw_project.get("version")
    return value.strip() if isinstance(value, str) and value.strip() else None


def inspect_repository(repository_root: Path) -> dict[str, Any]:
    """Return bounded source-derived facts and a progressive adoption plan."""
    root = repository_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("repository root must be a directory")
    project = _pyproject(root)
    dependencies = _dependency_names(project, root)
    corpus, scanned_files, scanned_bytes = _source_corpus(root)

    if "fastmcp" in dependencies or "fastmcp-slim" in dependencies:
        sdk_profile = "python-fastmcp-package"
    elif "mcp" in dependencies:
        sdk_profile = "python-official-mcp"
    else:
        sdk_profile = "unknown"

    has_external_upstream = bool(HTTP_DEPENDENCIES.intersection(dependencies)) or any(
        marker in corpus for marker in ("requests.get(", "requests.post(", "httpx.", "aiohttp.")
    )
    has_external_tests = (root / "tests/external").is_dir() or any(
        marker in corpus for marker in ("pytest.mark.external", '"external:"', "'external:'")
    )
    pyproject_text = _regular_text(root / "pyproject.toml") or ""
    external_default_excluded = "not external" in pyproject_text.casefold()
    upstream_contract = (root / "upstream-contract.yaml").is_file()
    live_policy = (root / "live-backend-test-policy.yaml").is_file()
    has_stdio = "stdio" in corpus
    has_streamable_http = any(marker in corpus for marker in ("streamable_http", "streamable-http"))
    has_legacy_sse = any(marker in corpus for marker in ("/sse", "legacy sse", "http+sse"))
    destructive_signal = any(
        marker in corpus
        for marker in (
            "operation_kind: destructive",
            'operation_kind="destructive"',
            'operation_kind = "destructive"',
            "delete_",
            "remove_",
        )
    )
    write_signal = destructive_signal or any(
        marker in corpus
        for marker in (
            "operation_kind: write",
            'operation_kind="write"',
            'operation_kind = "write"',
            "create_",
            "update_",
            "put_",
        )
    )

    facts: dict[str, Any] = {
        "language": "python" if project else "unknown",
        "sdk_profile": sdk_profile,
        "project_version": _project_version(project),
        "packaged": bool(project),
        "containerized": any((root / name).is_file() for name in ("Dockerfile", "Containerfile")),
        "github_actions": (root / ".github/workflows").is_dir(),
        "external_upstream": has_external_upstream,
        "external_tests": has_external_tests,
        "external_tests_default_excluded": external_default_excluded,
        "upstream_contract_present": upstream_contract,
        "live_backend_policy_present": live_policy,
        "transports": {
            "stdio": has_stdio,
            "streamable_http": has_streamable_http,
            "legacy_http_sse_signal": has_legacy_sse,
        },
        "capabilities": {
            "write_signal": write_signal,
            "destructive_signal": destructive_signal,
        },
    }

    upstream_status = "not-applicable"
    if has_external_upstream:
        upstream_status = "verified" if upstream_contract else "required"
    live_status = "not-applicable"
    if has_external_tests:
        live_status = "declared" if live_policy else "needs-policy"

    unknowns: list[str] = []
    if sdk_profile == "unknown":
        unknowns.append("MCP SDK package identity was not resolved from package metadata")
    if has_external_upstream and not upstream_contract:
        unknowns.append("external upstream contract is unobserved; probe the real boundary before adapter refactoring")
    if has_external_tests and not external_default_excluded:
        unknowns.append("external tests are not visibly deselected by default")
    if has_external_tests and not live_policy:
        unknowns.append("live-backend safety policy is missing")

    routes = ["STANDARD.md", "references/testing-strategy.md"]
    if sdk_profile == "python-fastmcp-package":
        routes.append("references/python-fastmcp-package.md")
    elif sdk_profile == "python-official-mcp":
        routes.append("references/python-official-mcp-sdk.md")
    if has_external_upstream:
        routes.append("references/upstream-contract-discovery.md")

    return {
        "format": "ai-skills-adoption-discovery",
        "schema_version": 1,
        "facts": facts,
        "plan": {
            "discovery": "complete",
            "upstream_contract": upstream_status,
            "live_backend_safety": live_status,
            "implementation": "not-evaluated",
            "local_verification": "not-evaluated",
            "provider_verification": "not-evaluated",
            "acceptance": "not-evaluated",
        },
        "required_read_set": routes,
        "unknowns": unknowns,
        "scan": {"files": scanned_files, "bytes": scanned_bytes},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    document = inspect_repository(args.repository)
    serialized = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(serialized, end="")
    else:
        if os.path.lexists(args.output):
            parser.error("output already exists; refusing to overwrite")
        args.output.write_text(serialized, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
)

write(
    "skills/mcp-server-architect/tools/check_consumer_canaries.py",
    r'''#!/usr/bin/env python3
"""Validate source-only adoption discovery against exact real-consumer revisions."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

from inspect_existing_project import inspect_repository

REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
FULL_SHA = re.compile(r"[0-9a-f]{40}")
CANARY_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")


def _run(argv: list[str], *, cwd: Path, timeout: int = 120) -> None:
    environment = dict(os.environ)
    environment.update({"GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1"})
    subprocess.run(  # noqa: S603 - fixed git executable and validated repository/SHA inputs.
        argv,
        cwd=cwd,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _materialize(repository: str, revision: str, target: Path) -> None:
    if REPOSITORY.fullmatch(repository) is None or FULL_SHA.fullmatch(revision) is None:
        raise ValueError("consumer canary requires owner/name and a full lowercase commit SHA")
    target.mkdir(parents=True, exist_ok=False)
    _run(["git", "init", "-q"], cwd=target)
    _run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "remote",
            "add",
            "origin",
            f"https://github.com/{repository}.git",
        ],
        cwd=target,
    )
    _run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "fetch",
            "--depth=1",
            "--no-tags",
            "origin",
            revision,
        ],
        cwd=target,
    )
    _run(["git", "-c", "core.hooksPath=/dev/null", "checkout", "-q", "--detach", "FETCH_HEAD"], cwd=target)
    completed = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "HEAD"],
        cwd=target,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.stdout.strip() != revision:
        raise ValueError("materialized consumer revision does not match the canary pin")


def _lookup(document: dict[str, Any], dotted: str) -> Any:
    value: Any = document
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            raise KeyError(dotted)
        value = value[part]
    return value


def check_catalog(catalog_path: Path, workspace: Path, *, materialize: bool) -> list[str]:
    raw = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != 1:
        return ["consumer canary catalog must use schema_version 1"]
    canaries = raw.get("canaries")
    if not isinstance(canaries, list) or not canaries:
        return ["consumer canary catalog must contain canaries"]
    findings: list[str] = []
    for index, entry in enumerate(canaries):
        if not isinstance(entry, dict):
            findings.append(f"canaries[{index}] must be an object")
            continue
        canary_id = str(entry.get("id") or "")
        repository = str(entry.get("repository") or "")
        revision = str(entry.get("revision") or "")
        if CANARY_ID.fullmatch(canary_id) is None:
            findings.append(f"canaries[{index}].id is invalid")
            continue
        if REPOSITORY.fullmatch(repository) is None or FULL_SHA.fullmatch(revision) is None:
            findings.append(f"canaries[{index}] must pin owner/name at an immutable full SHA")
            continue
        target = workspace / canary_id
        if not target.exists():
            if not materialize:
                findings.append(f"{canary_id}: workspace is missing")
                continue
            _materialize(repository, revision, target)
        discovery = inspect_repository(target)
        expected = entry.get("expected")
        if not isinstance(expected, dict) or not expected:
            findings.append(f"{canary_id}: expected facts are missing")
            continue
        for dotted, expected_value in sorted(expected.items()):
            try:
                observed = _lookup(discovery, dotted)
            except KeyError:
                findings.append(f"{canary_id}: expected path {dotted!r} was not discovered")
                continue
            if observed != expected_value:
                findings.append(
                    f"{canary_id}: {dotted} expected {expected_value!r}, observed {observed!r}"
                )
        report = workspace / f"{canary_id}.discovery.json"
        report.write_text(json.dumps(discovery, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=Path("contracts/consumer-canaries.yaml"))
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--no-materialize", action="store_true")
    args = parser.parse_args(argv)
    args.workspace.mkdir(parents=True, exist_ok=True)
    findings = check_catalog(args.catalog, args.workspace, materialize=not args.no_materialize)
    for finding in findings:
        print(f"ERROR: {finding}")
    print(f"consumer canary findings: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
)

write(
    "contracts/consumer-canaries.yaml",
    '''schema_version: 1
canaries:
  - id: home-automation-fastmcp
    repository: paulomac1000/ha-mcp-readonly
    revision: 4dd4adaec2ac9a3f7b39edb4f208fd53a6e6703c
    expected:
      facts.language: python
      facts.sdk_profile: python-fastmcp-package
      facts.project_version: 2.0.0
      facts.packaged: true
      facts.containerized: true
      facts.github_actions: true
      facts.external_upstream: true
      plan.upstream_contract: required
  - id: legacy-financial-official-sdk
    repository: paulomac1000/kontomierz-mcp
    revision: c1030d5e922a4eeae45287295627c88396cf47fa
    expected:
      facts.language: python
      facts.sdk_profile: python-official-mcp
      facts.project_version: 2.0.0
      facts.packaged: true
      facts.containerized: true
      facts.github_actions: true
      facts.external_upstream: true
      facts.external_tests: true
      facts.external_tests_default_excluded: true
      plan.upstream_contract: required
      plan.live_backend_safety: needs-policy
''',
)

write(
    "contracts/upstream-contract.schema.json",
    '''{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/paulomac1000/ai-skills/blob/main/contracts/upstream-contract.schema.json",
  "title": "Observed upstream integration contract",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "upstream", "observations"],
  "properties": {
    "schema_version": {"const": 1},
    "upstream": {
      "type": "object",
      "additionalProperties": false,
      "required": ["name", "classification"],
      "properties": {
        "name": {"type": "string", "minLength": 1, "maxLength": 128},
        "classification": {"enum": ["documented", "legacy", "poorly-documented", "unknown"]}
      }
    },
    "observations": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["operation", "method", "endpoint", "request_encoding", "success_statuses", "response_body", "credential_placement", "confidence", "evidence"],
        "properties": {
          "operation": {"type": "string", "pattern": "^[a-z0-9][a-z0-9._-]{0,127}$"},
          "method": {"enum": ["GET", "POST", "PUT", "PATCH", "DELETE", "OTHER"]},
          "endpoint": {"type": "string", "minLength": 1, "maxLength": 512},
          "request_encoding": {"enum": ["none", "json", "form", "multipart", "query", "other"]},
          "required_fields": {"type": "array", "uniqueItems": true, "items": {"type": "string", "minLength": 1, "maxLength": 128}},
          "date_formats": {"type": "array", "uniqueItems": true, "items": {"type": "string", "minLength": 1, "maxLength": 64}},
          "success_statuses": {"type": "array", "minItems": 1, "uniqueItems": true, "items": {"type": "integer", "minimum": 100, "maximum": 599}},
          "response_body": {"enum": ["json", "empty", "text", "binary", "mixed"]},
          "pagination": {
            "type": "object",
            "additionalProperties": false,
            "required": ["model", "termination"],
            "properties": {
              "model": {"type": "string", "minLength": 1, "maxLength": 128},
              "termination": {"type": "string", "minLength": 1, "maxLength": 256}
            }
          },
          "create_identity": {"type": "string", "minLength": 1, "maxLength": 256},
          "delete_semantics": {"type": "string", "minLength": 1, "maxLength": 256},
          "retry_hint": {"type": "string", "minLength": 1, "maxLength": 256},
          "credential_placement": {"enum": ["none", "header", "query", "body", "other"]},
          "confidence": {"enum": ["observed", "recorded", "documented", "inferred"]},
          "evidence": {"type": "array", "minItems": 1, "uniqueItems": true, "items": {"type": "string", "minLength": 1, "maxLength": 512}}
        }
      }
    }
  }
}
''',
)

write(
    "contracts/validate_upstream_contract.py",
    r'''#!/usr/bin/env python3
"""Validate observed upstream contracts before adapter implementation."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

DEFAULT_SCHEMA = Path(__file__).with_name("upstream-contract.schema.json")
MAX_BYTES = 512 * 1024
SECRET_KEYS = {"token", "password", "secret", "api_key", "apikey", "credential"}


def _load(path: Path) -> Mapping[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("upstream contract must be a regular non-symlink file")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError(f"upstream contract exceeds {MAX_BYTES} bytes")
    text = path.read_text(encoding="utf-8")
    try:
        value = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"invalid upstream contract syntax: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ValueError("upstream contract root must be an object")
    return value


def _contains_secret_key(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).casefold().replace("-", "_")
            if normalized in SECRET_KEYS:
                return True
            if _contains_secret_key(child):
                return True
    elif isinstance(value, list):
        return any(_contains_secret_key(item) for item in value)
    return False


def validate_contract(path: Path, schema_path: Path = DEFAULT_SCHEMA, *, require_observed: bool = False) -> list[str]:
    try:
        schema = _load(schema_path)
        document = _load(path)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return [str(exc)]
    findings = [
        f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
        for error in sorted(
            Draft202012Validator(schema).iter_errors(document),
            key=lambda item: tuple(str(part) for part in item.absolute_path),
        )
    ]
    if findings:
        return findings
    observations = document.get("observations")
    assert isinstance(observations, list)
    seen: set[str] = set()
    for index, raw in enumerate(observations):
        assert isinstance(raw, Mapping)
        operation = str(raw.get("operation") or "")
        if operation in seen:
            findings.append(f"observations.{index}.operation: duplicate operation {operation}")
        seen.add(operation)
        if require_observed and raw.get("confidence") == "inferred":
            findings.append(f"observations.{index}.confidence: inferred claims cannot satisfy observed-contract acceptance")
        if _contains_secret_key(raw):
            findings.append(f"observations.{index}: secret values do not belong in upstream contract evidence")
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--require-observed", action="store_true")
    args = parser.parse_args(argv)
    findings = validate_contract(args.contract, args.schema, require_observed=args.require_observed)
    for finding in findings:
        print(f"ERROR: {finding}")
    print(f"upstream contract findings: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
)

write(
    "contracts/live-backend-test-policy.schema.json",
    '''{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/paulomac1000/ai-skills/blob/main/contracts/live-backend-test-policy.schema.json",
  "title": "Live backend test safety policy",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version", "default_execution", "mutations"],
  "properties": {
    "schema_version": {"const": 1},
    "default_execution": {"const": "excluded"},
    "mutations": {
      "type": "object",
      "additionalProperties": false,
      "required": ["enabled_by_default", "independent_opt_ins", "credential_access", "unique_namespace", "cleanup"],
      "properties": {
        "enabled_by_default": {"const": false},
        "independent_opt_ins": {"type": "integer", "minimum": 2},
        "credential_access": {"const": "after-opt-in"},
        "unique_namespace": {"const": true},
        "cleanup": {
          "type": "object",
          "additionalProperties": false,
          "required": ["capture_created_ids", "reconcile_by_marker", "report_unreconciled"],
          "properties": {
            "capture_created_ids": {"const": true},
            "reconcile_by_marker": {"const": true},
            "report_unreconciled": {"const": true}
          }
        }
      }
    }
  }
}
''',
)

write(
    "contracts/validate_live_backend_test_policy.py",
    r'''#!/usr/bin/env python3
"""Validate fail-closed live-backend test safety policy."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

DEFAULT_SCHEMA = Path(__file__).with_name("live-backend-test-policy.schema.json")
MAX_BYTES = 128 * 1024


def _load(path: Path) -> Mapping[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("live-backend policy must be a regular non-symlink file")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError(f"live-backend policy exceeds {MAX_BYTES} bytes")
    text = path.read_text(encoding="utf-8")
    try:
        value = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"invalid live-backend policy syntax: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ValueError("live-backend policy root must be an object")
    return value


def validate_policy(path: Path, schema_path: Path = DEFAULT_SCHEMA) -> list[str]:
    try:
        schema = _load(schema_path)
        document = _load(path)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return [str(exc)]
    return [
        f"{'.'.join(str(part) for part in error.absolute_path) or '$'}: {error.message}"
        for error in sorted(
            Draft202012Validator(schema).iter_errors(document),
            key=lambda item: tuple(str(part) for part in item.absolute_path),
        )
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy", type=Path)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    args = parser.parse_args(argv)
    findings = validate_policy(args.policy, args.schema)
    for finding in findings:
        print(f"ERROR: {finding}")
    print(f"live-backend policy findings: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
)

write(
    "skills/mcp-server-architect/templates/upstream-contract.yaml.template",
    '''schema_version: 1
upstream:
  name: replace-with-upstream-name
  classification: unknown
observations:
  - operation: replace-with-operation
    method: GET
    endpoint: /replace-with-observed-endpoint
    request_encoding: none
    required_fields: []
    date_formats: []
    success_statuses: [200]
    response_body: json
    credential_placement: header
    confidence: inferred
    evidence:
      - replace-with-recording-probe-or-authoritative-document-reference
''',
)

write(
    "skills/mcp-server-architect/templates/live-backend-test-policy.yaml.template",
    '''schema_version: 1
default_execution: excluded
mutations:
  enabled_by_default: false
  independent_opt_ins: 2
  credential_access: after-opt-in
  unique_namespace: true
  cleanup:
    capture_created_ids: true
    reconcile_by_marker: true
    report_unreconciled: true
''',
)

write(
    "skills/mcp-server-architect/references/upstream-contract-discovery.md",
    '''---
description: Discovery-first workflow for legacy, external, or poorly documented upstream integrations.
doc_id: reference.mcp-upstream-contract-discovery
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Run the read-only repository inspector, record controlled upstream observations, validate upstream-contract.yaml, and prove public canonical inputs do not leak the upstream dialect.
---

# Upstream contract discovery

## Entry gate

For an existing adapter, discover the real upstream contract before restructuring MCP architecture whenever the backend is external, legacy, poorly documented, or contradicted by existing tests. Do not infer body encoding, date dialect, pagination, success payload shape, returned identity, retry safety, or credential placement from client code alone.

Start with `python skills/mcp-server-architect/tools/inspect_existing_project.py <repository>`. If the plan reports `upstream_contract: required`, create `upstream-contract.yaml` from the template and validate it with `python contracts/validate_upstream_contract.py upstream-contract.yaml --require-observed` before changing the adapter contract.

## Observed facts

Record observations, not desired architecture. Each operation binds method, endpoint, request encoding, required fields, success statuses, response-body shape, credential placement, and evidence. Add date dialect, pagination termination, create identity, delete semantics, and retry hints when they apply. Secrets and protected payloads never belong in this document.

`confidence: inferred` is useful during discovery but cannot satisfy observed-contract acceptance. Promote a claim only after a controlled probe, recording, test container, emulator, or authoritative provider document demonstrates it.

## Public boundary

The MCP public contract remains canonical even when the upstream dialect is not. Test the full boundary `public input -> canonical domain value -> upstream adapter -> upstream dialect`, and add a negative test proving backend-only date, money, identifier, enum, or field-name formats are rejected at the public MCP input when they are not intentionally public.

## Safe live probes

Real-system probes are separate from ordinary tests. Live mutations are excluded by default, require at least two independent opt-ins, delay credential access until after those opt-ins, use a unique test namespace, capture created identities, reconcile after partially successful creates, and report every resource whose cleanup cannot be confirmed. Use the live-backend policy template and validator as a machine-readable floor; project tests must still prove the policy is actually enforced.
''',
)

write(
    "skills/mcp-server-architect/references/consumer-driven-validation.md",
    '''---
description: Consumer-driven validation model that turns real downstream migrations into permanent ai-skills regression canaries.
doc_id: reference.mcp-consumer-driven-validation
type: reference
status: active
rigor: operational
owners: [repository-maintainers]
verification: Run the consumer-canary CI job against every immutable revision in contracts/consumer-canaries.yaml and review drift before changing normative migration guidance.
---

# Consumer-driven validation

## Why canaries exist

Synthetic generators prove a baseline, but they do not prove that an existing repository can be discovered and migrated without false assumptions. Reusable findings from real migrations therefore become one of three artifacts: a standard invariant, an executable validator, or an immutable external consumer canary. New prose without one of those enforcement paths is incomplete remediation.

## Cheap source canary

`check_consumer_canaries.py` fetches exact public commit SHAs, never executes consumer code, and runs the bounded read-only inspector. The catalog records only facts that the inspector must continue to discover correctly. This lane is safe for every pull request and catches regressions in SDK routing, upstream discovery, packaging, external-test discovery, and progressive planning.

The canary catalog is intentionally the only repository file allowed to contain the concrete consumer repository names. Those names are regression evidence, not normative examples or domain-specific guidance.

## Full consumer exercise

A heavier consumer exercise may run on a reviewed immutable consumer revision when it executes without protected credentials. It should build the consumer artifact, prove imports come from the installed artifact, use the public MCP composition and official client, and validate generated assessment/evidence records. Live backend prerequisites remain `external prerequisite unavailable / not executed`; absence of credentials is never converted into a pass.

Never give assessed consumer code provider credentials used to approve its own evidence. Provider correlation and acceptance remain separate trusted steps.

## Promotion rule

A consumer incident is generalized only after reproducing the actual failure. The preferred loop is `consumer failure -> minimal fact discovery -> generic invariant -> executable check -> consumer canary -> exact-head repository gate`. A bot suggestion or theoretical edge case without a reproduced contract violation does not outrank this loop.
''',
)

write(
    "scripts/check_release_version.py",
    r'''#!/usr/bin/env python3
"""Require stable skill versions to change when their shipped implementation changes."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _git_show(base: str, path: str) -> str | None:
    completed = subprocess.run(  # noqa: S603 - fixed git executable, validated revision supplied by trusted CI.
        ["git", "show", f"{base}:{path}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed.stdout if completed.returncode == 0 else None


def _changed_paths(base: str) -> set[str]:
    completed = subprocess.run(  # noqa: S603
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return {line.strip() for line in completed.stdout.splitlines() if line.strip()}


def validate_version_bumps(base: str) -> list[str]:
    changed = _changed_paths(base)
    shared_contract_change = any(path.startswith("contracts/") for path in changed)
    findings: list[str] = []
    for manifest_path in sorted((ROOT / "skills").glob("*/manifest.yaml")):
        relative = manifest_path.relative_to(ROOT).as_posix()
        current = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(current, dict) or current.get("maturity") != "stable":
            continue
        old_text = _git_show(base, relative)
        if old_text is None:
            continue
        previous = yaml.safe_load(old_text)
        if not isinstance(previous, dict):
            continue
        skill_prefix = f"skills/{manifest_path.parent.name}/"
        semantic_change = shared_contract_change or any(path.startswith(skill_prefix) for path in changed)
        if semantic_change and current.get("version") == previous.get("version"):
            findings.append(
                f"{manifest_path.parent.name}: stable shipped content changed without a skill version bump"
            )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    args = parser.parse_args(argv)
    findings = validate_version_bumps(args.base)
    for finding in findings:
        print(f"ERROR: {finding}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
)

write(
    "tests/test_practical_consumer_feedback.py",
    r'''"""Executable regressions derived from real downstream migration failures."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def inspector():
    return load_module(
        "consumer_inspector",
        ROOT / "skills/mcp-server-architect/tools/inspect_existing_project.py",
    )


def test_inspector_routes_fastmcp_and_requires_upstream_discovery(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '''[project]\nname = "sample"\nversion = "3.2.1"\ndependencies = ["fastmcp==3.4.6", "httpx==0.28.1"]\n[tool.pytest.ini_options]\naddopts = '-m "not external"'\n''',
        encoding="utf-8",
    )
    (tmp_path / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
    (tmp_path / ".github/workflows").mkdir(parents=True)
    (tmp_path / ".github/workflows/ci.yml").write_text("name: CI\n", encoding="utf-8")
    (tmp_path / "tests/external").mkdir(parents=True)
    (tmp_path / "tests/external/test_live.py").write_text("import pytest\npytestmark = pytest.mark.external\n", encoding="utf-8")
    (tmp_path / "server.py").write_text("# stdio streamable_http create_record delete_record\n", encoding="utf-8")

    result = inspector().inspect_repository(tmp_path)
    assert result["facts"]["sdk_profile"] == "python-fastmcp-package"
    assert result["facts"]["external_tests_default_excluded"] is True
    assert result["facts"]["transports"] == {
        "stdio": True,
        "streamable_http": True,
        "legacy_http_sse_signal": False,
    }
    assert result["plan"]["upstream_contract"] == "required"
    assert result["plan"]["live_backend_safety"] == "needs-policy"
    assert "references/python-fastmcp-package.md" in result["required_read_set"]


def test_inspector_recognizes_machine_readable_discovery_artifacts(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="sample"\nversion="2.0.0"\ndependencies=["mcp==2.0.0", "requests==2.34.2"]\n',
        encoding="utf-8",
    )
    (tmp_path / "upstream-contract.yaml").write_text("schema_version: 1\n", encoding="utf-8")
    result = inspector().inspect_repository(tmp_path)
    assert result["facts"]["sdk_profile"] == "python-official-mcp"
    assert result["plan"]["upstream_contract"] == "verified"


def test_upstream_contract_rejects_inference_and_embedded_secret_keys(tmp_path: Path) -> None:
    validator = load_module("upstream_contract_validator", ROOT / "contracts/validate_upstream_contract.py")
    contract = {
        "schema_version": 1,
        "upstream": {"name": "legacy-api", "classification": "legacy"},
        "observations": [
            {
                "operation": "create-item",
                "method": "POST",
                "endpoint": "/items",
                "request_encoding": "form",
                "success_statuses": [201],
                "response_body": "empty",
                "credential_placement": "query",
                "confidence": "inferred",
                "evidence": ["controlled-probe-1"],
            }
        ],
    }
    path = tmp_path / "upstream-contract.yaml"
    path.write_text(yaml.safe_dump(contract), encoding="utf-8")
    assert any("inferred" in finding for finding in validator.validate_contract(path, require_observed=True))
    contract["observations"][0]["confidence"] = "observed"
    contract["observations"][0]["api_key"] = "should-never-be-recorded"
    path.write_text(yaml.safe_dump(contract), encoding="utf-8")
    assert validator.validate_contract(path)


def test_live_backend_policy_requires_two_opt_ins_and_reconciliation(tmp_path: Path) -> None:
    validator = load_module(
        "live_policy_validator",
        ROOT / "contracts/validate_live_backend_test_policy.py",
    )
    valid = {
        "schema_version": 1,
        "default_execution": "excluded",
        "mutations": {
            "enabled_by_default": False,
            "independent_opt_ins": 2,
            "credential_access": "after-opt-in",
            "unique_namespace": True,
            "cleanup": {
                "capture_created_ids": True,
                "reconcile_by_marker": True,
                "report_unreconciled": True,
            },
        },
    }
    path = tmp_path / "live-backend-test-policy.yaml"
    path.write_text(yaml.safe_dump(valid), encoding="utf-8")
    assert validator.validate_policy(path) == []
    valid["mutations"]["independent_opt_ins"] = 1
    path.write_text(yaml.safe_dump(valid), encoding="utf-8")
    assert validator.validate_policy(path)


def test_real_consumer_canaries_are_immutable_and_source_only() -> None:
    catalog = yaml.safe_load((ROOT / "contracts/consumer-canaries.yaml").read_text(encoding="utf-8"))
    assert catalog["schema_version"] == 1
    assert len(catalog["canaries"]) >= 2
    for canary in catalog["canaries"]:
        assert len(canary["revision"]) == 40
        int(canary["revision"], 16)
        assert canary["expected"]["facts.external_upstream"] is True
    checker = (ROOT / "skills/mcp-server-architect/tools/check_consumer_canaries.py").read_text(encoding="utf-8")
    assert "inspect_repository" in checker
    assert "pytest" not in checker
    assert "subprocess.run" in checker


def test_atomic_controls_capture_practical_migration_failures() -> None:
    catalog = yaml.safe_load((ROOT / "contracts/atomic-claim-catalog.yaml").read_text(encoding="utf-8"))
    controls = {item["id"]: item for item in catalog["controls"]}
    assert controls["mcp.testing.live-backend-safety"]["applies_when"]["profiles_any"] == ["live-backend"]
    parity = controls["mcp.authorization.transport-parity"]
    assert parity["applies_when"]["profiles_all"] == ["local-stdio", "remote-http"]
    assert set(parity["applies_when"]["capabilities_any"]) == {"write", "destructive"}
    upstream = controls["mcp.upstream.contract-observed"]
    assert upstream["parent_rule_id"] == "mcp.verification.layered"


def test_consumer_discovery_document_is_valid_json(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\nversion="1.0.0"\ndependencies=[]\n', encoding="utf-8")
    document = inspector().inspect_repository(tmp_path)
    assert json.loads(json.dumps(document))["format"] == "ai-skills-adoption-discovery"
''',
)

write(
    "tests/test_contract_boundary_coverage.py",
    r'''"""Boundary coverage for policy-critical contract readers and renderers."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
import yaml

from contracts import render_rule_catalog
from contracts import validate_capability_manifest
from contracts import validate_live_backend_test_policy
from contracts import validate_upstream_contract


def test_render_rule_catalog_rejects_unsafe_source_shapes(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    source = root / "skills/demo/STANDARD.md"
    source.parent.mkdir(parents=True)
    source.write_text("# Demo\n\n## Safe heading\n", encoding="utf-8")
    catalog = root / "catalog.yaml"

    def render(source_value: object) -> None:
        catalog.write_text(
            yaml.safe_dump(
                {
                    "schema_version": 1,
                    "catalog_version": "1.0.0",
                    "skills": {"demo": {"rules": [{"id": "demo.rule", "source": source_value}]}},
                }
            ),
            encoding="utf-8",
        )
        render_rule_catalog.render_catalog(catalog, root)

    with pytest.raises(ValueError, match="one path and one anchor"):
        render("STANDARD.md")
    with pytest.raises(ValueError, match="belong to demo"):
        render("skills/other/STANDARD.md#safe-heading")
    with pytest.raises(ValueError, match="missing source anchor"):
        render("STANDARD.md#missing")
    render("STANDARD.md#safe-heading")


def test_render_rule_catalog_file_guards(tmp_path: Path) -> None:
    root = tmp_path
    regular = root / "a.md"
    regular.write_text("x", encoding="utf-8")
    assert render_rule_catalog._safe_regular_file(root, "a.md", 10) == regular
    with pytest.raises(ValueError, match="POSIX"):
        render_rule_catalog._safe_regular_file(root, "a\\b", 10)
    with pytest.raises(ValueError, match="inside"):
        render_rule_catalog._safe_regular_file(root, "../a.md", 10)
    with pytest.raises(ValueError, match="does not exist"):
        render_rule_catalog._safe_regular_file(root, "missing.md", 10)
    directory = root / "dir"
    directory.mkdir()
    with pytest.raises(ValueError, match="regular file"):
        render_rule_catalog._safe_regular_file(root, "dir", 10)
    with pytest.raises(ValueError, match="exceeds"):
        render_rule_catalog._safe_regular_file(root, "a.md", 0)
    link = root / "link.md"
    try:
        link.symlink_to(regular)
    except OSError:
        return
    with pytest.raises(ValueError, match="symlink"):
        render_rule_catalog._safe_regular_file(root, "link.md", 10)


def test_capability_manifest_loader_and_semantics(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"
    assert validate_capability_manifest.validate_manifest(missing)
    sequence = tmp_path / "sequence.yaml"
    sequence.write_text("- not-an-object\n", encoding="utf-8")
    assert any("root must be an object" in item for item in validate_capability_manifest.validate_manifest(sequence))

    write = {
        "operation_kind": "write",
        "active_state": "inactive",
        "retryable": True,
        "idempotent": True,
        "reversible": True,
        "requires_confirmation": True,
    }
    findings = validate_capability_manifest._semantic_findings(write, require_active=True)
    assert any("only active" in item for item in findings)
    assert sum("rationale" in item for item in findings) == 3
    assert any("approval record" in item for item in findings)
    write["approval"] = {"binds": ["principal"]}
    findings = validate_capability_manifest._semantic_findings(write)
    assert any("approval.binds" in item for item in findings)


def test_new_contract_loaders_reject_invalid_shapes(tmp_path: Path) -> None:
    for module, filename in (
        (validate_upstream_contract, "upstream.yaml"),
        (validate_live_backend_test_policy, "live.yaml"),
    ):
        path = tmp_path / filename
        path.write_text("- bad\n", encoding="utf-8")
        function = module.validate_contract if hasattr(module, "validate_contract") else module.validate_policy
        assert function(path)


def test_contract_validator_mains_report_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("{}\n", encoding="utf-8")
    assert validate_upstream_contract.main([str(path)]) == 1
    assert "findings" in capsys.readouterr().out
    assert validate_live_backend_test_policy.main([str(path)]) == 1
    assert "findings" in capsys.readouterr().out


def test_render_main_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "out.json"
    output.write_text("existing", encoding="utf-8")
    with pytest.raises(SystemExit):
        render_rule_catalog.main(["--output", str(output)])
''',
)

# Discovery-first workflow: do not demand a complete provider assessment before learning the repository/upstream.
replace_once(
    "skills/mcp-server-architect/SKILL.md",
    "2. For an existing server, create `migration-assessment.yaml` from `templates/migration-assessment.yaml.template`, bind it to the exact source revision, and classify every applicable rule before changing code.\n3. Resolve distribution name, exact SDK version, import namespace, registration/enumeration APIs, auth context, transport startup API, and protocol revisions from locks and production imports.\n",
    "2. For an existing server, run the read-only inspector first. Record discovered facts and unknowns before editing code; do not fabricate a complete migration assessment from source assumptions.\n3. If the repository integrates an external, legacy, or poorly documented backend, observe and validate `upstream-contract.yaml` before refactoring its adapter. Then resolve distribution name, exact SDK version, import namespace, registration/enumeration APIs, auth context, transport startup API, and protocol revisions from locks and production imports.\n",
)
replace_once(
    "skills/mcp-server-architect/SKILL.md",
    "18. Complete applicability, compatibility, behavior, waiver, rollback, residual-risk, SDK-profile, protocol-revision, transport, and exact-artifact evidence before claiming adoption.\n19. Review the selected SDK profile and cross-language incident map before claiming Python/.NET parity.\n\nRead `STANDARD.md`, `references/migration-assessment.md`, `references/capability-manifests-and-versioning.md`, `references/protocol-and-sdk-compatibility.md`, `references/transport-lifecycle-and-conformance.md`, `references/runtime-boundaries-and-artifacts.md`, the selected SDK profile, both migration simulations, `references/testing-strategy.md`, `references/security-and-operations.md`, and `references/problem-solution-matrix.md` for production work.\n",
    "18. Progress through discovered, planned, implemented, locally verified, provider verified, and accepted states. Build the full provider-backed assessment only when implementation and local exact-artifact verification are stable enough for formal adoption.\n19. Complete applicability, compatibility, behavior, waiver, rollback, residual-risk, SDK-profile, protocol-revision, transport, and exact-artifact evidence before claiming adoption.\n\nRead `STANDARD.md`, `references/testing-strategy.md`, and the SDK profile selected by package identity first. Add `references/upstream-contract-discovery.md` when an external upstream is present, and load other references only when the inspector or an applicable rule routes to them. Python consumers do not need the .NET migration simulation, and .NET consumers do not need the Python simulation; both simulations remain mandatory for ai-skills self-validation.\n",
)
replace_once(
    "skills/mcp-server-architect/SKILL.md",
    "1. Read `contracts/rule-catalog.yaml`, the atomic child-control catalog, compatibility matrix, evidence profiles, and selected skill manifest.\n2. Create one assessment per skill from `contracts/adoption-assessment.yaml.template`, bound to the exact SHA; use the assessment bundle/index for multi-skill migrations.\n3. Record maturity, deployment profiles, capabilities, SDK profile, protocol revisions, and transports; let machine applicability determine required rules and child controls.\n",
    "1. Start with read-only discovery and a lightweight conformance plan; `unknown` and `needs human decision` are valid migration states and are not waivers.\n2. Read the rule catalog, atomic child controls, compatibility matrix, evidence profiles, and selected skill manifest only after discovery identifies the relevant profile.\n3. Create the full assessment from `contracts/adoption-assessment.yaml.template` when the implementation is ready for formal local/provider verification, bind it to the exact SHA, and let machine applicability determine required rules and child controls.\n",
)

# Add operational sequencing to the normative standard without creating another unmapped H2.
replace_once(
    "skills/mcp-server-architect/STANDARD.md",
    "## Migration acceptance\n\nEvery L2+ migration produces `migration-assessment.yaml` from `templates/migration-assessment.yaml.template`, covers every `mcp-server-architect` rule in `contracts/rule-catalog.yaml`, preserves the complete normative-heading mapping in `contracts/standard-rule-map.yaml`, and follows `references/migration-assessment.md`. The assessment pins the immutable source revision, skill version, maturity target, profiles, scope, applicability matrix, implementation evidence, verification commands, preserved and intentionally changed behavior, removed legacy behavior, waivers, exact artifact identity, rollback, residual risks, and independent decision.\n",
    "## Migration acceptance\n\nExisting projects begin with bounded read-only discovery rather than a handwritten final assessment. Discovery records observed package identity, transports, packaging, external boundaries, live-test prerequisites, and unresolved facts. An external, legacy, poorly documented, or contradicted backend requires an observed `upstream-contract.yaml` before its adapter contract is redesigned. Inferred upstream behavior is a discovery state, not acceptance evidence.\n\nMigration state progresses through `discovered -> planned -> implemented -> locally-verified -> provider-verified -> accepted`. Normal unfinished work does not require a waiver. A waiver represents an intentional final deviation from an applicable rule, not the fact that implementation has not reached acceptance yet.\n\nEvery L2+ migration eventually produces `migration-assessment.yaml` from `templates/migration-assessment.yaml.template`, covers every `mcp-server-architect` rule in `contracts/rule-catalog.yaml`, preserves the complete normative-heading mapping in `contracts/standard-rule-map.yaml`, and follows `references/migration-assessment.md`. The final assessment pins the immutable source revision, skill version, maturity target, profiles, scope, applicability matrix, implementation evidence, verification commands, preserved and intentionally changed behavior, removed legacy behavior, waivers, exact artifact identity, rollback, residual risks, and independent decision.\n",
)
replace_once(
    "skills/mcp-server-architect/STANDARD.md",
    "9. upstream contract tests with controlled fakes, recordings, canaries, or test containers;\n10. Python migration simulation and .NET migration simulation across analogous archetypes;\n",
    "9. upstream contract tests with controlled fakes, recordings, canaries, or test containers; for unknown or legacy upstreams this layer moves before adapter refactoring;\n10. the implementation-language migration simulation for consumer work, while ai-skills self-validation runs both Python and .NET simulations;\n",
)
replace_once(
    "skills/mcp-server-architect/STANDARD.md",
    "A canonical independent reviewer may approve only through provider-backed evidence whose review state and commit ID match the immutable assessed revision, after every advertised transport passes official-client smoke against the exact deployment artifact and all applicable rules have executable evidence. An undocumented behavioral difference or unresolved normative conflict is a migration defect.\n",
    "A canonical independent reviewer may approve only through provider-backed evidence whose review state and commit ID match the immutable assessed revision, after every advertised transport passes official-client smoke against the exact deployment artifact and all applicable rules have executable evidence. Runtime risk and publication exposure are separate axes: destructive local-single-user capabilities still require strong runtime authorization, but independent protected-release authority is driven by maturity and actual distribution/exposure rather than the mere presence of a delete operation. An undocumented behavioral difference or unresolved normative conflict is a migration defect.\n",
)

# Testing strategy: turn two real incidents into executable policy guidance.
replace_once(
    "skills/mcp-server-architect/references/testing-strategy.md",
    "### Upstream contract\n\nUse fakes, mock HTTP handlers, recorded fixtures, emulators, browser fixtures, canaries, or Testcontainers according to the integration. Verify timeout, cancellation, host identity, credential placement, status mapping, retry hints, pagination, ambiguous completion, UI drift, and partial failure rather than mocking the final return value.\n",
    "### Upstream contract\n\nFor an external, legacy, poorly documented, or contradicted backend, this is an entry gate before adapter refactoring. First record the observed contract with `upstream-contract.yaml`; do not infer JSON/form encoding, localized dates, pagination termination, empty success bodies, returned create identity, delete semantics, or retry safety from existing client code.\n\nUse fakes, mock HTTP handlers, recorded fixtures, emulators, browser fixtures, canaries, or Testcontainers according to the integration. Verify timeout, cancellation, host identity, credential placement, status mapping, retry hints, pagination, ambiguous completion, UI drift, and partial failure rather than mocking the final return value. Public canonical values and upstream dialects have a negative boundary test so localized dates, money, identifiers, enums, or field names do not leak back into the MCP contract unintentionally.\n",
)
replace_once(
    "skills/mcp-server-architect/references/testing-strategy.md",
    "Keep generator, unit, integration, smoke, e2e, conformance, live-backend, browser, artifact, and migration suites separately visible. A skipped suite declares its prerequisite and does not contribute misleading coverage.\n",
    "Keep generator, unit, integration, smoke, e2e, conformance, live-backend, browser, artifact, and migration suites separately visible. A skipped suite declares its prerequisite and does not contribute misleading coverage. Live-backend suites are deselected by default. Mutating live tests require at least two independent opt-ins, read credentials only after the opt-ins pass, use a unique namespace, reconcile partially successful creates, and report every cleanup that cannot be confirmed.\n",
)
replace_once(
    "skills/mcp-server-architect/references/testing-strategy.md",
    "Run both the Python migration simulation and .NET migration simulation. A new reusable finding becomes a test category here; repository-specific names and fixtures remain in implementation repositories.\n",
    "For consumer migration, run the simulation matching the selected implementation profile; cross-language simulations are routed only when a claimed parity decision needs them. ai-skills itself runs both Python and .NET simulations. A reusable real-consumer finding becomes a generic invariant plus an executable regression; exact external consumer revisions may remain in the dedicated canary catalog rather than leaking project names into normative guidance.\n",
)

# Add atomic controls sourced from the real migrations.
atomic_path = ROOT / "contracts/atomic-claim-catalog.yaml"
atomic = atomic_path.read_text(encoding="utf-8")
anchor = "  - id: mcp.response.protocol-error\n"
if anchor not in atomic:
    raise RuntimeError("atomic catalog insertion anchor missing")
controls = '''  - id: mcp.upstream.contract-observed
    parent_rule_id: mcp.verification.layered
    skill: mcp-server-architect
    source: skills/mcp-server-architect/STANDARD.md#migration-acceptance
    description: External or legacy upstream behavior is discovered from controlled observations before adapter refactoring, and inferred dialect assumptions cannot satisfy acceptance.
    applies_when: {maturity_at_least: L1, profiles_any: [external-upstream, legacy-upstream]}
    severity: blocking
    waivable: false
    required_evidence: [integration]
    test_selectors: [tests/test_practical_consumer_feedback.py::test_atomic_controls_capture_practical_migration_failures]
  - id: mcp.testing.live-backend-safety
    parent_rule_id: mcp.verification.layered
    skill: mcp-server-architect
    source: skills/mcp-server-architect/STANDARD.md#verification-layers
    description: Live-backend tests are excluded by default and mutating probes require independent opt-ins, delayed credential access, unique test identities, reconciliation, and reported cleanup failures.
    applies_when: {maturity_at_least: L1, profiles_any: [live-backend]}
    severity: blocking
    waivable: false
    required_evidence: [integration, security]
    test_selectors: [tests/test_practical_consumer_feedback.py::test_atomic_controls_capture_practical_migration_failures]
  - id: mcp.authorization.transport-parity
    parent_rule_id: mcp.authorization.server-side
    skill: mcp-server-architect
    source: skills/mcp-server-architect/STANDARD.md#authentication-and-authorization
    description: Every advertised transport enforces the same operator gate, authorization, exact capability, target, and resource policy for representative write and destructive operations.
    applies_when: {maturity_at_least: L2, profiles_all: [local-stdio, remote-http], capabilities_any: [write, destructive]}
    severity: blocking
    waivable: false
    required_evidence: [integration, security, official-client]
    test_selectors: [tests/test_practical_consumer_feedback.py::test_atomic_controls_capture_practical_migration_failures]
'''
atomic_path.write_text(atomic.replace(anchor, controls + anchor, 1), encoding="utf-8", newline="\n")

# Supported provider list must match implemented provider adapters.
replace_once(
    "contracts/evidence-profiles.yaml",
    "    provider_kinds: [github-actions, gitlab-ci, azure-pipelines, jenkins, generic-hosted]\n    maximum_maturity: L2\n",
    "    provider_kinds: [github-actions]\n    maximum_maturity: L2\n",
)
replace_once(
    "contracts/evidence-profiles.yaml",
    "    provider_kinds: [github-actions, gitlab-ci, azure-pipelines, jenkins, generic-hosted]\n    maximum_maturity: L4\n",
    "    provider_kinds: [github-actions]\n    maximum_maturity: L4\n",
)
replace_once(
    "contracts/evidence-profiles.yaml",
    "  destructive: independent-release\n",
    "  public-distribution: independent-release\n  shared-service: independent-release\n",
)

# FastMCP is now consumer-observed, not falsely repository-tested.
replace_once(
    "skills/mcp-server-architect/manifest.yaml",
    "    python-fastmcp-package:\n      distribution: fastmcp\n      import_namespace: fastmcp\n      generated: false\n      verified_baseline_versions: []\n      repository_tested_revisions: []\n",
    "    python-fastmcp-package:\n      distribution: fastmcp\n      import_namespace: fastmcp\n      generated: false\n      profile_maturity: consumer-observed\n      consumer_canary_versions: ['3.4.6']\n      verified_baseline_versions: []\n      repository_tested_revisions: []\n",
)
replace_once(
    "skills/mcp-server-architect/manifest.yaml",
    "- references/principal-and-shell-boundaries.md\n- templates/migration-assessment.yaml.template\n- tools/generate_python_server.py\n",
    "- references/principal-and-shell-boundaries.md\n- references/upstream-contract-discovery.md\n- references/consumer-driven-validation.md\n- templates/migration-assessment.yaml.template\n- templates/upstream-contract.yaml.template\n- templates/live-backend-test-policy.yaml.template\n- tools/inspect_existing_project.py\n- tools/check_consumer_canaries.py\n- tools/generate_python_server.py\n",
)

# Repository hygiene permits concrete consumer names only in the dedicated evidence catalog.
replace_once(
    "tests/test_repository.py",
    "PROJECT_SPECIFIC_TERMS = {\n",
    "PROJECT_SPECIFIC_EVIDENCE_FILES = {Path(\"contracts/consumer-canaries.yaml\")}\nPROJECT_SPECIFIC_TERMS = {\n",
)
replace_once(
    "tests/test_repository.py",
    "        lowered = text.lower()\n        assert not any(term in lowered for term in PROJECT_SPECIFIC_TERMS), path\n        relative = path.relative_to(ROOT)\n",
    "        lowered = text.lower()\n        relative = path.relative_to(ROOT)\n        if relative not in PROJECT_SPECIFIC_EVIDENCE_FILES:\n            assert not any(term in lowered for term in PROJECT_SPECIFIC_TERMS), path\n",
)

# Quality/typing targets include the new executable tooling.
replace_once(
    "scripts/quality_targets.py",
    '    "skills/mcp-server-architect/tools/generate_dotnet_server.py",\n)\nTYPE_PATHS = (\n',
    '    "skills/mcp-server-architect/tools/generate_dotnet_server.py",\n    "skills/mcp-server-architect/tools/inspect_existing_project.py",\n    "skills/mcp-server-architect/tools/check_consumer_canaries.py",\n    "scripts/check_release_version.py",\n)\nTYPE_PATHS = (\n',
)
replace_once(
    "scripts/quality_targets.py",
    '    "contracts/validate_skills_lock.py",\n    "contracts/write_evidence_report.py",\n',
    '    "contracts/validate_skills_lock.py",\n    "contracts/validate_upstream_contract.py",\n    "contracts/validate_live_backend_test_policy.py",\n    "contracts/write_evidence_report.py",\n',
)
replace_once(
    "scripts/quality_targets.py",
    '    "scripts/select_lock.py",\n    "skills/afds-doc-writer/validate.py",\n',
    '    "scripts/select_lock.py",\n    "scripts/check_release_version.py",\n    "skills/afds-doc-writer/validate.py",\n',
)
replace_once(
    "scripts/quality_targets.py",
    '    "skills/mcp-server-architect/tools/generate_dotnet_server.py",\n)\nBANDIT_PATHS = (\n',
    '    "skills/mcp-server-architect/tools/generate_dotnet_server.py",\n    "skills/mcp-server-architect/tools/inspect_existing_project.py",\n    "skills/mcp-server-architect/tools/check_consumer_canaries.py",\n)\nBANDIT_PATHS = (\n',
)

# Version the changed stable release instead of shipping multiple contents as 1.2.0.
for manifest_path in sorted((ROOT / "skills").glob("*/manifest.yaml")):
    text = manifest_path.read_text(encoding="utf-8")
    if "version: 1.2.0" not in text:
        raise RuntimeError(f"unexpected manifest version in {manifest_path}")
    manifest_path.write_text(text.replace("version: 1.2.0", "version: 1.3.0", 1), encoding="utf-8", newline="\n")
replace_once("contracts/rule-catalog.yaml", "catalog_version: 1.2.0\n", "catalog_version: 1.3.0\n")
replace_once("contracts/atomic-claim-catalog.yaml", "catalog_version: 1.2.0\n", "catalog_version: 1.3.0\n")
replace_once(
    "README.md",
    "The current repository release is `1.2.0`. All bundled skills are published with `maturity: stable` and are intended for production adoption.",
    "The current repository release is `1.3.0`. All bundled skills are published with `maturity: stable` and are intended for production adoption.",
)
replace_once(
    "CHANGELOG.md",
    "## Unreleased\n",
    "## 1.3.0 - 2026-08-12\n",
)
replace_once(
    "CHANGELOG.md",
    "### Added\n\n",
    "### Added\n\n- Added consumer-driven adoption discovery, immutable external consumer canaries, observed upstream-contract validation, and live-backend mutation-safety contracts derived from real MCP migrations.\n- Added transport-by-capability authorization parity, profile-specific FastMCP consumer evidence, and a stable-version drift gate so changed stable skill contents cannot continue to identify as the previous release.\n",
)

# CI: exact-head version drift check plus source-only real consumer canaries.
ci_path = ROOT / ".github/workflows/ci.yml"
ci = ci_path.read_text(encoding="utf-8")
exact_anchor = '''      - name: Verify exact branch head
        shell: bash
        env:
          EXPECTED_SHA: ${{ github.event.pull_request.head.sha }}
        run: test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"
      - name: Execute complete local gate on exact head
'''
exact_replacement = '''      - name: Verify exact branch head
        shell: bash
        env:
          EXPECTED_SHA: ${{ github.event.pull_request.head.sha }}
        run: test "$(git rev-parse HEAD)" = "$EXPECTED_SHA"
      - name: Verify stable release versions changed with shipped contracts
        env:
          BASE_SHA: ${{ github.event.pull_request.base.sha }}
        run: |
          git fetch --no-tags --depth=1 origin "$BASE_SHA"
          python scripts/check_release_version.py --base "$BASE_SHA"
      - name: Execute complete local gate on exact head
'''
if ci.count(exact_anchor) != 1:
    raise RuntimeError("exact-head CI anchor missing")
ci = ci.replace(exact_anchor, exact_replacement, 1)
job_anchor = "\n  compatibility-python:\n"
consumer_job = '''
  consumer-canaries:
    runs-on: ubuntu-24.04
    timeout-minutes: 12
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
        with:
          ref: ${{ github.event.pull_request.head.sha || github.sha }}
          fetch-depth: 1
          persist-credentials: false
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97
        with:
          python-version: "3.12"
          architecture: x64
          cache: pip
          cache-dependency-path: requirements-dev-linux-x64-py312.lock
      - run: python scripts/install_locked.py
      - name: Inspect immutable real-consumer canaries without executing them
        run: >-
          python skills/mcp-server-architect/tools/check_consumer_canaries.py
          --catalog contracts/consumer-canaries.yaml
          --workspace "${RUNNER_TEMP}/ai-skills-consumer-canaries"
      - name: Upload consumer discovery reports
        if: always()
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a
        with:
          name: consumer-canary-discovery-${{ github.run_id }}
          path: ${{ runner.temp }}/ai-skills-consumer-canaries/*.discovery.json
          if-no-files-found: error
          retention-days: 30
'''
if ci.count(job_anchor) != 1:
    raise RuntimeError("compatibility job anchor missing")
ci = ci.replace(job_anchor, consumer_job + job_anchor, 1)
ci_path.write_text(ci, encoding="utf-8", newline="\n")

# Manifest-based release behavior and consumer-driven mechanics are now explicit in README.
replace_once(
    "README.md",
    "- Record reusable lessons from real failures in the canonical standard or playbook.\n",
    "- Record reusable lessons from real failures as a canonical invariant plus an executable validator, regression, or immutable consumer canary.\n",
)
