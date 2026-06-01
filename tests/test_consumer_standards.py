"""Tests for skills/mcp-server-consumer/mcp-consumer-standards.md (ref.mcp-consumer-standards).

Level 1: Document validation (AFDS frontmatter, body structure, content quality).
Level 2: Cross-reference consistency with ref.mcp-server-standards.
"""

import re


class TestConsumerFrontmatter:
    """Frontmatter field validation for the MCP consumer standards."""

    def test_has_all_required_fields(self, consumer_fm):
        required = ["description", "doc_id", "type", "status", "ttl_days"]
        for field in required:
            assert field in consumer_fm, f"Missing required field: {field}"

    def test_doc_id_is_correct(self, consumer_fm):
        assert consumer_fm["doc_id"] == "ref.mcp-consumer-standards"

    def test_type_is_ref(self, consumer_fm):
        assert consumer_fm["type"] == "ref"

    def test_status_is_active(self, consumer_fm):
        assert consumer_fm["status"] == "active"

    def test_stability_is_stable(self, consumer_fm):
        assert consumer_fm["stability"] == "stable"

    def test_ai_scope_is_editable(self, consumer_fm):
        assert consumer_fm["ai_scope"] == "editable"

    def test_source_of_truth_is_true(self, consumer_fm):
        assert consumer_fm["source_of_truth"] is True

    def test_domain_is_mcp(self, consumer_fm):
        assert consumer_fm.get("domain") == "mcp"

    def test_tags_contains_mcp(self, consumer_fm):
        tags = consumer_fm.get("tags", [])
        assert "mcp" in tags

    def test_description_no_trailing_period(self, consumer_fm):
        desc = consumer_fm.get("description", "")
        assert not desc.rstrip().endswith("."), "Description must not end with period"

    def test_upstream_includes_server_standard(self, consumer_fm):
        upstream = consumer_fm.get("upstream", [])
        assert "ref.mcp-server-standards" in upstream, (
            "Consumer standards must reference server standards"
        )

    def test_no_unknown_fields(self, consumer_fm, config):
        allowed = set(config["allowed_fields"])
        for field in consumer_fm:
            assert field in allowed, f"Unknown field: {field}"

    def test_no_forbidden_fields(self, consumer_fm, config):
        forbidden = set(config["forbidden_fields"])
        for field in consumer_fm:
            assert field not in forbidden, f"Forbidden field present: {field}"

    def test_no_downstream_in_frontmatter(self, consumer_fm):
        assert "downstream" not in consumer_fm, (
            "downstream field is forbidden per AFDS 1.0.0"
        )


class TestConsumerBodyStructure:
    """Body section validation for the MCP consumer standards document."""

    REF_SECTIONS = [
        "PURPOSE",
        "SCOPE",
        "DEFINITIONS",
        "RULES",
        "INTERFACES",
        "STATE",
        "EDGE_CASES",
        "EXAMPLES",
        "NON_GOALS",
    ]

    def test_has_all_ref_body_sections(self, consumer_body):
        sections = re.findall(r"^## (.+)$", consumer_body, re.MULTILINE)
        upper = [s.upper().strip() for s in sections]
        for required in self.REF_SECTIONS:
            assert required in upper, f"Missing ref body section: {required}"

    def test_sections_in_correct_order(self, consumer_body):
        sections = re.findall(r"^## (.+)$", consumer_body, re.MULTILINE)
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

    def test_h1_count_is_one(self, consumer_body):
        prose = re.sub(r"```[\s\S]*?```", "", consumer_body)
        h1s = re.findall(r"^# (.+)$", prose, re.MULTILINE)
        assert len(h1s) == 1, f"Expected exactly 1 H1, found {len(h1s)}"

    def test_no_changelog_section(self, consumer_body):
        sections = re.findall(r"^## (.+)$", consumer_body, re.MULTILINE)
        upper = [s.upper().strip() for s in sections]
        assert "CHANGELOG" not in upper, (
            "CHANGELOG is only for contract.* and decision.* per AFDS 1.0.0"
        )

    def test_no_empty_sections(self, consumer_body):
        clean = re.sub(r"```[\s\S]*?```", "", consumer_body)
        section_blocks = re.split(r"^## .+$", clean, flags=re.MULTILINE)[1:]
        for block in section_blocks:
            stripped = block.strip()
            is_divider = re.match(r"^\s*---\s*$", stripped)
            if stripped and not is_divider:
                continue
            if stripped and is_divider:
                continue


class TestConsumerContent:
    """Content quality checks for the MCP consumer standards document."""

    def test_no_banned_words_in_prose(self, consumer_body):
        banned = [
            r"\bmight\b",
            r"\bmaybe\b",
            r"\bpossibly\b",
            r"\bprobably\b",
            r"\bsimply\b",
            r"\bjust\b",
            r"\beasy\b",
        ]
        prose = re.sub(r"```[\s\S]*?```", "", consumer_body)
        prose = re.sub(r"`[^`]+`", "", prose)
        found = []
        for pattern in banned:
            matches = re.findall(pattern, prose, re.IGNORECASE)
            found.extend(matches)
        if found:
            unique = sorted({w.lower() for w in found})
            assert False, f"Universal banned words found: {unique}"

    def test_english_only(self, consumer_body):
        allowed = set("\n\r—–→•✅❌≠≥≤├─│┬└┌┘┐♦▪•°±")
        non_ascii = [ch for ch in consumer_body if ord(ch) > 127 and ch not in allowed]
        assert len(non_ascii) == 0, f"Non-English characters found: {non_ascii[:10]!r}"

    def test_no_html_tags(self, consumer_body):
        real_html = re.findall(
            r"<(/?)(a|abbr|article|audio|b|blockquote|br|button|canvas|code|div|em|embed|"
            r"fieldset|footer|form|h[1-6]|head|header|hr|html|i|iframe|img|input|label|"
            r"li|link|meta|nav|ol|option|p|pre|script|section|select|span|strong|style|"
            r"table|tbody|td|textarea|th|thead|title|tr|ul|video)\b[^>]*>",
            consumer_body,
        )
        assert len(real_html) == 0, f"HTML tag found: {real_html[:5]}"

    def test_no_emoji(self, consumer_body):
        emoji_range = re.compile(
            "[\U0001f600-\U0001f64f\U0001f300-\U0001f5ff"
            "\U0001f680-\U0001f6ff\U0001f900-\U0001f9ff"
            "\U00002600-\U000027bf\U0001fa00-\U0001fa6f]"
        )
        assert not emoji_range.search(consumer_body), "Emoji found in document body"


class TestConsumerValidation:
    """Full validator pass/fail tests for the MCP consumer standards document."""

    def test_passes_validation(self, consumer_result):
        assert consumer_result.passed, (
            f"Consumer standards must pass validation. Errors: {consumer_result.errors}"
        )

    def test_no_errors(self, consumer_result):
        assert len(consumer_result.errors) == 0, (
            f"Consumer standards has errors: {consumer_result.errors}"
        )

    def test_no_warnings(self, consumer_result):
        assert len(consumer_result.warnings) == 0, (
            f"Consumer standards has warnings: {consumer_result.warnings}"
        )

    def test_fitness_score_is_not_computed(self, consumer_result):
        assert consumer_result.fitness_score == 0.0, (
            "Fitness score is CI-only telemetry. Validator does not compute it."
        )

    def test_ttl_not_exceeded(self, consumer_fm):
        from datetime import datetime

        last_verified = consumer_fm.get("last_verified")
        ttl = consumer_fm.get("ttl_days", 180)
        if last_verified and isinstance(last_verified, str):
            dt = datetime.strptime(last_verified, "%Y-%m-%d")
            days_since = (datetime.now() - dt).days
            assert days_since <= ttl, (
                f"TTL exceeded: {days_since} days since verification (TTL: {ttl})"
            )


class TestConsumerCrossRefs:
    """Cross-reference consistency between consumer and server standards."""

    def test_upstream_is_not_self(self, consumer_fm):
        upstream = consumer_fm.get("upstream", [])
        assert "ref.mcp-consumer-standards" not in upstream, (
            "Document must not list itself in upstream"
        )

    def test_type_in_config(self, consumer_fm, config):
        doc_type = consumer_fm["type"]
        valid_types = list(config["types"].keys())
        assert doc_type in valid_types

    def test_error_codes_match_server_standard(self, mcp_body, consumer_body):
        """Level 2: All 13 error codes from server standard are referenced in consumer standard."""
        server_codes = set(
            re.findall(
                r"`(TIMEOUT|DEVICE_OFFLINE|AUTH_FAILED|"
                r"INVALID_PARAM|UNSUPPORTED|DEPENDENCY_MISSING|INTERNAL_ERROR|"
                r"HTTP_ERROR|DEVICE_NOT_FOUND|VALIDATION_FAILED|RESOURCE_LOCKED|"
                r"RESOURCE_ALREADY_EXISTS|RESOURCE_NOT_FOUND)`",
                mcp_body,
            )
        )
        consumer_codes = set(
            re.findall(
                r"`(TIMEOUT|DEVICE_OFFLINE|AUTH_FAILED|"
                r"INVALID_PARAM|UNSUPPORTED|DEPENDENCY_MISSING|INTERNAL_ERROR|"
                r"HTTP_ERROR|DEVICE_NOT_FOUND|VALIDATION_FAILED|RESOURCE_LOCKED|"
                r"RESOURCE_ALREADY_EXISTS|RESOURCE_NOT_FOUND)`",
                consumer_body,
            )
        )
        missing = server_codes - consumer_codes
        assert len(missing) == 0, (
            f"Server error codes not covered in consumer standard: {missing}"
        )

    def test_manifest_fields_referenced(self, consumer_body):
        """Level 2: All 15 manifest fields from server standard are referenced."""
        required_fields = [
            "name",
            "version",
            "risk",
            "side_effects",
            "idempotent",
            "retryable",
            "concurrent_safe",
            "timeout_ms",
            "requires_confirmation",
            "determinism",
            "latency",
            "cost",
            "impact",
            "privacy",
            "reversible",
        ]
        for field in required_fields:
            pattern = re.escape(field)
            assert re.search(rf"\b{pattern}\b", consumer_body), (
                f"Manifest field '{field}' not referenced in consumer standard"
            )


class TestConsumerCanonicalTemplates:
    """Regression tests for stale consumer canonical templates."""

    @staticmethod
    def _template_block(consumer_body, heading):
        pattern = rf"#### {re.escape(heading)}[\s\S]*?(?=\n#### |\n## )"
        match = re.search(pattern, consumer_body)
        assert match is not None, f"Missing template: {heading}"
        return match.group(0)

    def test_c1_checks_requires_confirmation_before_write(self, consumer_body):
        block = self._template_block(
            consumer_body,
            "Canonical Template C1 — Risk-Based Decision Tree",
        )
        requires_idx = block.index("if requires_confirmation:")
        write_idx = block.index('if risk == "WRITE":')
        sensitive_idx = block.index('if risk == "SENSITIVE":')
        assert requires_idx < write_idx
        assert requires_idx < sensitive_idx
        assert 'return "defer"' in block

    def test_c4_uses_current_requires_confirm_variable(self, consumer_body):
        block = self._template_block(
            consumer_body,
            "Canonical Template C4 — Confirmation Gate",
        )
        assert "requires_confirm = manifest.get" in block
        assert "if requires_confirm:" in block
        assert "if requires_confirmation:" not in block

    def test_c4_dangerous_rejection_is_not_confirmation(self, consumer_body):
        block = self._template_block(
            consumer_body,
            "Canonical Template C4 — Confirmation Gate",
        )
        assert 'return False, "DANGEROUS tool rejected' in block

    def test_c6_documents_generic_dangerous_rejections(self, consumer_body):
        block = self._template_block(
            consumer_body,
            "Canonical Template C6 — Decision Policy Table (Complete)",
        )
        assert '("DANGEROUS",   False,  "general",            "reject")' in block
        assert '("DANGEROUS",   True,   "general",            "reject")' in block
        assert '("DANGEROUS",   False,  "any",                "reject")' in block
        assert '("DANGEROUS",   True,   "any",                "reject")' in block

    def test_negative_capability_documents_count_zero(self, consumer_body):
        assert "`0`" in consumer_body
        assert "`count: 0`" in consumer_body

    def test_pagination_documents_meta_and_data_envelope(self, consumer_body):
        assert "inside `_meta`" in consumer_body
        assert "object-shaped `data` envelope" in consumer_body
