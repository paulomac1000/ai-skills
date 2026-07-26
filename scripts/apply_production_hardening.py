from __future__ import annotations

import base64
import gzip
from pathlib import Path

payload = Path(__file__).with_name("apply_payload.b64")
source = gzip.decompress(base64.b64decode(payload.read_text(encoding="ascii")))
compiled = compile(source, "scripts/apply_production_hardening.py", "exec")
exec(compiled, {"__name__": "__main__", "__file__": str(Path(__file__))})
