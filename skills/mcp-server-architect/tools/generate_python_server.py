#!/usr/bin/env python3
"""Public entry point for the executable Python MCP server generator.

The implementation module owns the security-shaped source templates. This facade
adds the release contract that must stay small and reviewable: supported SDK
versions, deterministic constraints, exact-wheel CI, and container installation
from the same constrained dependency set.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_IMPLEMENTATION_PATH = Path(__file__).with_name("generate_python_server_impl.py")
_SPEC = importlib.util.spec_from_file_location("mcp_python_generator_implementation", _IMPLEMENTATION_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"Cannot load generator implementation: {_IMPLEMENTATION_PATH}")
_implementation = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _implementation
_SPEC.loader.exec_module(_implementation)

# A generated package must not shadow any direct runtime or test dependency.
RESERVED_PACKAGE_NAMES = frozenset(_implementation.RESERVED_PACKAGE_NAMES) | {"pytest"}
_implementation.RESERVED_PACKAGE_NAMES = RESERVED_PACKAGE_NAMES

PACKAGE_RE = _implementation.PACKAGE_RE
SERVER_RE = _implementation.SERVER_RE
_BASE_PROJECT_FILES = _implementation.project_files

# Stable-lane constraints. Project metadata keeps compatible ranges so the wheel
# remains reusable; CI, local verification, and the container consume this exact
# set. Candidate-lane upgrades are deliberate changes to this reviewed file.
REQUIREMENTS_LOCK = """\
# Generated stable lane. Update only with an SDK compatibility review and smoke.
build==1.5.1
mcp==1.28.1
pytest==9.0.2
setuptools==83.0.0
uvicorn==0.51.0
wheel==0.47.0
"""


def _replace_required(text: str, old: str, new: str, *, file_name: str) -> str:
    """Replace one reviewed template fragment or fail instead of drifting silently."""
    occurrences = text.count(old)
    if occurrences != 1:
        raise RuntimeError(
            f"expected exactly one {old!r} fragment in generated {file_name}, found {occurrences}"
        )
    return text.replace(old, new)


def project_files(package: str, server_name: str) -> dict[str, str]:
    """Return the generated project plus its deterministic artifact contract."""
    files = _BASE_PROJECT_FILES(package, server_name)
    files["requirements.lock"] = REQUIREMENTS_LOCK

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

    files["README.md"] = _replace_required(
        files["README.md"],
        'pip install -e ".[dev]"',
        'pip install --constraint requirements.lock -e ".[dev]"',
        file_name="README.md",
    )
    files["README.md"] = _replace_required(
        files["README.md"],
        "the exact built wheel or container.",
        "the exact built wheel or container. Treat `requirements.lock` as the reviewed stable lane; "
        "upgrade it only together with the official-client smoke.",
        file_name="README.md",
    )

    files["Dockerfile"] = _replace_required(
        files["Dockerfile"],
        "COPY pyproject.toml README.md ./\nCOPY src ./src\nRUN pip install --no-cache-dir .",
        "COPY pyproject.toml README.md requirements.lock ./\n"
        "COPY src ./src\n"
        "ENV PIP_CONSTRAINT=/app/requirements.lock\n"
        "RUN pip install --no-cache-dir .",
        file_name="Dockerfile",
    )

    files[".github/workflows/ci.yml"] = _replace_required(
        files[".github/workflows/ci.yml"],
        "cache-dependency-path: pyproject.toml",
        "cache-dependency-path: requirements.lock",
        file_name=".github/workflows/ci.yml",
    )
    files[".github/workflows/ci.yml"] = _replace_required(
        files[".github/workflows/ci.yml"],
        '                  - run: python -m pip install -e ".[dev]"\n'
        "                  - run: python -m compileall -q src tests\n"
        "                  - run: python -m pytest\n",
        "                  - name: Install locked build tooling\n"
        "                    run: >-\n"
        "                      python -m pip install --constraint requirements.lock\n"
        "                      build==1.5.1 setuptools==83.0.0 wheel==0.47.0\n"
        "                  - run: python -m compileall -q src tests\n"
        "                  - name: Build exact wheel\n"
        "                    run: python -m build --wheel --no-isolation\n"
        "                  - name: Test exact wheel with the official MCP client\n"
        "                    shell: bash\n"
        "                    run: |\n"
        "                      python -m venv .artifact-venv\n"
        "                      .artifact-venv/bin/python -m pip install --constraint requirements.lock dist/*.whl pytest==9.0.2\n"
        "                      .artifact-venv/bin/python -m pytest\n",
        file_name=".github/workflows/ci.yml",
    )
    return files


# The implementation's atomic publisher resolves this symbol at call time. Patch
# it once so CLI and imported use paths produce the same reviewed file set.
_implementation.project_files = project_files
generate_project = _implementation.generate_project
main = _implementation.main

__all__ = [
    "PACKAGE_RE",
    "SERVER_RE",
    "RESERVED_PACKAGE_NAMES",
    "REQUIREMENTS_LOCK",
    "project_files",
    "generate_project",
    "main",
]

if __name__ == "__main__":
    main()
