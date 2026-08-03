from pathlib import Path

path = Path("tests/test_agents_md_codex_followup.py")
text = path.read_text(encoding="utf-8")
old = '''    monkeypatch.setattr(parser.os, "open", lambda *_args, **_kwargs: 42)
    if not parser._supports_component_nofollow():
        monkeypatch.setattr(
'''
new = '''    component_safe = parser._supports_component_nofollow()
    monkeypatch.setattr(parser, "_supports_component_nofollow", lambda: component_safe)
    monkeypatch.setattr(parser.os, "open", lambda *_args, **_kwargs: 42)
    if not component_safe:
        monkeypatch.setattr(
'''
if text.count(old) != 1:
    raise RuntimeError(f"expected one capability test block, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")

# Trigger after workflow registration.
