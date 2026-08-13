#!/usr/bin/env python3
"""Disambiguate a synthetic test SHA before the disposable final repair."""
from pathlib import Path

path = Path("tests/test_real_usage_hardening.py")
text = path.read_text(encoding="utf-8")
start = text.index("def test_trusted_source_validator_rejects_duplicate_unknown_and_missing_authority")
end = text.index("\ndef test_trusted_source_validator_rejects_authority_digest_and_unsafe_paths", start)
section = text[start:end]
old = '"revision": "a" * 40'
if section.count(old) != 2:
    raise SystemExit("expected two duplicate-source synthetic revisions in the duplicate-source fixture")
section = section.replace(old, '"revision": "d" * 40')
path.write_text(text[:start] + section + text[end:], encoding="utf-8")
