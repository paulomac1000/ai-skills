"""Strict Semantic Versioning 2.0.0 parser shared by repository contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass

_IDENTIFIER = r"(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
SEMVER_PATTERN = re.compile(
    rf"^(0|[1-9]\d*)\."
    rf"(0|[1-9]\d*)\."
    rf"(0|[1-9]\d*)"
    rf"(?:-({_IDENTIFIER}(?:\.{_IDENTIFIER})*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


@dataclass(frozen=True, slots=True)
class SemanticVersion:
    """One validated SemVer 2.0.0 value."""

    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()
    build: tuple[str, ...] = ()


def parse_semver(value: object) -> SemanticVersion:
    """Parse a canonical SemVer 2.0.0 string or raise ``ValueError``."""
    if not isinstance(value, str):
        raise ValueError("semantic version must be a string")
    match = SEMVER_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError(f"invalid semantic version: {value!r}")
    prerelease = tuple(match.group(4).split(".")) if match.group(4) else ()
    build = tuple(match.group(5).split(".")) if match.group(5) else ()
    return SemanticVersion(
        major=int(match.group(1)),
        minor=int(match.group(2)),
        patch=int(match.group(3)),
        prerelease=prerelease,
        build=build,
    )


def is_semver(value: object) -> bool:
    """Return whether ``value`` is a canonical SemVer 2.0.0 string."""
    try:
        parse_semver(value)
    except ValueError:
        return False
    return True
