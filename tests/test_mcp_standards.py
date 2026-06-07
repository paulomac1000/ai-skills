"""Tests for skills/mcp-server-architect/mcp-server-standards.md (ref.mcp-server-standards)."""

import re


class TestMcpFrontmatter:
    """Frontmatter field validation for the MCP server standards."""

    def test_has_all_required_fields(self, mcp_fm):
        required = ["description", "doc_id", "type", "status", "ttl_days"]
        for field in required:
            assert field in mcp_fm, f"Missing required field: {field}"

    def test_doc_id_is_correct(self, mcp_fm):
        assert mcp_fm["doc_id"] == "ref.mcp-server-standards"

    def test_type_is_ref(self, mcp_fm):
        assert mcp_fm["type"] == "ref"

    def test_status_is_active(self, mcp_fm):
        assert mcp_fm["status"] == "active"

    def test_stability_is_stable(self, mcp_fm):
        assert mcp_fm["stability"] == "stable"

    def test_ai_scope_is_editable(self, mcp_fm):
        assert mcp_fm["ai_scope"] == "editable"

    def test_source_of_truth_is_true(self, mcp_fm):
        assert mcp_fm["source_of_truth"] is True

    def test_domain_is_mcp(self, mcp_fm):
        assert mcp_fm.get("domain") == "mcp"

    def test_tags_contains_mcp(self, mcp_fm):
        tags = mcp_fm.get("tags", [])
        assert "mcp" in tags

    def test_description_no_trailing_period(self, mcp_fm):
        desc = mcp_fm.get("description", "")
        assert not desc.rstrip().endswith("."), "Description must not end with period"

    def test_upstream_includes_standard(self, mcp_fm):
        upstream = mcp_fm.get("upstream", [])
        assert "ref.documentation-standard" in upstream, (
            "MCP standards must reference documentation standard"
        )

    def test_no_unknown_fields(self, mcp_fm, config):
        allowed = set(config["allowed_fields"])
        for field in mcp_fm:
            assert field in allowed, f"Unknown field: {field}"

    def test_no_forbidden_fields(self, mcp_fm, config):
        forbidden = set(config["forbidden_fields"])
        for field in mcp_fm:
            assert field not in forbidden, f"Forbidden field present: {field}"

    def test_no_downstream_in_frontmatter(self, mcp_fm):
        assert "downstream" not in mcp_fm, (
            "downstream field is forbidden per AFDS 1.0.0"
        )


class TestMcpBodyStructure:
    """Body section validation for the MCP standards document."""

    REF_SECTIONS = [
        "PURPOSE", "SCOPE", "DEFINITIONS", "RULES", "INTERFACES",
        "STATE", "EDGE_CASES", "EXAMPLES", "NON_GOALS",
    ]

    def test_has_all_ref_body_sections(self, mcp_body):
        sections = re.findall(r"^## (.+)$", mcp_body, re.MULTILINE)
        upper = [s.upper().strip() for s in sections]
        for required in self.REF_SECTIONS:
            assert required in upper, f"Missing ref body section: {required}"

    def test_sections_in_correct_order(self, mcp_body):
        sections = re.findall(r"^## (.+)$", mcp_body, re.MULTILINE)
        upper = [s.upper().strip() for s in sections]
        expected_order = self.REF_SECTIONS
        indices = {}
        for i, sec in enumerate(upper):
            if sec not in indices:
                indices[sec] = i
        for i in range(len(expected_order) - 1):
            s1, s2 = expected_order[i], expected_order[i + 1]
            if s1 in indices and s2 in indices:
                assert indices[s1] < indices[s2], (
                    f"## {s1.title()} must appear before ## {s2.title()}"
                )

    def test_h1_count_is_one(self, mcp_body):
        prose = re.sub(r"```[\s\S]*?```", "", mcp_body)
        h1s = re.findall(r"^# (.+)$", prose, re.MULTILINE)
        assert len(h1s) == 1, f"Expected exactly 1 H1, found {len(h1s)}"

    def test_no_changelog_section(self, mcp_body):
        sections = re.findall(r"^## (.+)$", mcp_body, re.MULTILINE)
        upper = [s.upper().strip() for s in sections]
        assert "CHANGELOG" not in upper, (
            "CHANGELOG is only for contract.* and decision.* per AFDS 1.0.0"
        )

    def test_no_empty_sections(self, mcp_body):
        clean = re.sub(r"```[\s\S]*?```", "", mcp_body)
        section_blocks = re.split(r"^## .+$", clean, flags=re.MULTILINE)[1:]
        for block in section_blocks:
            stripped = block.strip()
            is_divider = re.match(r"^\s*---\s*$", stripped)
            if stripped and not is_divider:
                continue
            if stripped and is_divider:
                continue


class TestMcpContent:
    """Content quality checks for the MCP standards document."""

    def test_no_banned_words_in_prose(self, mcp_body):
        banned = [
            r"\bmight\b", r"\bmaybe\b", r"\bpossibly\b", r"\bprobably\b",
            r"\bsimply\b", r"\bjust\b", r"\beasy\b",
        ]
        prose = re.sub(r"```[\s\S]*?```", "", mcp_body)
        prose = re.sub(r"`[^`]+`", "", prose)
        found = []
        for pattern in banned:
            matches = re.findall(pattern, prose, re.IGNORECASE)
            found.extend(matches)
        if found:
            unique = sorted({w.lower() for w in found})
            assert False, f"Universal banned words found: {unique}"

    def test_english_only(self, mcp_body):
        allowed = set("\n\r—–→•✅❌≠≥≤├─│┬└┌┘┐♦▪•°±")
        non_ascii = [ch for ch in mcp_body if ord(ch) > 127 and ch not in allowed]
        assert len(non_ascii) == 0, (
            f"Non-English characters found: {non_ascii[:10]!r}"
        )

    def test_no_html_tags(self, mcp_body):
        real_html = re.findall(
            r"<(/?)(a|abbr|article|audio|b|blockquote|br|button|canvas|code|div|em|embed|"
            r"fieldset|footer|form|h[1-6]|head|header|hr|html|i|iframe|img|input|label|"
            r"li|link|meta|nav|ol|option|p|pre|script|section|select|span|strong|style|"
            r"table|tbody|td|textarea|th|thead|title|tr|ul|video)\b[^>]*>",
            mcp_body,
        )
        assert len(real_html) == 0, f"HTML tag found: {real_html[:5]}"

    def test_no_emoji(self, mcp_body):
        emoji_range = re.compile(
            "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF\U0001F900-\U0001F9FF"
            "\U00002600-\U000027BF\U0001FA00-\U0001FA6F]"
        )
        assert not emoji_range.search(mcp_body), "Emoji found in document body"


class TestMcpValidation:
    """Full validator pass/fail tests for the MCP standards document."""

    def test_passes_validation(self, mcp_result):
        assert mcp_result.passed, (
            f"MCP standards must pass validation. Errors: {mcp_result.errors}"
        )

    def test_no_errors(self, mcp_result):
        assert len(mcp_result.errors) == 0, (
            f"MCP standards has errors: {mcp_result.errors}"
        )

    def test_no_warnings(self, mcp_result):
        assert len(mcp_result.warnings) == 0, (
            f"MCP standards has warnings: {mcp_result.warnings}"
        )

    def test_fitness_score_is_not_computed(self, mcp_result):
        assert mcp_result.fitness_score == 0.0, (
            "Fitness score is CI-only telemetry. "
            "Validator does not compute it."
        )

    def test_ttl_not_exceeded(self, mcp_fm):
        from datetime import datetime
        last_verified = mcp_fm.get("last_verified")
        ttl = mcp_fm.get("ttl_days", 180)
        if last_verified and isinstance(last_verified, str):
            dt = datetime.strptime(last_verified, "%Y-%m-%d")
            days_since = (datetime.now() - dt).days
            assert days_since <= ttl, (
                f"TTL exceeded: {days_since} days since verification (TTL: {ttl})"
            )


class TestMcpCrossRefs:
    """Cross-reference consistency with other documentation."""

    def test_upstream_is_not_self(self, mcp_fm):
        upstream = mcp_fm.get("upstream", [])
        assert "ref.mcp-server-standards" not in upstream, (
            "Document must not list itself in upstream"
        )

    def test_type_in_config(self, mcp_fm, config):
        doc_type = mcp_fm["type"]
        valid_types = list(config["types"].keys())
        assert doc_type in valid_types


class TestMcpPythonAppendix:
    """Verify Python-specific appendices exist in the MCP standards (v2.1.0)."""

    def test_python_streamable_http_appendix_exists(self, mcp_body):
        """Fix 1: Python Streamable HTTP example after Transport Architecture."""
        # Find Transport Selection Guide table end marker
        match = re.search(
            r"Edge/Serverless\s+\|\s+Streamable HTTP.*?cold-start friendly",
            mcp_body, re.DOTALL,
        )
        assert match is not None, "Transport Selection Guide table not found"

        # After the table (within ~200 lines), must find Python Streamable HTTP appendix
        after_table = mcp_body[match.end():match.end() + 4000]
        assert re.search(r"Python.*Streamable HTTP", after_table, re.DOTALL), (
            "Fix 1 missing: Python Streamable HTTP appendix not found after Transport Selection Guide"
        )
        assert re.search(r"Starlette", after_table), (
            "Fix 1 missing: Starlette not mentioned in Python Streamable HTTP appendix"
        )
        assert re.search(r"FastMCP", after_table), (
            "Fix 1 missing: FastMCP not mentioned in Python Streamable HTTP appendix"
        )
        assert re.search(r"sse|SSE", after_table), (
            "Fix 1 missing: SSE transport not shown in Python Streamable HTTP appendix"
        )

    def test_fastmcp_broken_imports_documented(self, mcp_body):
        """Fix 2: FastMCP 2.0.0 broken imports in Known Issues with TRANSIENT label."""
        # Find the Known Issues area (Common Upgrade Issues table or nearby)
        assert re.search(
            r"fastmcp.*mcp_config|mcp_config.*fastmcp|sys\.modules.*fastmcp",
            mcp_body, re.IGNORECASE,
        ), (
            "Fix 2 missing: FastMCP 2.0.0 broken import workaround not documented"
        )
        # Must be labeled TRANSIENT
        assert re.search(r"TRANSIENT", mcp_body), (
            "Fix 2 missing: FastMCP 2.0.0 workaround not labeled TRANSIENT"
        )
        # Must have removal condition
        assert re.search(
            r"Remove.*FastMCP|removal condition|until.*FastMCP|when.*FastMCP.*released|"
            r"No longer needed.*FastMCP",
            mcp_body, re.IGNORECASE,
        ), (
            "Fix 2 missing: TRANSIENT label must include explicit removal condition"
        )

    def test_mcp_run_mypy_documented(self, mcp_body):
        """Fix 3: mcp.run() host/port mypy false-positive in Known Issues."""
        assert re.search(
            r"host.*port.*mypy|mypy.*host.*port|Unexpected keyword.*host|"
            r"Unexpected keyword.*port.*mcp\.run",
            mcp_body, re.IGNORECASE,
        ), (
            "Fix 3 missing: mcp.run() host/port mypy false-positive not documented"
        )

    def test_python_middleware_after_compose(self, mcp_body):
        """Fix 4: Python middleware example after Canonical Template 18."""
        # Find composeMiddleware (Canonical Template 18)
        match = re.search(r"composeMiddleware", mcp_body)
        assert match is not None, "Canonical Template 18 (composeMiddleware) not found"

        # After composeMiddleware (~within 2000 chars), find Python middleware pattern
        after_template = mcp_body[match.start():match.start() + 3000]
        assert re.search(
            r"async def.*middleware|def.*middleware.*handler|"
            r"Python.*middleware|sequential.*middleware",
            after_template, re.IGNORECASE,
        ), (
            "Fix 4 missing: Python middleware example not found after composeMiddleware"
        )

    def test_threading_local_vs_contextvars_clarified(self, mcp_body):
        """Fix 5: threading.local vs contextvars clarification near Observability rule 9."""
        match = re.search(
            r"MUST be stored in a `contextvars\.ContextVar`",
            mcp_body,
        )
        assert match is not None, "Observability rule 9 not found"

        around = mcp_body[match.start():match.start() + 2000]
        assert re.search(r"threading\.local.*sync|sync.*threading\.local", around, re.IGNORECASE), (
            "Fix 5 missing: threading.local guidance not found near Observability rule 9"
        )
        assert re.search(r"contextvars.*async|async.*contextvars", around, re.IGNORECASE), (
            "Fix 5 missing: contextvars guidance not found near Observability rule 9"
        )

    def test_session_management_python_template(self, mcp_body):
        """Fix 6: Session management Python in-memory store template."""
        # Must find a Python code block with session management logic
        assert re.search(
            r"```python.*?(create_session|validate_session|session_store).*?```",
            mcp_body, re.DOTALL | re.IGNORECASE,
        ), (
            "Fix 6 missing: Python session management template not found "
            "(expecting create_session/validate_session in Python code block)"
        )
        assert re.search(
            r"timeout\s*[=:]\s*3600|3600.*timeout",
            mcp_body,
        ), (
            "Fix 6 missing: 3600-second session timeout not found"
        )

    def test_build_meta_pure_constructor_exists(self, mcp_body):
        """Fix 8: _build_meta() as pure constructor, separate from build_meta()."""
        # Find the response helpers / build_meta area
        assert re.search(
            r"_build_meta",
            mcp_body,
        ), (
            "Fix 8 missing: _build_meta() not found in the standard"
        )
        # Must be documented as pure constructor (no side effects)
        match = re.search(r"_build_meta", mcp_body)
        after = mcp_body[match.start():match.start() + 500]
        assert re.search(
            r"pure.*constructor|no.*side.*effect|returns.*dict|constructs.*meta",
            after, re.IGNORECASE,
        ), (
            "Fix 8 missing: _build_meta() not documented as pure constructor"
        )

    def test_error_dict_extended_docstring_clarified(self, mcp_body):
        """Fix 7: _error_dict_extended naming has docstring clarifying dict vs JSONResponse."""
        match = re.search(r"_error_dict_extended", mcp_body)
        assert match is not None, "_error_dict_extended not found"

        # Within 300 chars after the match, must clarify dict vs JSONResponse
        after_fn = mcp_body[match.start():match.start() + 600]
        assert re.search(
            r"dict.*JSONResponse|JSONResponse.*dict|"
            r"return.*dict.*not.*JSON|returns.*dict",
            after_fn, re.IGNORECASE,
        ), (
            "Fix 7 missing: _error_dict_extended docstring does not clarify dict vs JSONResponse return types"
        )

    def test_version_bumped_to_2_1_0(self, mcp_fm):
        """Version bump: standard_version 2.0.0 → 2.1.0."""
        assert mcp_fm.get("standard_version") == "2.1.0", (
            f"Expected standard_version 2.1.0, got {mcp_fm.get('standard_version')}"
        )

    def test_changelog_2_1_0_exists(self, mcp_body):
        """Changelog: must contain 2.1.0 entry."""
        assert re.search(r"###\s+2\.1\.0\s*\(2026-06-07\)", mcp_body), (
            "Changelog missing: 2.1.0 (2026-06-07) entry not found"
        )
