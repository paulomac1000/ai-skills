"""Boundary tests for the repository's single SemVer 2.0.0 implementation."""

from __future__ import annotations

import pytest

from contracts.semver import is_semver, parse_semver


@pytest.mark.parametrize(
    "value",
    [
        "0.0.0",
        "0.1.0",
        "1.0.0",
        "2.0.0-rc.1",
        "10.20.30-alpha.beta-1+build.7",
        "1.0.0-0.3.7",
        "1.0.0-x.7.z.92",
    ],
)
def test_accepts_canonical_semver(value: str) -> None:
    assert is_semver(value)
    assert parse_semver(value)


@pytest.mark.parametrize(
    "value",
    [
        "0",
        "1",
        "1.0",
        "01.0.0",
        "1.01.0",
        "1.0.01",
        "1.0.0-",
        "1.0.0-..",
        "1.0.0-01",
        "1.0.0-alpha.01",
        "1.0.0+",
        "v1.0.0",
        1,
        None,
    ],
)
def test_rejects_noncanonical_semver(value: object) -> None:
    assert not is_semver(value)
    with pytest.raises(ValueError):
        parse_semver(value)
