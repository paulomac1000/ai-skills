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
LOCK_IDS = (
    "linux-x64-py312",
    "linux-x64-py313",
    "linux-x64-py314",
    "macos-arm64-py312",
    "windows-x64-py312",
)
LOCK_NAMES = tuple(f"{kind}-{lock_id}.lock" for kind in ("runtime", "dev") for lock_id in LOCK_IDS)
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
import platform as host_platform
import sys
from pathlib import Path

PLATFORMS = {"linux": "linux", "darwin": "macos", "win32": "windows"}
ARCHITECTURES = {
    "amd64": "x64",
    "x86_64": "x64",
    "x64": "x64",
    "arm64": "arm64",
    "aarch64": "arm64",
}
SUPPORTED = {
    ("linux", "x64", "3.12"),
    ("linux", "x64", "3.13"),
    ("linux", "x64", "3.14"),
    ("macos", "arm64", "3.12"),
    ("windows", "x64", "3.12"),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("runtime", "dev"))
    args = parser.parse_args()
    platform = PLATFORMS.get(sys.platform)
    architecture = ARCHITECTURES.get(host_platform.machine().casefold())
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    if platform is None or architecture is None or (platform, architecture, version) not in SUPPORTED:
        raise SystemExit(
            f"unsupported lock target: {sys.platform}/{host_platform.machine()}/python-{version}"
        )
    lock_id = f"{platform}-{architecture}-py{version.replace('.', '')}"
    print(Path(__file__).with_name(f"{args.kind}-{lock_id}.lock"))
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
        'dependencies = ["mcp>=2.0.0,<3", "uvicorn>=0.30,<1"]',
        'dependencies = ["mcp>=2.0.0,<3", "uvicorn>=0.51,<1"]',
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
        'python -m venv .venv\n. .venv/bin/activate\npip install -e ".[dev]"',
        "python -m venv .venv\n\n"
        "# POSIX\n"
        ".venv/bin/python requirements/select_lock.py dev > selected-lock.txt\n"
        "LOCK=$(cat selected-lock.txt)\n"
        '.venv/bin/python -m pip install --require-hashes -r "$LOCK"\n'
        ".venv/bin/python -m pip install --no-deps -e .\n"
        ".venv/bin/python -m pip check\n\n"
        "# Windows PowerShell\n"
        ".venv\\Scripts\\python.exe requirements\\select_lock.py dev | Set-Content selected-lock.txt\n"
        "$Lock = Get-Content selected-lock.txt\n"
        ".venv\\Scripts\\python.exe -m pip install --require-hashes -r $Lock\n"
        ".venv\\Scripts\\python.exe -m pip install --no-deps -e .\n"
        ".venv\\Scripts\\python.exe -m pip check",
        file_name="README.md",
    )
    files["README.md"] = _replace_required(
        files["README.md"],
        "the exact built wheel or container.",
        "the exact built wheel or container. This generated architecture seed is not production-accepted "
        "until the applicable ci-cd-architect profile adds lint, formatting, typing, security, dependency, "
        "coverage, and deployment-artifact gates and the repository completes an adoption assessment. "
        "Platform-specific runtime and development lockfiles contain the complete resolved graph and hashes; "
        "regenerate them only with the pinned lock workflow.",
        file_name="README.md",
    )
    files["README.md"] = _replace_required(
        files["README.md"],
        "```\n\nStdio is the default.",
        "```\n\n"
        "## Build the container from the verified wheel\n\n"
        "The image never rebuilds the package from source. Build exactly one wheel first, pass its "
        "SHA-256 into Docker, and let the Dockerfile verify the copied bytes before installation:\n\n"
        "```bash\n"
        ".venv/bin/python -m build --wheel --no-isolation\n"
        "WHEEL=$(find dist -maxdepth 1 -type f -name '*.whl')\n"
        "test \"$(find dist -maxdepth 1 -type f -name '*.whl' | wc -l)\" -eq 1\n"
        "WHEEL_SHA256=$(sha256sum \"$WHEEL\" | cut -d' ' -f1)\n"
        f'docker build --build-arg WHEEL_SHA256="$WHEEL_SHA256" -t {package}:0.1.0 .\n'
        "```\n\n"
        "Stdio is the default.",
        file_name="README.md",
    )

    files["Dockerfile"] = _replace_required(
        files["Dockerfile"],
        "COPY pyproject.toml README.md ./\nCOPY src ./src\nRUN pip install --no-cache-dir .",
        "ARG WHEEL_SHA256\n"
        "COPY requirements/runtime-linux-x64-py312.lock /tmp/runtime.lock\n"
        "COPY dist/*.whl /tmp/wheel/\n"
        "RUN set -eux; \\\n"
        '    test -n "$WHEEL_SHA256"; \\\n'
        "    test \"$(find /tmp/wheel -maxdepth 1 -type f -name '*.whl' | wc -l)\" -eq 1; \\\n"
        "    wheel=\"$(find /tmp/wheel -maxdepth 1 -type f -name '*.whl')\"; \\\n"
        '    printf \'%s  %s\\n\' "$WHEEL_SHA256" "$wheel" | sha256sum --check --strict; \\\n'
        "    pip install --no-cache-dir --require-hashes -r /tmp/runtime.lock; \\\n"
        '    pip install --no-cache-dir --no-deps "$wheel"; \\\n'
        "    pip check; \\\n"
        "    rm -rf /tmp/wheel /tmp/runtime.lock\n"
        "LABEL org.opencontainers.image.source-wheel-sha256=$WHEEL_SHA256",
        file_name="Dockerfile",
    )
    files[".dockerignore"] = (
        "*\n!Dockerfile\n!requirements/\n!requirements/runtime-linux-x64-py312.lock\n!dist/\n!dist/*.whl\n"
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
        "      - name: Record exact wheel identity\n"
        "        id: wheel\n"
        "        shell: bash\n"
        "        run: |\n"
        "          set -euo pipefail\n"
        "          mapfile -t WHEELS < <(find dist -maxdepth 1 -type f -name '*.whl' -print)\n"
        '          test "${#WHEELS[@]}" -eq 1\n'
        "          WHEEL_SHA256=$(sha256sum \"${WHEELS[0]}\" | cut -d' ' -f1)\n"
        '          echo "path=${WHEELS[0]}" >> "$GITHUB_OUTPUT"\n'
        '          echo "sha256=$WHEEL_SHA256" >> "$GITHUB_OUTPUT"\n'
        "      - name: Install exact wheel without dependency resolution\n"
        "        shell: bash\n"
        "        run: |\n"
        '          python -m pip install --no-deps "${{ steps.wheel.outputs.path }}"\n'
        "          python -m pip check\n"
        "      - name: Test exact wheel with the official MCP client\n"
        "        run: python -m pytest\n"
        "      - name: Build container from exact wheel\n"
        "        run: >-\n"
        "          docker build\n"
        "          --build-arg WHEEL_SHA256=${{ steps.wheel.outputs.sha256 }}\n"
        "          --tag generated-mcp:ci .\n"
        "      - name: Verify container wheel identity\n"
        "        shell: bash\n"
        "        run: |\n"
        "          LABEL=$(docker inspect --format "
        "'{{ index .Config.Labels \"org.opencontainers.image.source-wheel-sha256\" }}' generated-mcp:ci)\n"
        '          test "$LABEL" = "${{ steps.wheel.outputs.sha256 }}"\n',
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
    "LOCK_IDS",
    "LOCK_NAMES",
    "SOURCE_NAMES",
    "project_files",
    "generate_project",
    "main",
]

if __name__ == "__main__":
    main()
