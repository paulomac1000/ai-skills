#!/usr/bin/env python3
"""Deterministic structural/drift audit for repository README files."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import unquote

PROFILE_REQUIREMENTS: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "generic": [],
    "server": [
        ("quick-start", ("quick start", "getting started", "installation", "install")),
        ("security", ("security", "safety")),
    ],
    "mcp-server": [
        ("quick-start", ("quick start", "getting started", "installation", "install")),
        ("security", ("security", "safety", "authorization")),
        ("mcp-usage", ("mcp", "connect", "client", "transport")),
    ],
    "cli": [
        ("installation", ("installation", "install", "quick start", "getting started")),
        ("usage", ("usage", "quick start", "examples", "example")),
    ],
    "library": [
        ("installation", ("installation", "install", "quick start", "getting started")),
        ("example", ("usage", "example", "examples", "quick start")),
    ],
    "application": [
        ("quick-start", ("quick start", "getting started", "installation", "install", "run")),
    ],
}


def strip_fenced_code(text: str) -> str:
    out = []
    in_fence = False
    fence_char = ""
    fence_len = 0
    for line in text.splitlines():
        match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if match:
            marker = match.group(1)
            if not in_fence:
                in_fence = True
                fence_char = marker[0]
                fence_len = len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_len:
                in_fence = False
            out.append("")
            continue
        out.append("" if in_fence else line)
    return "\n".join(out)


def github_slug(text: str) -> str:
    value = re.sub(r"<[^>]+>", "", text)
    value = re.sub(r"[`*_~]", "", value)
    value = value.strip().lower()
    value = re.sub(r"[^\w\- ]", "", value, flags=re.UNICODE)
    value = re.sub(r"\s+", "-", value)
    return value


def markdown_links(text: str):
    # Good enough for local README auditing; intentionally ignores nested parens.
    pattern = re.compile(r"(!?)\[([^\]]*)\]\(([^)\s]+)(?:\s+[\"'][^\"']*[\"'])?\)")
    yield from pattern.finditer(text)


def html_images(text: str):
    yield from re.finditer(r"<img\b[^>]*>", text, re.IGNORECASE)


def is_external(target: str) -> bool:
    lower = target.lower()
    return lower.startswith(("http://", "https://", "mailto:", "tel:", "data:"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("readme", nargs="?", default="README.md")
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILE_REQUIREMENTS),
        default="generic",
    )
    parser.add_argument("--strict", action="store_true", help="warnings also fail")
    args = parser.parse_args()

    path = Path(args.readme)
    if not path.is_file():
        print(f"ERROR: README not found: {path}")
        return 2

    text = path.read_text(encoding="utf-8")
    visible = strip_fenced_code(text)
    lines = visible.splitlines()
    errors: list[str] = []
    warnings: list[str] = []

    headings = []
    for lineno, line in enumerate(lines, start=1):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            headings.append((lineno, len(match.group(1)), match.group(2).strip()))

    h1s = [heading for heading in headings if heading[1] == 1]
    if len(h1s) != 1:
        errors.append(f"expected exactly one H1, found {len(h1s)}")

    last_level = None
    for lineno, level, title in headings:
        if last_level is not None and level > last_level + 1:
            warnings.append(f"line {lineno}: heading jumps H{last_level} -> H{level}: {title}")
        last_level = level

    if headings and headings[0][0] > 30:
        warnings.append("first semantic heading appears after line 30")

    heading_titles = [title.lower() for _, _, title in headings]
    for requirement, aliases in PROFILE_REQUIREMENTS[args.profile]:
        if not any(any(alias in title for alias in aliases) for title in heading_titles):
            warnings.append(f"profile {args.profile}: no heading found for {requirement}")

    if any(title in {"contents", "table of contents", "toc"} for title in heading_titles):
        warnings.append("manual table of contents present; keep only if it materially improves navigation")

    if len(text.splitlines()) > 600:
        warnings.append(
            f"README is {len(text.splitlines())} lines; review whether deep reference material belongs in docs/"
        )

    badge_count = len(re.findall(r"(?:shields\.io|badge\.svg)", text, re.IGNORECASE))
    if badge_count > 5:
        warnings.append(f"{badge_count} badge-like images detected; opening badge set should stay focused")

    suspicious = {
        "static build-passing badge": r"shields\.io/badge/build-(?:passing|success|green)",
        "hard-coded coverage claim": r"\bcoverage\b.{0,24}\b\d{1,3}(?:\.\d+)?%",
        "hand-maintained test count": r"\b\d[\d,._]*\s+tests?\b",
        "hand-maintained tool count": r"\b\d+\s+(?:MCP\s+)?tools?\b",
        "hard-coded version badge": r"shields\.io/badge/version-[0-9]",
    }
    for label, pattern in suspicious.items():
        if re.search(pattern, visible, re.IGNORECASE | re.DOTALL):
            warnings.append(f"possible volatile fact: {label}")

    placeholder_patterns = {
        "TODO/FIXME/TBD marker": r"\b(?:TODO|FIXME|TBD)\b",
        "template project-name marker": r"\{\{PROJECT_NAME\}\}|YOUR_PROJECT_NAME",
    }
    for label, pattern in placeholder_patterns.items():
        if re.search(pattern, visible, re.IGNORECASE):
            errors.append(label)

    readme_dir = path.resolve().parent
    slugs = {github_slug(title) for _, _, title in headings}
    for match in markdown_links(visible):
        is_image, alt, target = match.groups()
        target = unquote(target)
        if is_image and not alt.strip():
            warnings.append("markdown image has empty alt text; keep only if the image is intentionally decorative")
        if is_external(target):
            continue
        if target.startswith("#"):
            anchor = target[1:].lower()
            if anchor and anchor not in slugs:
                warnings.append(f"local anchor may be broken: {target}")
            continue
        target_path = target.split("#", 1)[0]
        if not target_path:
            continue
        candidate = (readme_dir / target_path).resolve()
        if not candidate.exists():
            errors.append(f"broken relative link/image: {target_path}")

    for match in html_images(visible):
        tag = match.group(0)
        alt_match = re.search(r"\balt\s*=\s*([\"'])(.*?)\1", tag, re.IGNORECASE)
        if alt_match is None:
            errors.append("HTML <img> missing alt attribute")
        elif not alt_match.group(2).strip():
            warnings.append("HTML <img> has empty alt text; keep only if intentionally decorative")

    if re.search(r"(?i)shields\.io/badge/license-(?:mit|apache|gpl)", text):
        if not any((readme_dir / name).exists() for name in ("LICENSE", "LICENSE.md", "LICENSE.txt")):
            warnings.append("license badge present but no root LICENSE file detected")

    print(f"README audit: {path} [{args.profile}]")
    for item in errors:
        print(f"ERROR: {item}")
    for item in warnings:
        print(f"WARN: {item}")
    print(f"Summary: {len(errors)} error(s), {len(warnings)} warning(s)")

    if errors or (args.strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
