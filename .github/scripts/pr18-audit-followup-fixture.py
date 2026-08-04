#!/usr/bin/env python3
"""Correct the legacy GitHub Actions test fixture after fail-closed runner validation."""

from pathlib import Path

path = Path("tests/test_agents_md_latest_review.py")
text = path.read_text(encoding="utf-8")
old = '''"""jobs:
  test:
    steps:
      - run: |
          echo ok # ; python scripts/ghost.py
"""'''
new = '''"""jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: |
          echo ok # ; python scripts/ghost.py
"""'''
if text.count(old) != 1:
    raise SystemExit(f"expected one legacy fixture, found {text.count(old)}")
path.write_text(text.replace(old, new), encoding="utf-8")
