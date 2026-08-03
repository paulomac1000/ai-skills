from pathlib import Path

path = Path(__file__).with_name("apply_final_review_fixes.py")
text = path.read_text(encoding="utf-8")
old = r'        if character == "\\":' + "\n"
new = r'        if character == "\\\\":' + "\n"
if text.count(old) != 1:
    raise RuntimeError(f"expected one nested backslash literal, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="")
