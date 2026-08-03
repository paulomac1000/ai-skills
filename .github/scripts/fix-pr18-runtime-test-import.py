from pathlib import Path

path = Path("tests/test_agents_md_codex_followup.py")
text = path.read_text(encoding="utf-8")
old = "import pytest\n"
new = "import pytest\nimport yaml\n"
if text.count(old) != 1:
    raise RuntimeError(f"expected one pytest import, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
