from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_core_standards_validate_without_errors() -> None:
    validator = load_module("afds_validator_test", ROOT / "skills/afds-doc-writer/docs_validate.py")
    config = validator.load_config(ROOT / "skills/afds-doc-writer/afds_config.yaml")
    paths = [
        ROOT / "skills/afds-doc-writer/docs_standards.md",
        ROOT / "skills/mcp-server-architect/mcp-server-standards.md",
        ROOT / "skills/mcp-server-consumer/mcp-consumer-standards.md",
        ROOT / "skills/ci-cd-architect/ci-cd-standard.md",
        ROOT / "skills/pre-commit-architect/precommit-standard.md",
        ROOT / "benchmarks/afds/benchmark-report.md",
    ]
    findings = [finding for path in paths for finding in validator.validate_document(path, config)]
    assert not [finding for finding in findings if finding.severity == "ERROR"]


def test_benchmark_quality_gate() -> None:
    benchmark = load_module("afds_benchmark_test", ROOT / "benchmarks/afds/benchmark.py")
    result = benchmark.run()
    assert benchmark.check_thresholds(result) == []
    assert result["mutation"]["detection_rate"] == 1.0
