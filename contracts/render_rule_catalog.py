#!/usr/bin/env python3
"""Render the rule catalog with full repository paths and content digests."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG = Path(__file__).with_name("rule-catalog.yaml")
MAX_CATALOG_BYTES = 512 * 1024
MAX_SOURCE_BYTES = 4 * 1024 * 1024
HEADING = re.compile(r"^#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$", re.MULTILINE)
NON_SLUG = re.compile(r"[^a-z0-9 -]")
SPACES = re.compile(r"[ -]+")


def _slug(value: str) -> str:
    normalized = NON_SLUG.sub("", value.casefold().strip())
    return SPACES.sub("-", normalized).strip("-")


def _safe_regular_file(root: Path, raw: str, maximum: int) -> Path:
    if not raw or "\\" in raw:
        raise ValueError("path must be a repository-relative POSIX path")
    pure = PurePosixPath(raw)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError("path must remain inside the repository")
    current = root
    for part in pure.parts:
        current /= part
        if not os.path.lexists(current):
            raise ValueError(f"path does not exist: {raw}")
        mode = current.lstat().st_mode
        if stat.S_ISLNK(mode):
            raise ValueError(f"path contains a symlink: {raw}")
    metadata = current.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"path is not a regular file: {raw}")
    if metadata.st_size > maximum:
        raise ValueError(f"path exceeds {maximum} bytes: {raw}")
    return current


def _read_utf8(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"file must be UTF-8: {path}") from exc


def _load_catalog(path: Path) -> Mapping[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("rule catalog must be a regular non-symlink file")
    if path.stat().st_size > MAX_CATALOG_BYTES:
        raise ValueError(f"rule catalog exceeds {MAX_CATALOG_BYTES} bytes")
    try:
        value = yaml.safe_load(_read_utf8(path))
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid rule catalog YAML: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ValueError("rule catalog root must be an object")
    return value


def _full_source(skill: str, source: object) -> tuple[str, str]:
    if not isinstance(source, str) or source.count("#") != 1:
        raise ValueError("rule source must contain one path and one anchor")
    raw_path, anchor = source.split("#", 1)
    if not raw_path or not anchor:
        raise ValueError("rule source path and anchor must be non-empty")
    if raw_path.startswith("skills/"):
        full_path = raw_path
    else:
        full_path = f"skills/{skill}/{raw_path}"
    expected_prefix = f"skills/{skill}/"
    if not full_path.startswith(expected_prefix):
        raise ValueError(f"rule source must belong to {skill}")
    return full_path, anchor


def render_catalog(
    catalog_path: Path = DEFAULT_CATALOG,
    repository_root: Path = ROOT,
) -> dict[str, Any]:
    """Return a deterministic external catalog with unambiguous source identities."""
    catalog = _load_catalog(catalog_path)
    root = repository_root.resolve(strict=True)
    skills = catalog.get("skills")
    if not isinstance(skills, Mapping):
        raise ValueError("rule catalog skills must be an object")

    rendered_skills: dict[str, Any] = {}
    for skill in sorted(skills):
        raw_skill = skills[skill]
        if not isinstance(skill, str) or not isinstance(raw_skill, Mapping):
            raise ValueError("skill catalog entries must be objects")
        raw_rules = raw_skill.get("rules")
        if not isinstance(raw_rules, list):
            raise ValueError(f"skill {skill} must contain a rule list")
        rendered_rules: list[dict[str, Any]] = []
        for index, raw_rule in enumerate(raw_rules):
            if not isinstance(raw_rule, Mapping):
                raise ValueError(f"skill {skill} rule {index} must be an object")
            full_path, anchor = _full_source(skill, raw_rule.get("source"))
            source_path = _safe_regular_file(root, full_path, MAX_SOURCE_BYTES)
            content = _read_utf8(source_path)
            anchors = {_slug(heading) for heading in HEADING.findall(content)}
            if anchor not in anchors:
                raise ValueError(f"{skill} rule {raw_rule.get('id')}: missing source anchor {anchor!r}")
            rendered = dict(raw_rule)
            rendered["source"] = f"{full_path}#{anchor}"
            rendered["source_digest"] = "sha256:" + hashlib.sha256(source_path.read_bytes()).hexdigest()
            rendered_rules.append(rendered)
        rendered_skills[skill] = {"rules": rendered_rules}

    catalog_bytes = catalog_path.read_bytes()
    return {
        "schema_version": 1,
        "catalog_version": catalog.get("catalog_version"),
        "generated_from": {
            "path": catalog_path.resolve().relative_to(root).as_posix(),
            "digest": "sha256:" + hashlib.sha256(catalog_bytes).hexdigest(),
        },
        "skills": rendered_skills,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    try:
        rendered = render_catalog(args.catalog, args.repository_root)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    serialized = json.dumps(rendered, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(serialized, end="")
    else:
        if os.path.lexists(args.output):
            parser.error("output already exists; refusing to overwrite")
        args.output.write_text(serialized, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
