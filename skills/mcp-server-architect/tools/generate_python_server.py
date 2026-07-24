#!/usr/bin/env python3
"""Public entry point for the executable Python MCP server generator.

The implementation module owns security-shaped source templates. This facade adds
reviewed full-graph lockfiles, exact-artifact installation, and container parity.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_IMPLEMENTATION_PATH = Path(__file__).with_name("generate_python_server_impl.py")
_LOCK_ROOT = Path(__file__).resolve().parents[1] / "locks"
_SPEC = importlib.util.spec_from_file_location("mcp_python_generator_implementation", _IMPLEMENTATION_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"Cannot load generator implementation: {_IMPLEMENTATION_PATH}")
_implementation = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _implementation
_SPEC.loader.exec_module(_implementation)

RESERVED_PACKAGE_NAMES = frozenset(_implementation.RESERVED_PACKAGE_NAMES) | {"pytest"}
vars(_implementation)["RESERVED_PACKAGE_NAMES"] = RESERVED_PACKAGE_NAMES
PACKAGE_RE = _implementation.PACKAGE_RE
SERVER_RE = _implementation.SERVER_RE
_BASE_PROJECT_FILES = _implementation.project_files
LOCK_NAMES = (
    "runtime-linux.lock",
    "runtime-macos.lock",
    "runtime-windows.lock",
    "dev-linux.lock",
    "dev-macos.lock",
    "dev-windows.lock",
)
SOURCE_NAMES = ("python-runtime.in", "python-dev.in")


def _read_contract_file(name: str) -> str:
    path = _LOCK_ROOT / name
    if not path.is_file():
        raise RuntimeError(f"missing reviewed dependency contract: {path}")
    text = path.read_text(encoding="utf-8")
    if not text.endswith("\n"):
        text += "\n"
    return text


def _replace_required(text: str, old: str, new: str, *, file_name: str) -> str:
    occurrences = text.count(old)
    if occurrences != 1:
        raise RuntimeError(f"expected exactly one {old!r} fragment in generated {file_name}, found {occurrences}")
    return text.replace(old, new)


def _lock_selector() -> str:
    return """from __future__ import annotations

import argparse
import sys
from pathlib import Path

PLATFORMS = {"linux": "linux", "darwin": "macos", "win32": "windows"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("runtime", "dev"))
    args = parser.parse_args()
    platform = PLATFORMS.get(sys.platform)
    if platform is None:
        raise SystemExit(f"unsupported lock platform: {sys.platform}")
    print(Path(__file__).with_name(f"{args.kind}-{platform}.lock"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""


def project_files(package: str, server_name: str) -> dict[str, str]:
    """Return the generated project plus reviewed full-graph dependency locks."""
    files = _BASE_PROJECT_FILES(package, server_name)
    for name in LOCK_NAMES:
        files[f"requirements/{name}"] = _read_contract_file(name)
    for source_name in SOURCE_NAMES:
        files[f"requirements/{source_name}"] = _read_contract_file(source_name)
    files["requirements/select_lock.py"] = _lock_selector()

    files["pyproject.toml"] = _replace_required(
        files["pyproject.toml"],
        'requires = ["setuptools>=75", "wheel"]',
        'requires = ["setuptools==83.0.0", "wheel==0.47.0"]',
        file_name="pyproject.toml",
    )
    files["pyproject.toml"] = _replace_required(
        files["pyproject.toml"],
        'dependencies = ["mcp>=1.27.2,<2", "uvicorn>=0.30,<1"]',
        'dependencies = ["mcp>=1.28.1,<2", "uvicorn>=0.51,<1"]',
        file_name="pyproject.toml",
    )
    files["pyproject.toml"] = _replace_required(
        files["pyproject.toml"],
        'dev = ["pytest==9.0.2"]',
        'dev = ["pytest==9.1.1"]',
        file_name="pyproject.toml",
    )

    files["README.md"] = _replace_required(
        files["README.md"],
        'pip install -e ".[dev]"',
        "LOCK=$(python requirements/select_lock.py dev)\n"
        'python -m pip install --require-hashes -r "$LOCK"\n'
        "python -m pip install --no-deps -e .\n"
        "python -m pip check",
        file_name="README.md",
    )
    files["README.md"] = _replace_required(
        files["README.md"],
        "the exact built wheel or container.",
        "the exact built wheel or container. Platform-specific runtime and development lockfiles "
        "contain the complete resolved graph and hashes; regenerate them only with the pinned lock workflow.",
        file_name="README.md",
    )

    files["Dockerfile"] = _replace_required(
        files["Dockerfile"],
        "COPY pyproject.toml README.md ./\nCOPY src ./src\nRUN pip install --no-cache-dir .",
        "COPY pyproject.toml README.md ./\n"
        "COPY requirements ./requirements\n"
        "COPY src ./src\n"
        "RUN pip install --no-cache-dir --require-hashes -r requirements/runtime-linux.lock \\\n"
        "    && pip install --no-cache-dir --no-deps . \\\n"
        "    && pip check",
        file_name="Dockerfile",
    )

    files[".github/workflows/ci.yml"] = _replace_required(
        files[".github/workflows/ci.yml"],
        "cache-dependency-path: pyproject.toml",
        "cache-dependency-path: requirements/*.lock",
        file_name=".github/workflows/ci.yml",
    )
    files[".github/workflows/ci.yml"] = _replace_required(
        files[".github/workflows/ci.yml"],
        '      - run: python -m pip install -e ".[dev]"\n'
        "      - run: python -m compileall -q src tests\n"
        "      - run: python -m pytest\n",
        "      - name: Select platform lock\n"
        "        shell: bash\n"
        "        run: python requirements/select_lock.py dev > selected-lock.txt\n"
        "      - name: Install complete hashed dependency graph\n"
        "        shell: bash\n"
        "        run: |\n"
        "          LOCK=$(cat selected-lock.txt)\n"
        '          python -m pip install --require-hashes -r "$LOCK"\n'
        "          python -m pip check\n"
        "      - run: python -m compileall -q src tests requirements/select_lock.py\n"
        "      - name: Build exact wheel\n"
        "        run: python -m build --wheel --no-isolation\n"
        "      - name: Install exact wheel without dependency resolution\n"
        "        shell: bash\n"
        "        run: |\n"
        "          python -m pip install --no-deps dist/*.whl\n"
        "          python -m pip check\n"
        "      - name: Test exact wheel with the official MCP client\n"
        "        run: python -m pytest\n",
        file_name=".github/workflows/ci.yml",
    )
    return files


vars(_implementation)["project_files"] = project_files
generate_project = _implementation.generate_project
main = _implementation.main

__all__ = [
    "PACKAGE_RE",
    "SERVER_RE",
    "RESERVED_PACKAGE_NAMES",
    "LOCK_NAMES",
    "SOURCE_NAMES",
    "project_files",
    "generate_project",
    "main",
]

if __name__ == "__main__":
    main()
