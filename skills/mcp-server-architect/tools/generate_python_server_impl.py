"""Render and validate the canonical official-SDK Python MCP server template."""

from __future__ import annotations

import ctypes
import errno
import json
import os
import re
import stat
import sys
import tomllib
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from jsonschema import Draft202012Validator

PACKAGE_NAME = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
MAX_TEMPLATE_BYTES = 2 * 1024 * 1024
TEMPLATE_ROOT = Path(__file__).with_name("python-template")
SKILL_ROOT = Path(__file__).resolve().parent.parent
REPOSITORY_ROOT = SKILL_ROOT.parents[1]
LOCK_ROOT = SKILL_ROOT / "locks"
CONTRACT_ROOT = REPOSITORY_ROOT / "contracts"
LOCK_NAMES = (
    "dev-linux-x64-py312.lock",
    "dev-linux-x64-py313.lock",
    "dev-linux-x64-py314.lock",
    "dev-macos-arm64-py312.lock",
    "dev-windows-x64-py312.lock",
    "runtime-linux-x64-py312.lock",
    "runtime-linux-x64-py313.lock",
    "runtime-linux-x64-py314.lock",
    "runtime-macos-arm64-py312.lock",
    "runtime-windows-x64-py312.lock",
)
COPIED_CONTRACTS = ("capability-manifest.schema.json",)
TOKENS = ("__PACKAGE__", "__DISTRIBUTION__", "__SERVER_NAME__")


def _read_regular_utf8(path: Path, *, maximum: int = MAX_TEMPLATE_BYTES) -> str:
    if path.is_symlink():
        raise ValueError(f"template input must not be a symlink: {path}")
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"template input must be a regular file: {path}")
    if metadata.st_size > maximum:
        raise ValueError(f"template input exceeds {maximum} bytes: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"template input must be UTF-8: {path}") from exc


def _validate_inputs(package_name: str, server_name: str) -> None:
    if not PACKAGE_NAME.fullmatch(package_name):
        raise ValueError("package name must match ^[a-z][a-z0-9_]{1,63}$")
    if not server_name or len(server_name) > 128 or any(ord(character) < 0x20 for character in server_name):
        raise ValueError("server name must contain 1-128 printable characters")


def _render(value: str, package_name: str, server_name: str) -> str:
    return (
        value.replace("__PACKAGE__", package_name)
        .replace("__DISTRIBUTION__", package_name.replace("_", "-"))
        .replace("__SERVER_NAME__", server_name)
    )


def _safe_relative_path(raw: str) -> PurePosixPath:
    if not raw or "\\" in raw:
        raise ValueError(f"generated path must be a repository-relative POSIX path: {raw!r}")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"generated path escapes project root: {raw!r}")
    return path


def project_files(package_name: str, server_name: str) -> dict[str, str]:
    """Return the complete rendered project from one canonical template tree."""
    _validate_inputs(package_name, server_name)
    if not TEMPLATE_ROOT.is_dir() or TEMPLATE_ROOT.is_symlink():
        raise ValueError("canonical Python template directory is missing or unsafe")

    rendered: dict[str, str] = {}
    for template in sorted(TEMPLATE_ROOT.rglob("*.template")):
        relative_template = template.relative_to(TEMPLATE_ROOT).as_posix()
        output_name = _render(relative_template.removesuffix(".template"), package_name, server_name)
        output_path = _safe_relative_path(output_name).as_posix()
        if output_path in rendered:
            raise ValueError(f"duplicate generated path: {output_path}")
        rendered[output_path] = _render(_read_regular_utf8(template), package_name, server_name)

    for lock_name in LOCK_NAMES:
        rendered[f"locks/{lock_name}"] = _read_regular_utf8(
            LOCK_ROOT / lock_name,
            maximum=4 * 1024 * 1024,
        )
    for contract_name in COPIED_CONTRACTS:
        destination = f"src/{package_name}/contracts/{contract_name}"
        rendered[destination] = _read_regular_utf8(CONTRACT_ROOT / contract_name)

    if not rendered:
        raise ValueError("canonical Python template did not produce any files")
    unresolved = {
        path: token
        for path, content in rendered.items()
        for token in TOKENS
        if token in path or token in content
    }
    if unresolved:
        raise ValueError(f"unresolved template tokens: {unresolved}")
    return rendered


def _validate_capabilities(files: Mapping[str, str], package_name: str) -> None:
    schema_path = f"src/{package_name}/contracts/capability-manifest.schema.json"
    schema = json.loads(files[schema_path])
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    manifest_paths = sorted(
        path
        for path in files
        if path.startswith(f"src/{package_name}/capabilities/") and path.endswith(".json")
    )
    if not manifest_paths:
        raise ValueError("generated project has no capability manifests")
    identifiers: set[str] = set()
    for path in manifest_paths:
        manifest = json.loads(files[path])
        errors = sorted(
            validator.iter_errors(manifest),
            key=lambda item: tuple(item.absolute_path),
        )
        if errors:
            raise ValueError(f"{path}: {errors[0].message}")
        capability_id = manifest["id"]
        if capability_id in identifiers:
            raise ValueError(f"duplicate generated capability id: {capability_id}")
        identifiers.add(capability_id)


def validate_generated_project(files: Mapping[str, str], package_name: str) -> None:
    """Reject stale, incomplete, or policy-incompatible rendered output before publication."""
    required = {
        "pyproject.toml",
        "README.md",
        "Dockerfile",
        ".github/workflows/ci.yml",
        f"src/{package_name}/server.py",
        f"src/{package_name}/kernel.py",
        f"src/{package_name}/manifest.py",
        f"src/{package_name}/security.py",
    }
    missing = sorted(required - set(files))
    if missing:
        raise ValueError(f"canonical template is incomplete: {missing}")

    pyproject = tomllib.loads(files["pyproject.toml"])
    if pyproject.get("project", {}).get("name") != package_name.replace("_", "-"):
        raise ValueError("generated package identity does not match requested name")
    for path, content in files.items():
        if path.endswith(".py"):
            compile(content, path, "exec")
    _validate_capabilities(files, package_name)

    workflow = files[".github/workflows/ci.yml"]
    forbidden_workflow_tokens = (
        "ubuntu-latest",
        "contents: write",
        "packages: write",
        "id-token: write",
    )
    if any(token in workflow for token in forbidden_workflow_tokens):
        raise ValueError("generated CI violates the trusted-CI baseline")
    if "concurrency:" not in workflow or "persist-credentials: false" not in workflow:
        raise ValueError("generated CI lacks concurrency or credential confinement")

    dockerfile = files["Dockerfile"]
    if "@sha256:" not in dockerfile or "COPY ${WHEEL}" not in dockerfile:
        raise ValueError("generated container must pin its base and copy the exact wheel")
    if "COPY src" in dockerfile or "pip install --no-cache-dir ." in dockerfile:
        raise ValueError("generated container must not rebuild the application from source")

    stale_manifest_fields = {"operational_impact", "active", "side_effects"}
    for path, content in files.items():
        if "/capabilities/" not in path or not path.endswith(".json"):
            continue
        manifest = json.loads(content)
        observed_legacy_fields = sorted(stale_manifest_fields.intersection(manifest))
        if observed_legacy_fields:
            raise ValueError(
                f"{path}: generated capability manifest contains legacy fields: "
                f"{observed_legacy_fields}"
            )


def _write_files(root: Path, files: Mapping[str, str]) -> None:
    for raw_path, content in sorted(files.items()):
        relative = _safe_relative_path(raw_path)
        destination = root.joinpath(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    if os.name == "nt":
        return
    for directory, _, _names in os.walk(root, topdown=False):
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _rename_noreplace(source: Path, destination: Path) -> None:
    source_bytes = os.fsencode(source)
    destination_bytes = os.fsencode(destination)
    if sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise RuntimeError("atomic no-replace publication requires renameat2")
        renameat2.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        renameat2.restype = ctypes.c_int
        if renameat2(-100, source_bytes, -100, destination_bytes, 1) != 0:
            error = ctypes.get_errno()
            if error in {errno.EEXIST, errno.ENOTEMPTY}:
                raise FileExistsError(destination)
            raise OSError(error, os.strerror(error), destination)
        return
    if sys.platform == "darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        renamex_np = getattr(libc, "renamex_np", None)
        if renamex_np is None:
            raise RuntimeError("atomic no-replace publication requires renamex_np")
        renamex_np.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
        renamex_np.restype = ctypes.c_int
        if renamex_np(source_bytes, destination_bytes, 0x00000004) != 0:
            error = ctypes.get_errno()
            if error in {errno.EEXIST, errno.ENOTEMPTY}:
                raise FileExistsError(destination)
            raise OSError(error, os.strerror(error), destination)
        return
    if os.name == "nt":
        move_file = ctypes.windll.kernel32.MoveFileW
        move_file.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        move_file.restype = ctypes.c_int
        if not move_file(str(source), str(destination)):
            error = ctypes.get_last_error()
            if error in {80, 183}:
                raise FileExistsError(destination)
            raise OSError(error, os.strerror(error), destination)
        return
    raise RuntimeError(f"atomic no-replace publication is unsupported on {sys.platform}")
