"""Tests for templates/docs-template.md (ref.docs-template)."""

import re

import pytest


class TestTemplateFrontmatter:
    """Frontmatter field validation for the document template."""

    def test_has_all_required_fields(self, template_fm):
        required = ["description", "doc_id", "type", "status", "ttl_days"]
        for field in required:
            assert field in template_fm, f"Missing required field: {field}"

    def test_doc_id_is_correct(self, template_fm):
        assert template_fm["doc_id"] == "ref.docs-template"

    def test_type_is_ref(self, template_fm):
        assert template_fm["type"] == "ref"

    def test_status_is_active(self, template_fm):
        assert template_fm["status"] == "active"

    def test_stability_is_frozen(self, template_fm):
        assert template_fm["stability"] == "frozen"

    def test_ai_scope_is_editable(self, template_fm):
        assert template_fm["ai_scope"] == "editable"

    def test_source_of_truth_is_true(self, template_fm):
        assert template_fm["source_of_truth"] is True

    def test_description_no_trailing_period(self, template_fm):
        desc = template_fm.get("description", "")
        assert not desc.rstrip().endswith("."), "Description must not end with period"

    def test_upstream_includes_standard(self, template_fm):
        upstream = template_fm.get("upstream", [])
        assert "ref.documentation-standard" in upstream, (
            "Template must reference the standard in upstream"
        )

    def test_no_unknown_fields(self, template_fm, config):
        allowed = set(config["allowed_fields"])
        for field in template_fm:
            assert field in allowed, f"Unknown field: {field}"

    def test_no_forbidden_fields(self, template_fm, config):
        forbidden = set(config["forbidden_fields"])
        for field in template_fm:
            assert field not in forbidden, f"Forbidden field present: {field}"


class TestTemplateBodyStructure:
    """Body section validation for the document template."""

    REF_SECTIONS = [
        "PURPOSE", "SCOPE", "DEFINITIONS", "RULES", "INTERFACES",
        "STATE", "EDGE_CASES", "EXAMPLES", "NON_GOALS",
    ]

    def test_has_all_ref_body_sections(self, template_body):
        sections = re.findall(r"^## (.+)$", template_body, re.MULTILINE)
        upper = [s.upper().strip() for s in sections]
        for required in self.REF_SECTIONS:
            assert required in upper, f"Missing ref body section: {required}"

    def test_sections_in_correct_order(self, template_body):
        sections = re.findall(r"^## (.+)$", template_body, re.MULTILINE)
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

    def test_h1_count_is_one(self, template_body):
        h1s = re.findall(r"^# (.+)$", template_body, re.MULTILINE)
        assert len(h1s) == 1, f"Expected exactly 1 H1, found {len(h1s)}"

    def test_has_syntax_tip_callout(self, template_body):
        assert "> [!TIP]" in template_body, "Missing syntax reminders callout"
        assert "ref.documentation-standard" in template_body, (
            "Syntax callout must link to the standard"
        )

    def test_has_frontmatter_quick_reference(self, template_body):
        sections = re.findall(r"^## (.+)$", template_body, re.MULTILINE)
        upper = [s.upper().strip() for s in sections]
        assert "FRONTMATTER QUICK REFERENCE" in upper, (
            "Missing Frontmatter Quick Reference section"
        )

    def test_has_frontmatter_template_section(self, template_body):
        sections = re.findall(r"^## (.+)$", template_body, re.MULTILINE)
        upper = [s.upper().strip() for s in sections]
        assert "FRONTMATTER TEMPLATE" in upper, (
            "Missing Frontmatter Template section"
        )

    def test_has_workflow_template(self, template_body):
        assert "### Workflow (`workflow.*`)" in template_body, (
            "Missing workflow frontmatter template"
        )

    def test_has_ref_template(self, template_body):
        assert "### Reference (`ref.*`)" in template_body, (
            "Missing ref frontmatter template"
        )

    def test_has_system_template(self, template_body):
        assert "### System (`sys.*`)" in template_body, (
            "Missing system frontmatter template"
        )


class TestTemplateContent:
    """Content quality checks for the template."""

    def test_no_banned_words_in_prose(self, template_body):
        import re as _re
        banned = [
            r"\bmight\b", r"\bmaybe\b", r"\bpossibly\b", r"\bprobably\b",
            r"\bsimply\b", r"\bjust\b", r"\beasy\b",
        ]
        prose = _re.sub(r"```[\s\S]*?```", "", template_body)
        prose = _re.sub(r"`[^`]+`", "", prose)
        found = []
        for pattern in banned:
            matches = _re.findall(pattern, prose, _re.IGNORECASE)
            found.extend(matches)
        if found:
            unique = sorted({w.lower() for w in found})
            pytest.fail(f"Banned words found: {unique}")

    def test_english_only(self, template_body):
        non_ascii = [ch for ch in template_body if ord(ch) > 127 and ch not in "\n\r—–→•"]
        assert len(non_ascii) == 0, (
            f"Non-English characters found: {non_ascii[:10]!r}"
        )

    def test_no_html_tags(self, template_body):
        real_html = re.findall(
            r"<(/?)(a|abbr|article|audio|b|blockquote|br|button|canvas|code|div|em|embed|"
            r"fieldset|footer|form|h[1-6]|head|header|hr|html|i|iframe|img|input|label|"
            r"li|link|meta|nav|ol|option|p|pre|script|section|select|span|strong|style|"
            r"table|tbody|td|textarea|th|thead|title|tr|ul|video)\b[^>]*>",
            template_body,
        )
        assert len(real_html) == 0, f"HTML tag found: {real_html[:5]}"

    def test_no_emoji(self, template_body):
        import re as _re
        emoji_range = _re.compile(
            "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF\U0001F900-\U0001F9FF"
            "\U00002600-\U000027BF\U0001FA00-\U0001FA6F]"
        )
        assert not emoji_range.search(template_body), "Emoji found in template body"


class TestTemplateValidation:
    """Full validator pass/fail tests for the template."""

    def test_passes_validation(self, template_result):
        assert template_result.passed, (
            f"Template must pass validation. Errors: {template_result.errors}"
        )

    def test_no_errors(self, template_result):
        assert len(template_result.errors) == 0, (
            f"Template has errors: {template_result.errors}"
        )

    def test_no_warnings(self, template_result):
        assert len(template_result.warnings) == 0, (
            f"Template has warnings: {template_result.warnings}"
        )

    def test_fitness_score_is_not_computed(self, template_result):
        assert template_result.fitness_score == 0.0, (
            "Fitness score is CI-only telemetry. "
            "Validator does not compute it."
        )
