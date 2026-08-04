"""Lossless command invocation parsing and display for evidence comparison."""

from __future__ import annotations

import shlex
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class CommandInvocation:
    """One command represented by exact argument boundaries and safe display text."""

    argv: tuple[str, ...]
    display: str


def invocation_from_argv(argv: Iterable[str]) -> CommandInvocation | None:
    """Build a canonical invocation without losing argument boundaries."""
    arguments = tuple(argv)
    if not arguments or any("\x00" in argument for argument in arguments):
        return None
    return CommandInvocation(arguments, shlex.join(arguments))


def parse_invocation(command: str) -> CommandInvocation | None:
    """Parse a POSIX-style command and retain its exact argv tuple."""
    try:
        arguments = tuple(shlex.split(command, posix=True))
    except ValueError:
        return None
    return invocation_from_argv(arguments)


def canonical_invocation(argv: Iterable[str]) -> str:
    """Render argv as a round-trippable command string."""
    invocation = invocation_from_argv(argv)
    if invocation is None:
        raise ValueError("Command invocation must contain non-NUL arguments.")
    return invocation.display
