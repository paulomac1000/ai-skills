#!/usr/bin/env python3
"""Fail closed when a candidate branch carries an unauthorized commit identity.

This is a metadata hygiene gate, not an authorization boundary. A commit
identity is self-asserted metadata, so a determined actor can write any
identity it likes; what the gate detects is the ordinary accident: an agent
committing under a stale, foreign or unverified address while integrating a
candidate. The authoritative attribution is the provider's own record of the
commit, and the repository's protection rules and required reviews remain the
authorization boundary.

Only identities the repository trusts may appear in the commits a candidate
proposes for integration, whether that candidate is a pull request or a push
to the integration branch. The owner is identified by the verified address
published on the GitHub account, not by a display name, because a name can be
chosen by anyone.

Addresses are compared case-insensitively, so an address that differs only in
case is accepted. The platform address is trusted only as a committer, because
a merge or a squash records the platform as the committer while the original
author is preserved; it is never trusted as an author, because a web edit is
attributed to it.
"""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The repository owner's verified public address and the private form GitHub
# attributes when the owner commits with a hidden email.
OWNER_EMAILS = frozenset(
    {
        "pawel.maciejewski95@gmail.com",
        "9095484+paulomac1000@users.noreply.github.com",
    }
)

# Trusted automation accounts. Dependabot opens the dependency pull requests
# and GitHub Actions writes the automation commits. Neither may author a
# human-owned change, but both may author their own automation commits.
TRUSTED_BOT_EMAILS = frozenset(
    {
        "49699333+dependabot[bot]@users.noreply.github.com",
        "41898282+github-actions[bot]@users.noreply.github.com",
    }
)

# The platform signs merges and rebase operations, so it appears as the
# committer of a platform-written commit. It is never trusted as an author:
# a web edit is attributed to this address, and the gate must not mistake a
# web edit for a reviewed integration.
PLATFORM_COMMITTER_EMAILS = frozenset({"noreply@github.com"})

SEPARATOR = "\x1f"


class AuditError(RuntimeError):
    """The audit could not be completed, so its result is not trustworthy."""


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


def _require_ancestor(base: str, head: str, root: Path = ROOT) -> None:
    """Fail closed when the base is not an ancestor of the head.

    A stale or foreign base would otherwise turn the range into an unrelated
    set of commits, and the audit would report on history that is not proposed
    for integration.
    """
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base, head],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode == 1:
        raise AuditError(f"base {base} is not an ancestor of {head}")
    if completed.returncode != 0:
        raise AuditError(f"base {base} cannot be resolved as an ancestor of {head} (git exit {completed.returncode})")


def _commits(base: str, head: str, root: Path = ROOT) -> list[tuple[str, str, str, str]]:
    """Return (sha, author name, author email, committer email) for the range.

    A line that cannot be parsed is a failure, not a line to skip: a skipped
    line would hide an identity from the audit.
    """
    output = _git(
        "log",
        "--no-merges",
        f"--format=%H{SEPARATOR}%an{SEPARATOR}%ae{SEPARATOR}%ce",
        f"{base}..{head}",
        root=root,
    )
    return _parse_commits(output, base, head)


def _merge_commits(base: str, head: str, root: Path = ROOT) -> list[tuple[str, str]]:
    """Return (sha, subject) for every merge commit in the range.

    The integration policy is squash-only linear history, so a merge commit in
    a pushed main range is a policy violation rather than an auditable skip:
    the identity listing excludes merge commits, which would otherwise let a
    merge topology carry an unaudited identity onto the integration branch.
    """
    output = _git(
        "log",
        "--merges",
        f"--format=%H{SEPARATOR}%s",
        f"{base}..{head}",
        root=root,
    )
    records: list[tuple[str, str]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        sha, separator, subject = line.partition(SEPARATOR)
        if not separator:
            raise AuditError(f"merge commit record in {base}..{head} cannot be parsed")
        records.append((sha, subject))
    return records


def _parse_commits(output: str, base: str = "", head: str = "") -> list[tuple[str, str, str, str]]:
    """Parse the commit records, refusing a record that cannot be read.

    A record that cannot be parsed is a failure, not a record to skip: a
    skipped record would hide an identity from the audit.
    """
    commits: list[tuple[str, str, str, str]] = []
    for number, line in enumerate(output.splitlines(), start=1):
        if not line.strip():
            continue
        parts = line.split(SEPARATOR)
        if len(parts) != 4:
            raise AuditError(f"commit record {number} in {base}..{head} cannot be parsed")
        commits.append((parts[0], parts[1], parts[2], parts[3]))
    return commits


def unauthorized_identities(
    commits: Sequence[tuple[str, str, str, str]],
    *,
    owner_emails: frozenset[str] = OWNER_EMAILS,
    bot_emails: frozenset[str] = TRUSTED_BOT_EMAILS,
    platform_committer_emails: frozenset[str] = PLATFORM_COMMITTER_EMAILS,
) -> list[str]:
    """Return a finding for every commit whose identity is not trusted.

    The author of an integrated commit must be the owner or a trusted
    automation account. The committer may additionally be the platform, because
    a rebase or a squash records the platform as the committer while the
    original author is preserved.
    """
    allowed_authors = {value.casefold() for value in owner_emails | bot_emails}
    allowed_committers = allowed_authors | {value.casefold() for value in platform_committer_emails}
    findings: list[str] = []
    for sha, author, author_email, committer_email in commits:
        if author_email.casefold() not in allowed_authors:
            findings.append(f"UNAUTHORIZED_AUTHOR_IDENTITY: {sha} authored by {author} <{author_email}>")
        if committer_email.casefold() not in allowed_committers:
            findings.append(f"UNAUTHORIZED_COMMITTER_IDENTITY: {sha} committed by {committer_email}")
    return findings


def main(argv: Sequence[str] | None = None, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="The base ref the candidate is compared against.")
    parser.add_argument("--head", default="HEAD", help="The candidate ref to check.")
    parser.add_argument(
        "--forbid-merge-commits",
        action="store_true",
        help=(
            "Fail when the range contains merge commits. Use this on the push path, "
            "where the audited range is the integration branch's own history and the "
            "policy is squash-only linear history."
        ),
    )
    args = parser.parse_args(argv)

    try:
        _require_ancestor(args.base, args.head, root)
        if args.forbid_merge_commits:
            merges = _merge_commits(args.base, args.head, root)
            if merges:
                for sha, subject in merges:
                    print(f"ERROR: MERGE_COMMIT_IN_RANGE: {sha} {subject}")
                return 1
        commits = _commits(args.base, args.head, root)
    except (AuditError, OSError, subprocess.SubprocessError) as error:
        print(f"ERROR: AUTHORSHIP_AUDIT_INCOMPLETE: {error}")
        return 1

    if not commits:
        # An empty range means the audit examined nothing, so it cannot pass.
        print(f"ERROR: AUTHORSHIP_AUDIT_EMPTY: no commits in {args.base}..{args.head}")
        return 1

    findings = unauthorized_identities(commits)
    for finding in findings:
        print(f"ERROR: {finding}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
