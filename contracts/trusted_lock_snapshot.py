#!/usr/bin/env python3
"""Compatibility facade for validating an already-bound trusted-source lock snapshot."""

from __future__ import annotations

from validate_trusted_executable_sources import parse_document, validate_document

__all__ = ["parse_document", "validate_document"]
