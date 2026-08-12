#!/usr/bin/env python3
"""Detect real-world downstream integration hygiene gaps before they reach hosted CI."""

from __future__ import annotations

import argparse
import re
import stat
from pathlib import Path

MAX_FILE_BYTES = 1024 * 1024
SCANNERS = ("semgrep", "bandit", "trivy", "gitleaks")
TRUSTED_REVISION = re.compile(
    r"(?im)\b[A-Z0-9_]*(?:AUDITOR|COLLECTOR|VALIDATOR|VERIFIER)[A-Z0-9_]*REVISION\b\s*[:=]\s*[\"']?([0-9a-f]{40})"
)


def _read(path: Path) -> str:
    try:
        metadata = path.lstat()
    except OSError:
        return ""
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_FILE_BYTES:
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _operational_files(root: Path) -> list[Path]:
    paths = [root / "Makefile", root / ".pre-commit-config.yaml"]
    workflows = root / ".github/workflows"
    if workflows.is_dir():
        paths.extend(sorted(workflows.glob("*.yml")))
        paths.extend(sorted(workflows.glob("*.yaml")))
    scripts = root / "scripts"
    if scripts.is_dir():
        paths.extend(sorted(scripts.glob("*.sh")))
        paths.extend(sorted(scripts.glob("*.py")))
    return [path for path in paths if path.exists()]


def _afds_direct_invocations(files: list[Path]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for path in files:
        lines = []
        for raw in _read(path).splitlines():
            lowered = raw.casefold()
            if "afds-doc-writer/validate.py" in lowered or "afds_validate_" in lowered:
                lines.append(" ".join(raw.strip().split()))
        if lines:
            result[path.as_posix()] = sorted(set(lines))
    return result


def _security_hook_findings(root: Path) -> list[str]:
    path = root / ".pre-commit-config.yaml"
    text = _read(path)
    lowered = text.casefold()
    findings: list[str] = []
    for scanner in SCANNERS:
        if scanner not in lowered:
            continue
        no_op_patterns = (
            rf"if\s+command\s+-v\s+{re.escape(scanner)}",
            rf"command\s+-v\s+{re.escape(scanner)}[^\n]*(?:\|\||;\s*then)",
            rf"{re.escape(scanner)}[^\n]*\|\|\s*(?:true|echo)",
            r"remains\s+a\s+required\s+ci\s+gate",
        )
        if any(re.search(pattern, lowered) for pattern in no_op_patterns):
            findings.append(
                f"{path}: security scanner {scanner} may succeed locally when the scanner is unavailable"
            )
    return findings


def check_repository(root: Path) -> list[str]:
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("repository root must be a directory")
    files = _operational_files(root)
    findings = _security_hook_findings(root)
    afds = _afds_direct_invocations(files)
    if len(afds) > 1:
        locations = ", ".join(sorted(afds))
        findings.append(
            "AFDS is invoked directly from multiple operational entrypoints "
            f"({locations}); route pre-commit and CI through one canonical docs-check command"
        )
    combined = "\n".join(_read(path) for path in files)
    lowered = combined.casefold()
    trusted_lock = (root / "trusted-executable-sources.lock.yaml").is_file()
    if "afds_validate_" in lowered and ".ai-skills/skills/afds-doc-writer/validate.py" in lowered and not trusted_lock:
        findings.append(
            "vendored and authority AFDS validators coexist without trusted-executable-sources.lock.yaml"
        )
    revisions = sorted(set(TRUSTED_REVISION.findall(combined)))
    if revisions and not trusted_lock:
        findings.append(
            "hardcoded trusted auditor/collector/validator revision exists outside a trusted executable source lock"
        )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path, nargs="?", default=Path("."))
    args = parser.parse_args(argv)
    findings = check_repository(args.repository)
    for finding in findings:
        print(f"ERROR: {finding}")
    print(f"consumer trust hygiene findings: {len(findings)}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
