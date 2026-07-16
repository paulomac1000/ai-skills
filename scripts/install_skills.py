#!/usr/bin/env python3
"""Install every repository skill into an agent skill directory."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    source = root / "skills"
    args.target.expanduser().mkdir(parents=True, exist_ok=True)

    installed = 0
    for skill_dir in sorted(source.iterdir()):
        if not skill_dir.is_dir() or not (skill_dir / "SKILL.md").exists():
            continue
        destination = args.target.expanduser() / skill_dir.name
        if destination.exists():
            if not args.replace:
                print(f"skip {skill_dir.name}: destination exists (use --replace)")
                continue
            shutil.rmtree(destination)
        shutil.copytree(skill_dir, destination)
        installed += 1
        print(f"installed {skill_dir.name} -> {destination}")
    return 0 if installed else 1


if __name__ == "__main__":
    raise SystemExit(main())
