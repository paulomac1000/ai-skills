#!/usr/bin/env python3
"""Install and verify the complete hashed graph for the active target tuple.

Locked inventory validation compares every pinned distribution with the
installed one under PEP 440 canonicalization. ``packaging`` is supplied by the
committed dependency locks; a missing dependency is reported as an explicit
validation error instead of an opaque crash.
"""

from __future__ import annotations

import re
import subprocess
import sys
from importlib import metadata

from select_lock import selected_lock


class LockedInventoryUnavailable(RuntimeError):
    """Raised when locked inventory validation cannot load its declared dependency."""


def classify_pip_check(report: str, lock_text: str) -> tuple[list[str], list[str]]:
    """Keep strict lock-graph checks despite globally preinstalled runner tools.

    pip check traverses EVERY system-site distribution, even those neither
    installed nor declared by this repository. A host-package conflict is
    diagnostic only when its *requiring* distribution is absent from the lock.
    Unknown report syntax stays blocking.
    """
    pinned = {
        re.sub(r"[-_.]+", "-", name).lower()
        for name in re.findall(r"(?m)^\s*([A-Za-z0-9_.-]+)==[0-9][^\s]*", lock_text)
    }
    if not pinned:
        return ["locked_distribution_inventory_missing"], []
    blocking: list[str] = []
    unmanaged: list[str] = []
    for line in report.splitlines():
        message = line.strip()
        if not message or message == "No broken requirements found.":
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)\s+\S+\s+(?:has requirement|requires)\s+.+", message)
        missing = re.search(
            r"\b(?:requires|has requirement)\s+([A-Za-z0-9_.-]+).*\bwhich is not installed\.\s*$",
            message,
            re.IGNORECASE,
        )
        if missing is not None and re.sub(r"[-_.]+", "-", missing.group(1)).lower() in pinned:
            blocking.append(message)
        elif match is None:
            blocking.append(message)
        elif re.sub(r"[-_.]+", "-", match.group(1)).lower() in pinned:
            blocking.append(message)
        else:
            unmanaged.append(message)
    return blocking, unmanaged


def _locked_inventory_findings(lock_text: str) -> list[str]:
    """Require every selected lock pin at its installed distribution version."""
    try:
        from packaging.version import InvalidVersion, Version
    except ImportError as exc:
        raise LockedInventoryUnavailable("packaging is required for locked inventory validation") from exc

    def canonical_version(value: str) -> str | None:
        """Return the PEP 440 canonical form, or None when the value does not conform."""
        try:
            return str(Version(value))
        except InvalidVersion:
            return None

    pins = re.findall(r"(?m)^\s*([A-Za-z0-9_.-]+)==([0-9][A-Za-z0-9.+!_-]*)", lock_text)
    if not pins:
        return ["locked_distribution_inventory_missing"]
    findings: list[str] = []
    for name, expected in pins:
        canonical_name = re.sub(r"[-_.]+", "-", name).lower()
        try:
            installed = metadata.version(canonical_name)
        except metadata.PackageNotFoundError:
            findings.append(f"locked_distribution_missing:{canonical_name}=={expected}")
            continue
        expected_canonical = canonical_version(expected)
        if expected_canonical is None or canonical_version(installed) != expected_canonical:
            findings.append(f"locked_distribution_version_mismatch:{canonical_name}=={expected}:installed={installed}")
    return findings


def main(*, verify_only: bool = False) -> int:
    lock = selected_lock()
    if not verify_only:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--require-hashes", "-r", str(lock)],
            check=True,
            timeout=900,
        )
    outcome = subprocess.run(
        [sys.executable, "-m", "pip", "check"],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    if outcome.returncode:
        # Unexpected stderr is not evidence of an unmanaged host conflict.
        # It may indicate that pip failed before completing the dependency audit.
        if outcome.stderr and outcome.stderr.strip():
            print(outcome.stderr, file=sys.stderr)
            raise subprocess.CalledProcessError(outcome.returncode, outcome.args)
        blocking, unmanaged = classify_pip_check(outcome.stdout, lock.read_text(encoding="utf-8"))
        for notice in unmanaged:
            print("HOST_UNMANAGED_PACKAGE_CONFLICT: " + notice, file=sys.stderr)
        if blocking or not unmanaged or outcome.returncode != 1:
            print(outcome.stdout, file=sys.stderr)
            raise subprocess.CalledProcessError(outcome.returncode, outcome.args)
    try:
        inventory_findings = _locked_inventory_findings(lock.read_text(encoding="utf-8"))
    except LockedInventoryUnavailable as exc:
        print("LOCK_INVENTORY_UNAVAILABLE: " + str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    if inventory_findings:
        for finding in inventory_findings:
            print("LOCK_INVENTORY_INVALID: " + finding, file=sys.stderr)
        raise subprocess.CalledProcessError(1, outcome.args)
    return 0


if __name__ == "__main__":
    if sys.argv[1:] not in ([], ["--verify-only"]):
        raise SystemExit(2)
    raise SystemExit(main(verify_only=bool(sys.argv[1:])))
