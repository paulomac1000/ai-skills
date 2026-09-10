#!/usr/bin/env python3
"""Resolve task capabilities to exact governed skills without name guessing."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

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


def load_catalog(path: Path) -> dict:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise SkillConsumerError(f"catalog cannot be loaded: {error}") from error
    if not isinstance(raw, dict) or not isinstance(raw.get("skills"), list):
        raise SkillConsumerError("catalog must contain a skills list")
    return raw


def load_runtime_state(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SkillConsumerError(f"runtime state cannot be loaded: {error}") from error
    if not isinstance(raw, dict) or not isinstance(raw.get("skills"), list):
        raise SkillConsumerError("runtime state must contain a skills list")
    return raw


def catalog_digest(catalog: dict) -> str:
    encoded = json.dumps(catalog, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _matches_capability(entry: dict, capability: str) -> bool:
    capabilities = entry.get("capabilities") or []
    return capability in capabilities


def _runtime_entry(runtime: dict, skill_id: str) -> dict | None:
    matches = [item for item in runtime.get("skills", []) if item.get("skill_id") == skill_id]
    if len(matches) > 1:
        raise SkillConsumerError(f"runtime state contains duplicate skill_id: {skill_id}")
    return matches[0] if matches else None


def resolve_skill(
    *,
    catalog: dict,
    runtime: dict,
    capability: str,
    required_skill: str | None = None,
    allowed_load_modes: tuple[str, ...] = ("runtime_tool", "preload", "vendored"),
) -> SkillResolution:
    """Resolve an exact skill from declared capability and live runtime state."""
    revision = str(catalog.get("catalog_revision") or catalog_digest(catalog))

    candidates = [item for item in catalog["skills"] if _matches_capability(item, capability)]
    if required_skill is not None:
        required = [item for item in catalog["skills"] if item.get("skill_id") == required_skill]
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
    if not isinstance(installed_digest, str) or not installed_digest.strip():
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
    declared = tuple((entry.get("loading") or {}).get("modes") or ())
    selected = next(
        (mode for mode in allowed_load_modes if mode in supported and mode in declared),
        None,
    )
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
        if not isinstance(loaded_digest, str) or not loaded_digest.strip():
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
