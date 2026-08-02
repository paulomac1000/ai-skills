from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRODUCTION_CI_REVISION = "46568f9b87e6431eb1add23514046616dfa74fbb"
SELF = ".github/scripts/refresh_dependency_set.py"

ACTION_UPDATES = {
    "actions/checkout": (
        "34e114876b0b11c390a56381ad16ebd13914f8d5",
        "3d3c42e5aac5ba805825da76410c181273ba90b1",
        "v7.0.1",
    ),
    "actions/setup-python": (
        "a26af69be951a213d495a4c3e4e4022e16d87065",
        "5fda3b95a4ea91299a34e894583c3862153e4b97",
        "v7.0.0",
    ),
    "actions/setup-dotnet": (
        "9a946fdbd5fb07b82b2f5a4466058b876ab72bb2",
        "a98b56852c35b8e3190ac28c8c2271da59106c68",
        "v6.0.0",
    ),
}

PACKAGE_UPDATES = {
    "mcp==1.28.1": "mcp==2.0.0",
    "ruff==0.15.22": "ruff==0.16.0",
    "types-PyYAML==6.0.12.20260518": "types-PyYAML==6.0.12.20260724",
}

VERSION_COMMENT = re.compile(r"#\s*v?\d+(?:\.\d+){0,2}\s*$")
ACTION_REFERENCE = re.compile(
    r"(?P<action>actions/(?:checkout|setup-python|setup-dotnet))@(?P<revision>[^\s#\"']+)"
)
TEXT_SUFFIXES = {".in", ".j2", ".json", ".md", ".py", ".template", ".toml", ".yaml", ".yml"}


def tracked_files() -> list[str]:
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return [item.decode("utf-8") for item in output.split(b"\0") if item]


def restore_production_ci() -> None:
    if os.environ.get("RESTORE_PRODUCTION_CI") != "1":
        return
    content = subprocess.check_output(
        ["git", "show", f"{PRODUCTION_CI_REVISION}:.github/workflows/ci.yml"],
        cwd=ROOT,
    )
    (ROOT / ".github/workflows/ci.yml").write_bytes(content)


def replace_action_reference(match: re.Match[str]) -> str:
    action = match.group("action")
    new_sha = ACTION_UPDATES[action][1]
    return f"{action}@{new_sha}"


def update_line(line: str) -> str:
    updated = ACTION_REFERENCE.sub(replace_action_reference, line)
    for action, (_, _, version) in ACTION_UPDATES.items():
        if action in updated and "#" in updated:
            updated = VERSION_COMMENT.sub(f"# {version}", updated)
    for old, new in PACKAGE_UPDATES.items():
        updated = updated.replace(old, new)
    return updated


def readable_tracked_text() -> list[tuple[str, str]]:
    documents: list[tuple[str, str]] = []
    for relative in tracked_files():
        if relative == SELF or relative.endswith(".lock"):
            continue
        path = ROOT / relative
        if path.suffix.casefold() not in TEXT_SUFFIXES:
            continue
        try:
            documents.append((relative, path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):
            continue
    return documents


def update_tracked_text() -> list[str]:
    changed: list[str] = []
    for relative, original in readable_tracked_text():
        path = ROOT / relative
        updated = "".join(update_line(line) for line in original.splitlines(keepends=True))
        if updated == original:
            continue
        path.write_text(updated, encoding="utf-8", newline="")
        changed.append(relative)
    return changed


def verify_expected_inputs() -> None:
    requirements = (ROOT / "requirements-dev.in").read_text(encoding="utf-8")
    runtime = (ROOT / "skills/mcp-server-architect/locks/python-runtime.in").read_text(encoding="utf-8")
    for expected in PACKAGE_UPDATES.values():
        if expected.startswith("ruff") or expected.startswith("types-"):
            assert expected in requirements, expected
    assert "mcp==2.0.0" in requirements
    assert "mcp==2.0.0" in runtime

    references: dict[str, list[tuple[str, int, str]]] = {action: [] for action in ACTION_UPDATES}
    for relative, text in readable_tracked_text():
        for line_number, line in enumerate(text.splitlines(), start=1):
            for match in ACTION_REFERENCE.finditer(line):
                action = match.group("action")
                references[action].append((relative, line_number, match.group("revision")))

    for action, (_, expected_sha, _) in ACTION_UPDATES.items():
        observed = references[action]
        assert observed, f"No pinned references found for {action}"
        offenders = [item for item in observed if item[2] != expected_sha]
        assert not offenders, f"Unexpected {action} revisions: {offenders}"


def main() -> int:
    restore_production_ci()
    changed = update_tracked_text()
    verify_expected_inputs()
    print("Updated dependency policy files:")
    for relative in changed:
        print(relative)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
