"""Wave 2 regressions for typed content extraction and provenance."""

from __future__ import annotations

import fnmatch
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONSUMER = ROOT / "skills/mcp-server-consumer"
TOOL = CONSUMER / "tools/extraction.py"
MANIFEST = CONSUMER / "manifest.yaml"
QUALITY_TARGETS = ROOT / "scripts/quality_targets.py"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _covered(targets: tuple[str, ...], path: str) -> bool:
    return any(
        path == target
        or path.startswith(f"{target.rstrip('/')}/")
        or ("*" in target and fnmatch.fnmatch(path, target))
        for target in targets
    )


def test_chrome_first_4kb_html_is_unextracted_not_a_summary() -> None:
    extraction = _load("wave2_extraction_html", TOOL)
    chrome = (b"<nav>menu cookie consent navigation</nav>" * 140)[:4096]
    body = chrome + b"<article>The actual research finding appears later.</article>"
    result = extraction.extract_semantic_content(
        body[:4096],
        content_type="text/html; charset=utf-8",
        source_locator="https://example.invalid/article",
        transport_truncated=True,
    )

    assert result.state.value == "UNEXTRACTED"
    assert result.text is None
    assert result.provenance.transport_truncated is True
    assert len(result.provenance.content_sha256) == 64
    with pytest.raises(ValueError, match="not extracted"):
        extraction.require_extracted_text(result)


def test_binary_content_is_unsupported_format_not_coerced_text() -> None:
    extraction = _load("wave2_extraction_binary", TOOL)
    result = extraction.extract_semantic_content(
        b"\x00\xff\x10binary",
        content_type="application/octet-stream",
        source_locator="https://example.invalid/blob",
    )
    assert result.state.value == "UNSUPPORTED_FORMAT"
    assert result.text is None


def test_extracted_and_partial_states_preserve_extractor_and_truncation_provenance() -> None:
    extraction = _load("wave2_extraction_states", TOOL)
    extracted = extraction.extract_semantic_content(
        b"<html>ignored by adapter</html>",
        content_type="text/html",
        source_locator="https://example.invalid/article",
        extractor=lambda _body: "semantic article text",
        extractor_name="reader/2",
    )
    partial = extraction.extract_semantic_content(
        b"plain semantic text",
        content_type="text/plain",
        source_locator="https://example.invalid/plain",
        max_semantic_bytes=5,
    )

    assert extracted.state.value == "EXTRACTED"
    assert extracted.provenance.extractor == "reader/2"
    assert extraction.require_extracted_text(extracted) == "semantic article text"
    assert partial.state.value == "PARTIAL"
    assert partial.provenance.semantic_truncated is True


def test_extractor_failure_is_typed_unextracted() -> None:
    extraction = _load("wave2_extraction_failure", TOOL)

    def fail(_body: bytes) -> str:
        raise RuntimeError("parser failed")

    result = extraction.extract_semantic_content(
        b"<html></html>",
        content_type="text/html",
        source_locator="https://example.invalid/article",
        extractor=fail,
        extractor_name="reader/2",
    )
    assert result.state.value == "UNEXTRACTED"
    assert result.provenance.extractor == "reader/2"


def test_extraction_tool_is_required_and_in_all_quality_inventories() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    assert "tools/extraction.py" in manifest["required"]
    inventories = _load("wave2_quality_targets_extraction", QUALITY_TARGETS)
    path = "skills/mcp-server-consumer/tools/extraction.py"
    for targets in (
        inventories.QUALITY_PATHS,
        inventories.TYPE_PATHS,
        inventories.BANDIT_PATHS,
        inventories.POLICY_COVERAGE_PATHS,
    ):
        assert _covered(targets, path)
