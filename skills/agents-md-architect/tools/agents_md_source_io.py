"""Confined reads and public-source surface discovery for gate-source auditing."""

from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPOSITORY_ROOT = TOOLS.parents[2]
CONTRACTS = REPOSITORY_ROOT / "contracts"
for candidate in (TOOLS, CONTRACTS):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from agents_md_source_types import MAX_CLASSIFIER_FILE_BYTES, WELL_KNOWN_TASK_RUNNERS  # noqa: E402
from confined_io import ConfinedReadError, read_utf8_bounded  # noqa: E402
from discover_repository import Discovery  # noqa: E402


def read_bounded(root: Path, relative: str) -> str:
    """Read one repository-relative source under the classifier byte limit."""
    try:
        text, _byte_count = read_utf8_bounded(root / relative, root, MAX_CLASSIFIER_FILE_BYTES)
    except ConfinedReadError as error:
        if error.code == "input.too-large":
            raise ValueError(f"Input exceeds the classifier size limit: {error.message}") from error
        raise ValueError(f"symlink-safe confined read failed: {error.message}") from error
    return text


def public_task_surfaces(discovery: Discovery) -> set[str]:
    """Select CI, task-runner, and Python/Node manifest command surfaces."""
    surfaces = set(discovery.ci_files)
    surfaces.update(path for path in discovery.task_runners if Path(path).name in WELL_KNOWN_TASK_RUNNERS)
    surfaces.update(path for path in discovery.manifests if Path(path).name in {"package.json", "pyproject.toml"})
    surfaces.update(path for path in discovery.files if Path(path).name in {"action.yml", "action.yaml"})
    return surfaces


def command_origin(relative: str, text: str, command: str) -> str:
    """Return the first source line containing a parsed command."""
    for line_number, line in enumerate(text.splitlines(), start=1):
        if command.strip() and command.strip() in line:
            return f"{relative}:{line_number}"
    return relative


def is_executable_shebang_script(root: Path, relative: str) -> bool:
    """Recognize an executable shebang script only within the scripts namespace."""
    if not relative.startswith("scripts/"):
        return False
    path = root / relative
    try:
        if path.is_symlink() or path.stat().st_mode & 0o111 == 0:
            return False
        return read_bounded(root, relative).startswith("#!")
    except (OSError, UnicodeError, ValueError):
        return False


def local_reference_resolves(reference: str, discovery_files: set[str] | frozenset[str]) -> bool:
    """Resolve a local `uses` reference as a reusable workflow or composite action."""
    target = reference[2:].rstrip("/") if reference.startswith("./") else reference.rstrip("/")
    if target:
        if target in discovery_files and target.endswith((".yml", ".yaml")):
            return True
        return any(f"{target}/action.{kind}" in discovery_files for kind in ("yml", "yaml"))
    return "action.yml" in discovery_files or "action.yaml" in discovery_files
