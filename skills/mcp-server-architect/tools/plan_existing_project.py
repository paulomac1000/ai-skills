#!/usr/bin/env python3
"""Generate a read-only executable adoption plan from discovered consumer facts."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
TOOLS = Path(__file__).resolve().parent
for value in (str(ROOT), str(TOOLS)):
    if value not in sys.path:
        sys.path.insert(0, value)

_inspector_module = importlib.import_module("inspect_existing_project")
_applicability_module = importlib.import_module("contracts.rule_applicability")
inspect_repository = _inspector_module.inspect_repository
_regular_text = _inspector_module._regular_text
RuleContext = _applicability_module.RuleContext
project_applicability = _applicability_module.project_applicability

LEVELS = {"L1", "L2", "L3", "L4"}
SDK_PACKAGES = {
    "python-official-mcp": "mcp",
    "python-fastmcp-package": "fastmcp",
}
_WILDCARD_VERSION_COMPONENT = re.compile(r"(?:^|[._+-])[xX](?:$|[._+-])")


def _is_exact_requirement(requirement: str) -> bool:
    """Return true only for one concrete ``==`` package version, not a wildcard/range."""
    requirement_part = requirement.split(";", 1)[0].strip()
    match = re.fullmatch(r"==\s*([^,;\s]+)", requirement_part)
    if match is None:
        return False
    version = match.group(1)
    return "*" not in version and _WILDCARD_VERSION_COMPONENT.search(version) is None


def _dependency_specs(repository_root: Path, document: dict[str, Any]) -> list[str]:
    """Return bounded root dependency declarations from the same sources used by discovery."""
    specs: list[str] = []
    project = document.get("project") if isinstance(document, dict) else None
    dependencies = project.get("dependencies") if isinstance(project, dict) else None
    if isinstance(dependencies, list):
        specs.extend(raw.strip() for raw in dependencies if isinstance(raw, str) and raw.strip())
    for candidate in sorted(repository_root.glob("requirements*.txt")) + sorted(
        repository_root.glob("requirements*.in")
    ):
        text = _regular_text(candidate)
        if text is None:
            continue
        specs.extend(line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith(("#", "-")))
    return specs


def _sdk_claim(repository_root: Path, discovery: dict[str, Any]) -> dict[str, Any]:
    package = SDK_PACKAGES.get(discovery["facts"]["sdk_profile"])
    if package is None:
        return {"package": None, "requirement": None, "status": "unknown"}
    document: dict[str, Any] = {}
    pyproject = repository_root / "pyproject.toml"
    if pyproject.is_file():
        try:
            loaded = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            loaded = {}
        if isinstance(loaded, dict):
            document = loaded
    package_pattern = re.compile(
        rf"^\s*{re.escape(package)}(?:\[[^]]+\])?(?=\s*(?:[<>=!~;@]|$))\s*(.*)$",
        re.I,
    )
    requirements: list[str] = []
    for raw in _dependency_specs(repository_root, document):
        match = package_pattern.match(raw)
        if match is None:
            continue
        requirements.append(match.group(1).strip() or "unconstrained")
    if not requirements:
        return {"package": package, "requirement": None, "status": "unknown"}
    unique_requirements = list(dict.fromkeys(requirements))
    if len(unique_requirements) == 1:
        requirement = unique_requirements[0]
        status = "exact-pin" if _is_exact_requirement(requirement) else "requires-compatibility-evidence"
        return {"package": package, "requirement": requirement, "status": status}
    return {
        "package": package,
        "requirement": " | ".join(unique_requirements),
        "status": "requires-compatibility-evidence",
    }


def _context(discovery: dict[str, Any], target_level: str) -> Any:
    facts = discovery["facts"]
    profiles = {"mcp"}
    if facts["packaged"]:
        profiles.add("packaged")
    if facts["containerized"]:
        profiles.add("container")
    if facts["external_upstream"]:
        profiles.add("external-upstream")
    if facts["external_tests"]:
        profiles.add("live-backend")
    if facts["transports"]["stdio"]:
        profiles.add("local-stdio")
    if facts["transports"]["streamable_http"]:
        profiles.add("remote-http")

    capabilities: set[str] = set()
    if facts["capabilities"]["write_signal"]:
        capabilities.add("write")
    if facts["capabilities"]["destructive_signal"]:
        capabilities.add("destructive")
    return RuleContext(target_level, frozenset(profiles), frozenset(capabilities))


def _summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "severity": item.get("severity", "blocking"),
        "waivable": bool(item.get("waivable", False)),
        "required_evidence": list(item.get("required_evidence", [])),
        "status": "planned",
    }


def build_plan(repository_root: Path, *, target_level: str = "L2") -> dict[str, Any]:
    """Build one machine-projected migration plan without executing consumer code."""
    if target_level not in LEVELS:
        raise ValueError(f"unsupported target level: {target_level}")
    discovery = inspect_repository(repository_root)
    context = _context(discovery, target_level)
    parent_catalog = yaml.safe_load((ROOT / "contracts/rule-catalog.yaml").read_text(encoding="utf-8"))
    child_catalog = yaml.safe_load((ROOT / "contracts/atomic-claim-catalog.yaml").read_text(encoding="utf-8"))
    projection = project_applicability(parent_catalog, child_catalog, "mcp-server-architect", context)

    parents = [_summary(dict(item)) for item in projection.parent_rules]
    controls = [_summary(dict(item)) for item in projection.child_controls]
    evidence_types = sorted({evidence for item in (*parents, *controls) for evidence in item["required_evidence"]})

    sdk_claim = _sdk_claim(repository_root, discovery)
    next_actions: list[str] = []
    if discovery["plan"]["upstream_contract"] == "required":
        next_actions.append("observe and validate upstream-contract.yaml before adapter refactoring")
    if discovery["plan"]["live_backend_safety"] == "needs-policy":
        next_actions.append("define and validate live-backend-test-policy.yaml before any live mutation")
    if sdk_claim["status"] == "requires-compatibility-evidence":
        next_actions.append(
            "narrow the SDK claim to an exact tested version or add compatibility lanes covering the claimed range"
        )
    next_actions.extend(
        [
            "capture the baseline public MCP contract through an official-client probe",
            "implement only the projected parent rules and child controls",
            "build and exercise the exact candidate artifact",
            "capture the candidate public MCP contract and enforce the semantic-version diff",
            "collect provider-backed evidence only after local technical gates pass",
        ]
    )

    return {
        "format": "ai-skills-mcp-adoption-plan",
        "schema_version": 1,
        "target_level": target_level,
        "discovery": discovery,
        "context": {
            "profiles": sorted(context.profiles),
            "capabilities": sorted(context.capabilities),
        },
        "applicable_rules": parents,
        "applicable_controls": controls,
        "evidence_plan": {"required_types": evidence_types},
        "sdk_compatibility_claim": sdk_claim,
        "human_decisions": {
            "distribution_profile": "needs-human-decision",
            "exposure_profile": "needs-human-decision",
        },
        "next_actions": next_actions,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    parser.add_argument("--target-level", choices=sorted(LEVELS), default="L2")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    try:
        document = build_plan(args.repository, target_level=args.target_level)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        parser.error(str(exc))
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
