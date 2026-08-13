#!/usr/bin/env python3
"""Build a deterministic subprocess environment for local quality gates."""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping

BASE_ALLOWED = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "USERNAME",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "SHELL",
        "TMP",
        "TEMP",
        "TMPDIR",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "LANG",
        "VIRTUAL_ENV",
        "CONDA_PREFIX",
        "DOTNET_ROOT",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "ALL_PROXY",
        "PIP_INDEX_URL",
        "PIP_EXTRA_INDEX_URL",
        "PIP_CERT",
        "PIP_TRUSTED_HOST",
        "PYTHONUTF8",
        "PYTHONIOENCODING",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONHASHSEED",
    }
)
_CONTROL_VARIABLE = "AI_SKILLS_CI_PASSTHROUGH"


def build_clean_environment(
    source: Mapping[str, str] | None = None,
    *,
    extra_allowed: Iterable[str] = (),
) -> dict[str, str]:
    """Return infrastructure variables only, plus explicitly named passthroughs."""
    original = os.environ if source is None else source
    allowed = BASE_ALLOWED | frozenset(name for name in extra_allowed if name and name != _CONTROL_VARIABLE)
    result = {name: value for name, value in original.items() if name in allowed or name.startswith("LC_")}
    result.setdefault("PYTHONUTF8", "1")
    return result


def configured_passthrough(source: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Read explicit local-gate passthrough names without passing the control variable itself."""
    original = os.environ if source is None else source
    raw = original.get(_CONTROL_VARIABLE, "")
    return tuple(sorted({part.strip() for part in raw.split(",") if part.strip() and part.strip() != _CONTROL_VARIABLE}))
