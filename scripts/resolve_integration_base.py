#!/usr/bin/env python3
"""Resolve and validate the integration base of a CI event.

A pull request proposes the range between the recorded base of the pull
request and its head. A push to main proposes the range between the branch
state the provider recorded before the push and the pushed head. A base that
is missing, malformed, or the zero SHA of a branch creation cannot be audited,
so the gate must fail closed instead of silently auditing nothing.
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Sequence

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
ZERO_SHA = re.compile(r"^0{40}$")


def resolve_base(base: str) -> str:
    """Return the validated base, or raise ValueError with a typed reason."""
    if not isinstance(base, str) or FULL_SHA.fullmatch(base) is None:
        raise ValueError(
            f"INTEGRATION_BASE_INVALID: integration base {base!r} is missing or not a full lowercase commit SHA"
        )
    if ZERO_SHA.fullmatch(base) is not None:
        raise ValueError("INTEGRATION_BASE_ZERO: the zero SHA of a branch creation has no auditable prior revision")
    return base


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="The event-recorded base SHA to validate.")
    args = parser.parse_args(argv)
    try:
        base = resolve_base(args.base)
    except ValueError as error:
        print(f"ERROR: {error}")
        return 1
    print(base)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
