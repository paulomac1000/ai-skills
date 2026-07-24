#!/usr/bin/env python3
"""Select the committed platform lock used by repository quality gates."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLATFORM_SUFFIX = {"linux": "linux", "darwin": "macos", "win32": "windows"}


def selected_lock(platform: str = sys.platform) -> Path:
    """Return the platform-specific root development lock or fail closed."""
    suffix = PLATFORM_SUFFIX.get(platform)
    if suffix is None:
        raise RuntimeError(f"unsupported lock platform: {platform}")
    return ROOT / f"requirements-dev-{suffix}.lock"


def main() -> int:
    print(selected_lock().relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
