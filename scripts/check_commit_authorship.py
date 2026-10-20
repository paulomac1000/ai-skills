#!/usr/bin/env python3
"""Fail closed when a candidate branch carries an unauthorized commit identity.

Only identities that GitHub can attribute to the repository owner or to a
trusted automation account may appear in the commits a pull request proposes
for integration. The owner is identified by the verified address published on
the GitHub account, not by a display name.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The repository owner's verified public address. A display name proves
# nothing, because a name can be chosen by anyone.
OWNER_EMAILS = frozenset({"pawel.maciejewski95@gmail.com"})

# Trusted automation accounts. Dependabot opens the dependency pull requests and
# GitHub Actions writes the automation commits.
TRUSTED_BOT_EMAILS = frozenset(
    {
        "49699333+dependabot[bot]@users.noreply.github.com",
        "41898282+github-actions[bot]@users.noreply.github.com",
    }
)

# The platform signs merges and rebase operations, so a merge or a rebase
# carries the platform identity as its committer.
PLATFORM_EMAILS = frozenset({"noreply@github.com"})


def _git(*args: str, root: Path = ROOT) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return completed.stdout


def _commits(base: str, head: str, root: Path = ROOT) -> list[tuple[str, str, str, str]]:
    """Return (sha, author name, author email, committer email) for the range."""
    output = _git(
        "log",
        "--no-merges",
        "--format=%H%x1f%an%x1f%ae%x1f%ce",
        f"{base}..{head}",
        root=root,
    )
    commits: list[tuple[str, str, str, str]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x1f")
        if len(parts) != 4:
            continue
        commits.append((parts[0], parts[1], parts[2], parts[3]))
    return commits


def unauthorized_identities(
    commits: Sequence[tuple[str, str, str, str]],
    *,
    owner_emails: frozenset[str] = OWNER_EMAILS,
    bot_emails: frozenset[str] = TRUSTED_BOT_EMAILS,
    platform_emails: frozenset[str] = PLATFORM_EMAILS,
) -> list[str]:
    """Return a finding for every commit whose identity is not trusted."""
    allowed = owner_emails | bot_emails | platform_emails
    findings: list[str] = []
    for sha, author, author_email, committer_email in commits:
        if author_email.casefold() not in {value.casefold() for value in allowed}:
            findings.append(f"UNAUTHORIZED_AUTHOR_IDENTITY: {sha} authored by {author} <{author_email}>")
        if committer_email.casefold() not in {value.casefold() for value in allowed}:
            findings.append(f"UNAUTHORIZED_COMMITTER_IDENTITY: {sha} committed by {committer_email}")
    return findings


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="The base ref the candidate is compared against.")
    parser.add_argument("--head", default="HEAD", help="The candidate ref to check.")
    args = parser.parse_args(argv)

    commits = _commits(args.base, args.head)
    findings = unauthorized_identities(commits)
    for finding in findings:
        print(f"ERROR: {finding}")
    if not commits:
        print(f"AUTHORSHIP_AUDIT_EMPTY: no commits in {args.base}..{args.head}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
