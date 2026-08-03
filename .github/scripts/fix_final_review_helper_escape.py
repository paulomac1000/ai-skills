from __future__ import annotations

import sys
from pathlib import Path


def replace_once(text: str, old: str, new: str, description: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one {description}, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: fix_final_review_helper_escape.py SOURCE TARGET")
    source = Path(sys.argv[1])
    target = Path(sys.argv[2])
    text = source.read_text(encoding="utf-8")
    text = replace_once(
        text,
        r'        if character == "\\":' + "\n",
        r'        if character == "\\\\":' + "\n",
        "nested backslash literal",
    )
    text = replace_once(
        text,
        '    codex_text = replace_once(codex_text, "import stat\\n", "import os\\nimport stat\\n", codex_tests)\n',
        "",
        "unused os import injection",
    )
    target.write_text(text, encoding="utf-8", newline="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
