"""Classify stable versus volatile runtime facts embedded in AGENTS.md instructions."""

from __future__ import annotations

import re
from enum import StrEnum

FINDING_CODE = "VOLATILE_RUNTIME_BINDING_REQUIRES_OWNER"


class RuntimeFactClass(StrEnum):
    STABLE_INVARIANT = "stable_invariant"
    COMPATIBILITY_CONTRACT = "compatibility_contract"
    LOGICAL_CAPABILITY_OWNER = "logical_capability_owner"
    VOLATILE_OBSERVATION = "volatile_observation"
    PRIVATE_BINDING = "private_binding"


_IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
_PORT = re.compile(r"(?i)(?:\bport\s*[=:]?\s*|https?://[^\s/:]+:|\b[a-z0-9.-]+:)(\d{2,5})\b")
_CURRENT_RUNTIME = re.compile(
    r"(?i)\bcurrent\b.{0,40}\b(?:mcp|runtime|host|server|endpoint|port)\b|"
    r"\b(?:mcp|runtime|host|server|endpoint)\b.{0,40}\bcurrent\b"
)
_VERSION_BINDING = re.compile(r"(?i)\b(?:mcp|server|runtime|gateway|host)\b.{0,32}\bv?\d+(?:\.\d+){1,3}\b")
_OWNER = re.compile(r"(?i)\b(?:logical\s+)?capability\s+owner\b")
_RUNTIME_IDENTITY = re.compile(r"(?i)\bruntimeidentity\b|\bruntime identity\b")
_COMPAT = re.compile(r"(?i)\bcompatibility contract\b|\bsupported versions?\b|\bversion range\b")
_STABLE = re.compile(r"(?i)\bstable invariant\b")
_VOLATILE_LABEL = re.compile(r"(?i)\bvolatile observation\b|\bobserved at\b|\bsnapshot at\b")
_JUSTIFIED_PRIVATE = re.compile(
    r"(?i)\b(?:example only|local development only|test fixture|discovered dynamically|"
    r"resolve(?:d)? at runtime|runtimeidentity|runtime identity|volatile observation)\b"
)


def _has_private_binding(text: str) -> bool:
    if _IPV4.search(text):
        return True
    match = _PORT.search(text)
    if match is None:
        return False
    try:
        port = int(match.group(1))
    except (TypeError, ValueError):
        return False
    return 1 <= port <= 65535


def classify_runtime_fact(text: str) -> RuntimeFactClass:
    """Classify one instruction line by the strongest runtime-fact category it carries."""
    if _OWNER.search(text) and _RUNTIME_IDENTITY.search(text):
        return RuntimeFactClass.LOGICAL_CAPABILITY_OWNER
    if _COMPAT.search(text):
        return RuntimeFactClass.COMPATIBILITY_CONTRACT
    if _VOLATILE_LABEL.search(text) or _CURRENT_RUNTIME.search(text) or _VERSION_BINDING.search(text):
        return RuntimeFactClass.VOLATILE_OBSERVATION
    if _has_private_binding(text):
        return RuntimeFactClass.PRIVATE_BINDING
    if _STABLE.search(text):
        return RuntimeFactClass.STABLE_INVARIANT
    return RuntimeFactClass.STABLE_INVARIANT


def volatile_binding_message(text: str) -> str | None:
    """Return a finding message when a timeless instruction embeds a live/private binding."""
    classification = classify_runtime_fact(text)
    if classification in {
        RuntimeFactClass.STABLE_INVARIANT,
        RuntimeFactClass.COMPATIBILITY_CONTRACT,
        RuntimeFactClass.LOGICAL_CAPABILITY_OWNER,
    }:
        return None
    if classification is RuntimeFactClass.VOLATILE_OBSERVATION and _VOLATILE_LABEL.search(text):
        return None
    if classification is RuntimeFactClass.PRIVATE_BINDING and _JUSTIFIED_PRIVATE.search(text):
        return None
    return (
        "Volatile runtime host/version/IP/port cannot be timeless AGENTS.md truth; prove a stable "
        "compatibility contract or name the logical capability owner and resolve the live target "
        "through RuntimeIdentity."
    )
