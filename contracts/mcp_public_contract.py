"""MCP public-contract normalization, semantic diffing, and SemVer enforcement."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from contracts.semver import parse_semver

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "contracts/mcp-public-contract.schema.json"


@dataclass(frozen=True, slots=True)
class ContractChange:
    """One normalized public-contract difference."""

    classification: str
    pointer: str
    reason: str


@dataclass(frozen=True, slots=True)
class ContractComparison:
    """Semantic comparison result used by migration and release gates."""

    changes: tuple[ContractChange, ...]
    required_bump: str
    version_satisfies: bool


def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_contract(document: object) -> list[str]:
    """Return schema and cross-field findings for one public-contract snapshot."""
    validator = Draft202012Validator(_schema())
    findings = [
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(document), key=lambda item: tuple(str(part) for part in item.absolute_path))
    ]
    if findings or not isinstance(document, dict):
        return findings

    tools = document.get("tools")
    if isinstance(tools, list):
        names = [tool.get("name") for tool in tools if isinstance(tool, dict)]
        duplicates = sorted({name for name in names if isinstance(name, str) and names.count(name) > 1})
        if duplicates:
            findings.append(f"duplicate public tool names: {duplicates}")
    return findings


def load_contract(path: Path) -> dict[str, Any]:
    """Load and validate one JSON public-contract snapshot."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load MCP public contract: {exc}") from exc
    findings = validate_contract(document)
    if findings:
        raise ValueError("; ".join(findings))
    assert isinstance(document, dict)
    return document


def normalize_contract(document: dict[str, Any]) -> dict[str, Any]:
    """Return a stable JSON representation without changing public semantics."""
    findings = validate_contract(document)
    if findings:
        raise ValueError("; ".join(findings))
    normalized = json.loads(json.dumps(document))
    normalized["transports"] = sorted(normalized["transports"])
    normalized["tools"] = sorted(normalized["tools"], key=lambda item: item["name"])
    for tool in normalized["tools"]:
        tool["error_contract"] = sorted(tool["error_contract"])
        input_schema = tool.get("input_schema")
        if isinstance(input_schema, dict) and isinstance(input_schema.get("required"), list):
            input_schema["required"] = sorted(input_schema["required"])
        output_schema = tool.get("output_schema")
        if isinstance(output_schema, dict) and isinstance(output_schema.get("required"), list):
            output_schema["required"] = sorted(output_schema["required"])
    return normalized


def _object_properties(schema: object) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {}
    value = schema.get("properties")
    return dict(value) if isinstance(value, dict) else {}


def _required_fields(schema: object) -> set[str]:
    if not isinstance(schema, dict):
        return set()
    value = schema.get("required")
    return {item for item in value if isinstance(item, str)} if isinstance(value, list) else set()


def _schema_changes(
    baseline: object,
    candidate: object,
    *,
    pointer: str,
    output: bool,
) -> list[ContractChange]:
    changes: list[ContractChange] = []
    before_properties = _object_properties(baseline)
    after_properties = _object_properties(candidate)
    before_required = _required_fields(baseline)
    after_required = _required_fields(candidate)

    for name in sorted(before_properties.keys() - after_properties.keys()):
        changes.append(ContractChange("breaking", f"{pointer}/properties/{name}", "public field was removed"))
    for name in sorted(after_properties.keys() - before_properties.keys()):
        classification = "additive"
        if not output and name in after_required:
            classification = "breaking"
        changes.append(
            ContractChange(
                classification,
                f"{pointer}/properties/{name}",
                "new required input field" if classification == "breaking" else "public field was added",
            )
        )
    for name in sorted(before_properties.keys() & after_properties.keys()):
        if before_properties[name] != after_properties[name]:
            changes.append(ContractChange("breaking", f"{pointer}/properties/{name}", "public field schema changed"))

    if output:
        for name in sorted(before_required - after_required):
            changes.append(
                ContractChange("breaking", f"{pointer}/required/{name}", "required output guarantee was removed")
            )
        for name in sorted(after_required - before_required):
            changes.append(ContractChange("additive", f"{pointer}/required/{name}", "output guarantee was added"))
    else:
        for name in sorted(after_required - before_required):
            if name in before_properties:
                changes.append(ContractChange("breaking", f"{pointer}/required/{name}", "existing input became required"))
        for name in sorted(before_required - after_required):
            changes.append(ContractChange("additive", f"{pointer}/required/{name}", "required input became optional"))

    if isinstance(baseline, dict) and isinstance(candidate, dict):
        before_additional = baseline.get("additionalProperties", True)
        after_additional = candidate.get("additionalProperties", True)
        if before_additional is not False and after_additional is False:
            changes.append(
                ContractChange("breaking", f"{pointer}/additionalProperties", "unknown fields became forbidden")
            )
    return changes


def _version_allows(baseline: str, candidate: str, required_bump: str) -> bool:
    before = parse_semver(baseline)
    after = parse_semver(candidate)
    before_triplet = (before.major, before.minor, before.patch)
    after_triplet = (after.major, after.minor, after.patch)
    if required_bump == "none":
        return after_triplet >= before_triplet
    if after_triplet <= before_triplet:
        return False
    if required_bump == "major":
        return after.major > before.major
    if required_bump == "minor":
        return after.major > before.major or (after.major == before.major and after.minor > before.minor)
    raise ValueError(f"unknown required bump: {required_bump}")


def compare_contracts(baseline: dict[str, Any], candidate: dict[str, Any]) -> ContractComparison:
    """Classify public MCP changes and calculate the minimum SemVer bump."""
    before = normalize_contract(baseline)
    after = normalize_contract(candidate)
    changes: list[ContractChange] = []

    if before["server"]["name"] != after["server"]["name"]:
        changes.append(ContractChange("breaking", "/server/name", "server public identity changed"))
    if before["sdk"]["profile"] != after["sdk"]["profile"]:
        changes.append(ContractChange("breaking", "/sdk/profile", "MCP SDK family/profile changed"))

    before_transports = set(before["transports"])
    after_transports = set(after["transports"])
    for value in sorted(before_transports - after_transports):
        changes.append(ContractChange("breaking", f"/transports/{value}", "advertised transport was removed"))
    for value in sorted(after_transports - before_transports):
        changes.append(ContractChange("additive", f"/transports/{value}", "advertised transport was added"))

    for field in ("required", "mechanism", "target_selection"):
        if before["authentication"][field] != after["authentication"][field]:
            changes.append(
                ContractChange("breaking", f"/authentication/{field}", "authentication/target policy changed")
            )

    before_tools = {tool["name"]: tool for tool in before["tools"]}
    after_tools = {tool["name"]: tool for tool in after["tools"]}
    for name in sorted(before_tools.keys() - after_tools.keys()):
        changes.append(ContractChange("breaking", f"/tools/{name}", "public tool was removed"))
    for name in sorted(after_tools.keys() - before_tools.keys()):
        changes.append(ContractChange("additive", f"/tools/{name}", "public tool was added"))

    for name in sorted(before_tools.keys() & after_tools.keys()):
        left = before_tools[name]
        right = after_tools[name]
        changes.extend(
            _schema_changes(
                left["input_schema"],
                right["input_schema"],
                pointer=f"/tools/{name}/input_schema",
                output=False,
            )
        )
        changes.extend(
            _schema_changes(
                left.get("output_schema", {}),
                right.get("output_schema", {}),
                pointer=f"/tools/{name}/output_schema",
                output=True,
            )
        )
        for field in ("error_contract", "pagination", "retry_semantics", "target_selection"):
            if left[field] != right[field]:
                changes.append(ContractChange("breaking", f"/tools/{name}/{field}", f"{field} semantics changed"))

    if any(change.classification == "breaking" for change in changes):
        required_bump = "major"
    elif any(change.classification == "additive" for change in changes):
        required_bump = "minor"
    else:
        required_bump = "none"

    return ContractComparison(
        tuple(changes),
        required_bump,
        _version_allows(before["server"]["version"], after["server"]["version"], required_bump),
    )


def render_comparison(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Render a deterministic machine-readable contract comparison."""
    result = compare_contracts(baseline, candidate)
    return {
        "format": "ai-skills-mcp-contract-diff",
        "schema_version": 1,
        "baseline_revision": baseline["source_revision"],
        "candidate_revision": candidate["source_revision"],
        "baseline_version": baseline["server"]["version"],
        "candidate_version": candidate["server"]["version"],
        "required_bump": result.required_bump,
        "version_satisfies": result.version_satisfies,
        "changes": [
            {"classification": item.classification, "pointer": item.pointer, "reason": item.reason}
            for item in result.changes
        ],
    }
