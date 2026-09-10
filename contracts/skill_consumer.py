#!/usr/bin/env python3
"""Resolve task capabilities to exact governed skills without name guessing."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml

ResolutionStatus = Literal[
    "READY",
    "LOADED",
    "NOT_CATALOGUED",
    "AMBIGUOUS",
    "NOT_INSTALLED",
    "NOT_VISIBLE",
    "UNSUPPORTED_LOAD_MODE",
    "INCOMPATIBLE",
    "STALE_LOADED_REVISION",
    "BLOCKED_REQUIRED_SKILL",
    "UNKNOWN",
]
HEX64 = re.compile(r"^[a-f0-9]{64}$")
LOAD_MODES = {"runtime_tool", "preload", "vendored"}


class SkillConsumerError(ValueError):
    """Raised when catalog/runtime inputs are structurally unsafe."""


@dataclass(frozen=True)
class SkillResolution:
    status: ResolutionStatus
    capability: str
    skill_id: str | None
    catalog_revision: str
    installed_revision: str | None
    loaded_revision: str | None
    selected_load_mode: str | None
    deviation_required: bool
    reason: str


def _validate_catalog_entries(skills: object) -> list[dict[str, Any]]:
    if not isinstance(skills, list):
        raise SkillConsumerError("catalog must contain a skills list")
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(skills):
        if not isinstance(item, dict):
            raise SkillConsumerError(f"catalog skills[{index}] must be an object")
        skill_id = item.get("skill_id")
        if not isinstance(skill_id, str) or not skill_id:
            raise SkillConsumerError(f"catalog skills[{index}].skill_id is required")
        if skill_id in seen:
            raise SkillConsumerError(f"catalog contains duplicate skill_id: {skill_id}")
        seen.add(skill_id)
        capabilities = item.get("capabilities")
        if (
            not isinstance(capabilities, list)
            or not capabilities
            or any(not isinstance(capability, str) or not capability for capability in capabilities)
            or len(set(capabilities)) != len(capabilities)
        ):
            raise SkillConsumerError(f"catalog skill {skill_id}.capabilities must be unique non-empty strings")
        loading = item.get("loading")
        if not isinstance(loading, dict):
            raise SkillConsumerError(f"catalog skill {skill_id}.loading must be an object")
        modes = loading.get("modes")
        if (
            not isinstance(modes, list)
            or not modes
            or any(not isinstance(mode, str) or mode not in LOAD_MODES for mode in modes)
            or len(set(modes)) != len(modes)
        ):
            raise SkillConsumerError(f"catalog skill {skill_id}.loading.modes is invalid")
        validated.append(item)
    return validated


def load_catalog(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise SkillConsumerError(f"catalog cannot be loaded: {error}") from error
    if not isinstance(raw, dict):
        raise SkillConsumerError("catalog must contain an object")
    _validate_catalog_entries(raw.get("skills"))
    return raw


def _valid_datetime(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _validate_optional_digest(value: object, field: str) -> None:
    if value is None:
        return
    if not isinstance(value, str) or HEX64.fullmatch(value) is None:
        raise SkillConsumerError(f"runtime state {field} must be 64 lowercase hexadecimal characters or null")


def _validate_runtime_entries(skills: object) -> list[dict[str, Any]]:
    if not isinstance(skills, list):
        raise SkillConsumerError("runtime state must contain a skills list")
    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    for index, item in enumerate(skills):
        if not isinstance(item, dict):
            raise SkillConsumerError(f"runtime state skills[{index}] must be an object")
        skill_id = item.get("skill_id")
        if not isinstance(skill_id, str) or not skill_id:
            raise SkillConsumerError(f"runtime state skills[{index}].skill_id is required")
        if skill_id in seen:
            raise SkillConsumerError(f"runtime state contains duplicate skill_id: {skill_id}")
        seen.add(skill_id)
        for field in ("installed", "runtime_visible", "compatible"):
            if not isinstance(item.get(field), bool):
                raise SkillConsumerError(f"runtime state {skill_id}.{field} must be boolean")
        modes = item.get("supported_load_modes")
        if (
            not isinstance(modes, list)
            or any(not isinstance(mode, str) or mode not in LOAD_MODES for mode in modes)
            or len(set(modes)) != len(modes)
        ):
            raise SkillConsumerError(f"runtime state {skill_id}.supported_load_modes is invalid")
        for field in ("installed_revision", "loaded_revision"):
            value = item.get(field)
            if value is not None and (not isinstance(value, str) or not value):
                raise SkillConsumerError(f"runtime state {skill_id}.{field} must be a non-empty string or null")
        _validate_optional_digest(item.get("installed_artifact_digest"), f"{skill_id}.installed_artifact_digest")
        _validate_optional_digest(item.get("loaded_artifact_digest"), f"{skill_id}.loaded_artifact_digest")
        distribution_mode = item.get("distribution_mode")
        if distribution_mode is not None and distribution_mode not in {"GLOBAL", "VENDORED", "EPHEMERAL"}:
            raise SkillConsumerError(f"runtime state {skill_id}.distribution_mode is invalid")
        validated.append(item)
    return validated


def _validate_runtime_state(runtime: dict[str, Any]) -> None:
    if runtime.get("schema_version") != 1:
        raise SkillConsumerError("runtime state schema_version must be 1")
    runtime_id = runtime.get("runtime_id")
    if not isinstance(runtime_id, str) or not runtime_id:
        raise SkillConsumerError("runtime state runtime_id is required")
    if not _valid_datetime(runtime.get("observed_at")):
        raise SkillConsumerError("runtime state observed_at must be a timezone-aware date-time")
    _validate_runtime_entries(runtime.get("skills"))


def load_runtime_state(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SkillConsumerError(f"runtime state cannot be loaded: {error}") from error
    if not isinstance(raw, dict):
        raise SkillConsumerError("runtime state root must be an object")
    _validate_runtime_state(raw)
    return raw


def catalog_digest(catalog: dict[str, Any]) -> str:
    encoded = json.dumps(catalog, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _matches_capability(entry: dict[str, Any], capability: str) -> bool:
    capabilities = entry["capabilities"]
    return capability in capabilities


def _runtime_entry(runtime: dict[str, Any], skill_id: str) -> dict[str, Any] | None:
    matches = [item for item in runtime.get("skills", []) if item.get("skill_id") == skill_id]
    if len(matches) > 1:
        raise SkillConsumerError(f"runtime state contains duplicate skill_id: {skill_id}")
    return matches[0] if matches else None


def resolve_skill(
    *,
    catalog: dict[str, Any],
    runtime: dict[str, Any],
    capability: str,
    required_skill: str | None = None,
    allowed_load_modes: tuple[str, ...] = ("runtime_tool", "preload", "vendored"),
) -> SkillResolution:
    """Resolve an exact skill from declared capability and schema-valid live runtime state."""
    entries = _validate_catalog_entries(catalog.get("skills"))
    _validate_runtime_entries(runtime.get("skills"))
    revision = str(catalog.get("catalog_revision") or catalog_digest(catalog))

    candidates = [item for item in entries if _matches_capability(item, capability)]
    if required_skill is not None:
        required = [item for item in entries if item.get("skill_id") == required_skill]
        if not required:
            return SkillResolution(
                "BLOCKED_REQUIRED_SKILL",
                capability,
                required_skill,
                revision,
                None,
                None,
                None,
                True,
                "explicitly required skill is not present in the governed catalog",
            )
        entry = required[0]
        if entry not in candidates:
            return SkillResolution(
                "BLOCKED_REQUIRED_SKILL",
                capability,
                required_skill,
                revision,
                None,
                None,
                None,
                True,
                "explicitly required skill does not declare the requested capability",
            )
        candidates = [entry]

    if not candidates:
        return SkillResolution(
            "NOT_CATALOGUED",
            capability,
            None,
            revision,
            None,
            None,
            None,
            False,
            "no governed skill declares the requested capability",
        )
    if len(candidates) > 1:
        return SkillResolution(
            "AMBIGUOUS",
            capability,
            None,
            revision,
            None,
            None,
            None,
            required_skill is not None,
            "multiple governed skills declare the capability; refine declared routing constraints",
        )

    entry = candidates[0]
    skill_id = str(entry["skill_id"])
    state = _runtime_entry(runtime, skill_id)
    blocked = required_skill is not None
    if state is None or not state.get("installed", False):
        return SkillResolution(
            "BLOCKED_REQUIRED_SKILL" if blocked else "NOT_INSTALLED",
            capability,
            skill_id,
            revision,
            None,
            None,
            None,
            blocked,
            "skill is catalogued but no approved installed artifact is present",
        )

    installed_revision = str(state.get("installed_revision") or "")
    if not installed_revision:
        return SkillResolution(
            "BLOCKED_REQUIRED_SKILL" if blocked else "UNKNOWN",
            capability,
            skill_id,
            revision,
            None,
            None,
            None,
            blocked,
            "installed skill has no attributable revision",
        )
    installed_digest = state.get("installed_artifact_digest")
    if not isinstance(installed_digest, str):
        return SkillResolution(
            "BLOCKED_REQUIRED_SKILL" if blocked else "UNKNOWN",
            capability,
            skill_id,
            revision,
            installed_revision,
            None,
            None,
            blocked,
            "installed skill has no attributable artifact digest",
        )
    if not state.get("runtime_visible", False):
        return SkillResolution(
            "BLOCKED_REQUIRED_SKILL" if blocked else "NOT_VISIBLE",
            capability,
            skill_id,
            revision,
            installed_revision,
            None,
            None,
            blocked,
            "installed skill is not visible to the current runtime",
        )
    if not state.get("compatible", False):
        return SkillResolution(
            "BLOCKED_REQUIRED_SKILL" if blocked else "INCOMPATIBLE",
            capability,
            skill_id,
            revision,
            installed_revision,
            None,
            None,
            blocked,
            "current runtime does not satisfy the skill compatibility contract",
        )

    supported = tuple(state.get("supported_load_modes") or ())
    declared = tuple(entry["loading"]["modes"])
    selected = next((mode for mode in allowed_load_modes if mode in supported and mode in declared), None)
    if selected is None:
        return SkillResolution(
            "BLOCKED_REQUIRED_SKILL" if blocked else "UNSUPPORTED_LOAD_MODE",
            capability,
            skill_id,
            revision,
            installed_revision,
            None,
            None,
            blocked,
            "no load mode is both declared by the skill and supported by the current runtime",
        )

    loaded_revision = state.get("loaded_revision")
    loaded_digest = state.get("loaded_artifact_digest")
    if loaded_revision is not None:
        if not isinstance(loaded_digest, str):
            return SkillResolution(
                "BLOCKED_REQUIRED_SKILL" if blocked else "STALE_LOADED_REVISION",
                capability,
                skill_id,
                revision,
                installed_revision,
                str(loaded_revision),
                selected,
                blocked,
                "loaded skill has no attributable artifact digest; reload is required",
            )
        if str(loaded_revision) != installed_revision or loaded_digest != installed_digest:
            return SkillResolution(
                "BLOCKED_REQUIRED_SKILL" if blocked else "STALE_LOADED_REVISION",
                capability,
                skill_id,
                revision,
                installed_revision,
                str(loaded_revision),
                selected,
                blocked,
                "loaded skill identity no longer matches the installed artifact; reload is required",
            )
        return SkillResolution(
            "LOADED",
            capability,
            skill_id,
            revision,
            installed_revision,
            str(loaded_revision),
            selected,
            False,
            "exact installed revision and artifact digest are already loaded",
        )

    return SkillResolution(
        "READY",
        capability,
        skill_id,
        revision,
        installed_revision,
        None,
        selected,
        False,
        "exact skill is catalogued, installed, digest-attributed, visible, compatible, and loadable",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--runtime-state", type=Path, required=True)
    parser.add_argument("--capability", required=True)
    parser.add_argument("--required-skill")
    args = parser.parse_args()
    try:
        result = resolve_skill(
            catalog=load_catalog(args.catalog),
            runtime=load_runtime_state(args.runtime_state),
            capability=args.capability,
            required_skill=args.required_skill,
        )
    except SkillConsumerError as error:
        print(json.dumps({"status": "UNKNOWN", "reason": str(error)}, sort_keys=True))
        return 2
    print(json.dumps(asdict(result), indent=2, sort_keys=True))
    return 0 if result.status in {"READY", "LOADED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
