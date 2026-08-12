#!/usr/bin/env python3
"""Select the exact committed lock for the active target tuple."""

from __future__ import annotations

import argparse
import platform as host_platform
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLATFORM_NAMES = {
    "linux": "linux",
    "darwin": "macos",
    "macos": "macos",
    "win32": "windows",
    "windows": "windows",
}
ARCHITECTURES = {
    "amd64": "x64",
    "x86_64": "x64",
    "x64": "x64",
    "arm64": "arm64",
    "aarch64": "arm64",
}
VERSION = re.compile(r"^(\d+)\.(\d+)$")
SUPPORTED_LOCKS = {
    ("linux", "x64", "3.12"),
    ("linux", "x64", "3.13"),
    ("linux", "x64", "3.14"),
    ("macos", "arm64", "3.12"),
    ("windows", "x64", "3.12"),
}


def normalize_platform(value: str) -> str:
    """Return the idempotent contract OS name or fail closed."""
    normalized = PLATFORM_NAMES.get(value.casefold())
    if normalized is None:
        raise RuntimeError(f"unsupported lock platform: {value}")
    return normalized


def normalize_architecture(value: str) -> str:
    """Return x64 or arm64 for known host architecture labels."""
    normalized = ARCHITECTURES.get(value.casefold())
    if normalized is None:
        raise RuntimeError(f"unsupported lock architecture: {value}")
    return normalized


def normalize_python_version(value: str) -> str:
    """Return a major.minor Python version accepted by the lock contract."""
    match = VERSION.fullmatch(value.strip())
    if match is None:
        raise RuntimeError(f"invalid Python lock version: {value}")
    return f"{int(match.group(1))}.{int(match.group(2))}"


def lock_id(
    platform: str = sys.platform,
    architecture: str | None = None,
    python_version: str | None = None,
) -> str:
    """Return the exact OS/architecture/Python lock identifier."""
    os_name = normalize_platform(platform)
    arch = normalize_architecture(architecture or host_platform.machine())
    version = normalize_python_version(
        python_version or f"{sys.version_info.major}.{sys.version_info.minor}"
    )
    target = (os_name, arch, version)
    if target not in SUPPORTED_LOCKS:
        raise RuntimeError(
            f"unsupported lock target: {os_name}/{arch}/python-{version}"
        )
    return f"{os_name}-{arch}-py{version.replace('.', '')}"


def selected_lock(
    platform: str = sys.platform,
    architecture: str | None = None,
    python_version: str | None = None,
) -> Path:
    """Return the lock for the exact active target tuple."""
    return ROOT / f"requirements-dev-{lock_id(platform, architecture, python_version)}.lock"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", default=sys.platform)
    parser.add_argument("--architecture", default=host_platform.machine())
    parser.add_argument(
        "--python-version",
        default=f"{sys.version_info.major}.{sys.version_info.minor}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(
        selected_lock(
            args.platform,
            args.architecture,
            args.python_version,
        ).relative_to(ROOT)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
