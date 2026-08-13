#!/usr/bin/env python3
"""Validate that real-use lessons are generalized into owned executable regressions."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.confined_io import confined_regular_file  # noqa: E402

SCHEMA = ROOT / "contracts/consumer-feedback.schema.json"
SELECTOR = re.compile(r"^(tests/[A-Za-z0-9_.\-/]+\.py)::(test_[A-Za-z0-9_]+)$")
_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_PYTEST_ENVIRONMENT_ALLOWLIST = {
    "COMSPEC",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "PATH",
    "PATHEXT",
    "PYTHONHASHSEED",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "TMPDIR",
    "WINDIR",
}
_PYTEST_COLLECT_SCRIPT = """
import json
import pytest
import sys

class Capture:
    def __init__(self):
        self.nodeids = []

    def pytest_collection_finish(self, session):
        self.nodeids = [item.nodeid for item in session.items]

capture = Capture()
status = pytest.main(["--collect-only", "-p", "no:cacheprovider", *sys.argv[1:]], plugins=[capture])
print("AI_SKILLS_COLLECTED=" + json.dumps(capture.nodeids, separators=(",", ":")))
raise SystemExit(status)
""".strip()
_COLLECT_PREFIX = "AI_SKILLS_COLLECTED="


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.strip().casefold()).strip("-")


def _closing_fence(line: str, character: str, minimum_length: int) -> bool:
    return re.fullmatch(rf" {{0,3}}{re.escape(character)}{{{minimum_length},}}[ \t]*", line) is not None


def _heading_anchors(path: Path) -> set[str]:
    anchors: set[str] = set()
    fence_character: str | None = None
    fence_length = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if fence_character is not None:
            if _closing_fence(line, fence_character, fence_length):
                fence_character = None
                fence_length = 0
            continue
        fence = _FENCE_OPEN.match(line)
        if fence is not None:
            marker, info = fence.groups()
            if marker[0] != "`" or "`" not in info:
                fence_character = marker[0]
                fence_length = len(marker)
                continue
        match = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if match:
            anchors.add(_slug(match.group(1)))
    return anchors


def _test_names(path: Path) -> set[str]:
    """Return source-level candidates for ``file.py::test_name`` selectors."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_")
    }


def _pytest_environment() -> dict[str, str]:
    environment = {
        name: value
        for name, value in os.environ.items()
        if name in _PYTEST_ENVIRONMENT_ALLOWLIST or name.startswith("LC_")
    }
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return environment


def _collect_nodeids(root: Path, test_files: set[str]) -> tuple[set[str], str | None]:
    """Collect all referenced modules once under the repository's own pytest configuration."""
    if not test_files:
        return set(), None
    try:
        completed = subprocess.run(  # noqa: S603 - fixed interpreter/code and schema-validated repository paths.
            [sys.executable, "-c", _PYTEST_COLLECT_SCRIPT, *sorted(test_files)],
            cwd=root,
            env=_pytest_environment(),
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return set(), f"pytest collection could not run: {exc}"
    payload_line = next(
        (line for line in reversed(completed.stdout.splitlines()) if line.startswith(_COLLECT_PREFIX)),
        None,
    )
    if payload_line is None:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        return set(), detail[-1][:300] if detail else f"pytest collection exited {completed.returncode}"
    try:
        raw_nodeids = json.loads(payload_line[len(_COLLECT_PREFIX) :])
    except json.JSONDecodeError as exc:
        return set(), f"pytest collection returned invalid node ids: {exc}"
    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()
        return set(), detail[-1][:300] if detail else f"pytest collection exited {completed.returncode}"
    if not isinstance(raw_nodeids, list) or not all(isinstance(item, str) for item in raw_nodeids):
        return set(), "pytest collection returned an invalid node-id payload"
    return set(raw_nodeids), None


def _known_canaries(root: Path) -> set[str]:
    path = root / "contracts/consumer-canaries.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return set()
    entries = raw.get("canaries")
    if not isinstance(entries, list):
        return set()
    return {str(entry.get("id")) for entry in entries if isinstance(entry, dict) and isinstance(entry.get("id"), str)}


def validate_registry(path: Path, *, repository_root: Path = ROOT) -> list[str]:
    root = repository_root.resolve(strict=True)
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        return [f"consumer feedback registry could not be loaded: {exc}"]
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    schema_findings = [
        f"schema: {'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(
            Draft202012Validator(schema).iter_errors(document), key=lambda item: list(item.absolute_path)
        )
    ]
    if schema_findings:
        return schema_findings
    assert isinstance(document, dict)
    incidents = document["incidents"]
    assert isinstance(incidents, list)
    findings: list[str] = []
    try:
        known_canaries = _known_canaries(root)
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        return [f"consumer canary catalog could not be loaded: {exc}"]
    seen: set[str] = set()
    pending_selectors: list[tuple[str, str]] = []
    test_files: set[str] = set()
    for incident in incidents:
        assert isinstance(incident, dict)
        incident_id = str(incident["id"])
        if incident_id in seen:
            findings.append(f"{incident_id}: duplicate incident id")
        seen.add(incident_id)
        for canary in incident.get("source_canaries", []):
            if canary not in known_canaries:
                findings.append(f"{incident_id}: unknown source canary {canary!r}")
        owner, anchor = str(incident["canonical_owner"]).split("#", 1)
        try:
            owner_path = confined_regular_file(root, owner)
            anchors = _heading_anchors(owner_path)
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            findings.append(f"{incident_id}: invalid canonical owner: {exc}")
        else:
            if anchor not in anchors:
                findings.append(f"{incident_id}: canonical owner anchor #{anchor} does not exist")
        for raw_selector in incident["regression_selectors"]:
            selector = str(raw_selector)
            match = SELECTOR.fullmatch(selector)
            if match is None:
                findings.append(f"{incident_id}: invalid regression selector {raw_selector!r}")
                continue
            test_path_raw, test_name = match.groups()
            try:
                test_path = confined_regular_file(root, test_path_raw)
            except (OSError, ValueError) as exc:
                findings.append(f"{incident_id}: invalid regression path: {exc}")
                continue
            try:
                names = _test_names(test_path)
            except (OSError, UnicodeDecodeError, SyntaxError) as exc:
                findings.append(f"{incident_id}: regression file could not be parsed: {exc}")
                continue
            if test_name not in names:
                findings.append(
                    f"{incident_id}: regression selector does not name an existing test "
                    f"(must be a top-level test): {raw_selector}"
                )
                continue
            pending_selectors.append((incident_id, selector))
            test_files.add(test_path_raw)

    nodeids, collection_error = _collect_nodeids(root, test_files)
    if collection_error is not None:
        for incident_id, selector in pending_selectors:
            findings.append(
                f"{incident_id}: regression selector is not collectable by pytest: {selector} ({collection_error})"
            )
    else:
        for incident_id, selector in pending_selectors:
            if not any(nodeid == selector or nodeid.startswith(f"{selector}[") for nodeid in nodeids):
                findings.append(f"{incident_id}: regression selector is not collectable by pytest: {selector}")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", type=Path, nargs="?", default=Path("contracts/consumer-feedback.yaml"))
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    findings = validate_registry(args.registry, repository_root=args.repository_root)
    for finding in findings:
        print(f"ERROR: {finding}")
    print(f"consumer feedback findings: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
