#!/usr/bin/env python3
"""Apply the final Jenkins match typing correction exactly once."""

from pathlib import Path

path = Path("skills/agents-md-architect/tools/agents_md_shell_evidence_impl.py")
text = path.read_text(encoding="utf-8")
old = """    for line in \"\".join(masked).splitlines():
        match = single_line.fullmatch(line)
        if match is None:
            continue
        extractor = (
            _extract_powershell_invocations
            if match.group(\"step\") in {\"powershell\", \"pwsh\"}
            else _extract_shell_invocations
        )
        invocations.update(extractor(match.group(\"command\")))
"""
new = """    for line in \"\".join(masked).splitlines():
        single_match = single_line.fullmatch(line)
        if single_match is None:
            continue
        extractor = (
            _extract_powershell_invocations
            if single_match.group(\"step\") in {\"powershell\", \"pwsh\"}
            else _extract_shell_invocations
        )
        invocations.update(extractor(single_match.group(\"command\")))
"""
if text.count(old) != 1:
    raise SystemExit(f"expected one Jenkins single-line match block, found {text.count(old)}")
path.write_text(text.replace(old, new), encoding="utf-8")
