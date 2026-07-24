#!/usr/bin/env python3
"""Install and verify the complete hashed dependency graph for this platform."""

from __future__ import annotations

import subprocess
import sys

from select_lock import selected_lock


def main() -> int:
    lock = selected_lock()
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--require-hashes", "-r", str(lock)],
        check=True,
        timeout=900,
    )
    subprocess.run([sys.executable, "-m", "pip", "check"], check=True, timeout=120)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
