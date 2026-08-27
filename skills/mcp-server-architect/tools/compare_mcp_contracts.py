#!/usr/bin/env python3
"""Compare two observed MCP public contracts and enforce the required SemVer bump."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_contract_module = importlib.import_module("contracts.mcp_public_contract")
load_contract = _contract_module.load_contract
render_comparison = _contract_module.render_comparison


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true", help="exit non-zero when candidate SemVer is insufficient")
    args = parser.parse_args(argv)

    try:
        baseline = load_contract(args.baseline)
        candidate = load_contract(args.candidate)
    except ValueError as exc:
        parser.error(str(exc))
    report = render_comparison(baseline, candidate)
    serialized = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(serialized, end="")
    else:
        if os.path.lexists(args.output):
            parser.error("output already exists; refusing to overwrite")
        args.output.write_text(serialized, encoding="utf-8", newline="\n")
    return 1 if args.check and not report["version_satisfies"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
