"""OpenAI Codex effective instruction-chain validation."""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
CONTRACTS = TOOLS.parents[2] / "contracts"
if str(CONTRACTS) not in sys.path:
    sys.path.insert(0, str(CONTRACTS))

from agents_md_parse import trusted_input  # noqa: E402
from agents_md_types import MAX_INSTRUCTION_FILE_BYTES, Finding  # noqa: E402
from confined_io import ConfinedReadError, read_utf8_bounded  # noqa: E402
from discover_repository import discover  # noqa: E402

CODEX_DEFAULT_PROJECT_DOC_MAX_BYTES = 32 * 1024
CODEX_PRIMARY_FILENAMES = ("AGENTS.override.md", "AGENTS.md")


def _normalize_fallback_filenames(values: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        name = value.strip()
        if not name or name in CODEX_PRIMARY_FILENAMES or name in normalized:
            continue
        candidate = Path(name)
        if candidate.name != name or candidate.is_absolute() or name in {".", ".."}:
            raise ValueError(f"Invalid Codex project-doc fallback filename: {value}")
        normalized.append(name)
    return tuple(normalized)


def _validate_codex_context(
    root: Path,
    fallback_filenames: Iterable[str],
    max_bytes: int,
) -> list[Finding]:
    """Validate effective Codex root-to-directory instruction chains."""
    if max_bytes <= 0:
        return [
            Finding(
                str(root),
                "error",
                "platform.invalid-context-budget",
                1,
                "Codex project_doc_max_bytes must be positive.",
            )
        ]
    try:
        fallbacks = _normalize_fallback_filenames(fallback_filenames)
    except ValueError as error:
        return [Finding(str(root), "error", "platform.invalid-fallback", 1, str(error))]

    inventory = discover(root)
    findings = [Finding(str(root), "error", "platform.discovery-incomplete", 1, issue) for issue in inventory.issues]
    candidate_names = (*CODEX_PRIMARY_FILENAMES, *fallbacks)
    files = set(inventory.files)
    symlinks = set(inventory.symlinks)
    candidate_directories: set[Path] = {root}
    selected_by_directory: dict[Path, Path] = {}

    for relative in sorted(files):
        path = Path(relative)
        if path.name in candidate_names:
            candidate_directories.add(root / path.parent)
    for relative in sorted(symlinks):
        path = Path(relative)
        if path.name in candidate_names:
            findings.append(
                Finding(
                    relative,
                    "error",
                    "platform.codex-symlink",
                    1,
                    "Codex instruction files must not be symlinks.",
                )
            )

    for directory in sorted(candidate_directories, key=lambda item: (len(item.parts), item.as_posix())):
        relative_directory = directory.relative_to(root)
        for name in candidate_names:
            relative = (relative_directory / name).as_posix()
            if relative == ".":
                relative = name
            if relative in files:
                selected_by_directory[directory] = root / relative
                break

    sizes: dict[Path, int] = {}
    for path in selected_by_directory.values():
        trusted, code, message = trusted_input(path, root)
        if code is not None or trusted is None:
            findings.append(
                Finding(
                    str(path),
                    "error",
                    code or "platform.codex-unreadable",
                    1,
                    message or "Invalid input.",
                )
            )
            continue
        try:
            _text, byte_count = read_utf8_bounded(trusted, root, MAX_INSTRUCTION_FILE_BYTES)
        except ConfinedReadError as error:
            findings.append(
                Finding(
                    str(path),
                    "error",
                    error.code,
                    1,
                    error.message,
                )
            )
            continue
        sizes[path] = byte_count

    for target_directory in sorted(selected_by_directory, key=lambda item: (len(item.parts), item.as_posix())):
        chain = [
            (directory, path)
            for directory, path in selected_by_directory.items()
            if directory == root or directory == target_directory or directory in target_directory.parents
        ]
        chain.sort(key=lambda item: len(item[0].parts))
        total = sum(sizes.get(path, 0) for _, path in chain)
        if total <= max_bytes:
            continue
        rendered = ", ".join(path.relative_to(root).as_posix() for _, path in chain)
        findings.append(
            Finding(
                str(selected_by_directory[target_directory]),
                "error",
                "platform.codex-context-budget",
                1,
                f"Effective Codex instruction chain for {target_directory.relative_to(root).as_posix() or '.'} "
                f"is {total} UTF-8 bytes and exceeds project_doc_max_bytes={max_bytes}: {rendered}",
            )
        )
    return findings
