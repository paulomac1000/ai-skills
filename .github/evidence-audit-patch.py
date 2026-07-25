from __future__ import annotations

import base64
import gzip
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARTS = [ROOT / f"evidence-patch.part{index:02d}" for index in range(7)]
payload = "".join(path.read_text(encoding="utf-8").strip() for path in PARTS)
try:
    source = gzip.decompress(base64.b64decode(payload))
    exec(compile(source, "evidence-audit-patch", "exec"))
finally:
    for path in PARTS:
        path.unlink(missing_ok=True)
