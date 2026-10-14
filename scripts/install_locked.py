#!/usr/bin/env python3
"""Install and verify the complete hashed graph for the active target tuple."""

from __future__ import annotations

import re
import subprocess
import sys

from select_lock import selected_lock


def classify_pip_check(report: str, lock_text: str) -> tuple[list[str], list[str]]:
    """Keep strict lock-graph checks despite globally preinstalled runner tools.

    pip check traverses EVERY system-site distribution, even those neither
    installed nor declared by this repository. A host-package conflict is
    diagnostic only when its *requiring* distribution is absent from the lock.
    Unknown report syntax stays blocking.
    """
    pinned = {
        name.lower().replace("_", "-") for name in re.findall(r"(?m)^\s*([A-Za-z0-9_.-]+)==[0-9][^\s]*", lock_text)
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
        if match is None:
            blocking.append(message)
        elif match.group(1).lower().replace("_", "-") in pinned:
            blocking.append(message)
        else:
            unmanaged.append(message)
    return blocking, unmanaged


def main() -> int:
    lock = selected_lock()
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
        blocking, unmanaged = classify_pip_check(outcome.stdout, lock.read_text(encoding="utf-8"))
        for notice in unmanaged:
            print("HOST_UNMANAGED_PACKAGE_CONFLICT: " + notice, file=sys.stderr)
        if blocking or not unmanaged or outcome.returncode != 1:
            print(outcome.stdout, file=sys.stderr)
            raise subprocess.CalledProcessError(outcome.returncode, outcome.args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
