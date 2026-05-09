"""Tests for skills/afds-doc-writer/docs_standards.md (ref.documentation-standard)."""


class TestStandardFrontmatter:
    """Frontmatter field validation for the documentation standard."""

    def test_has_all_required_fields(self, standard_fm):
        required = ["description", "doc_id", "type", "status", "ttl_days"]
        for field in required:
            assert field in standard_fm, f"Missing required field: {field}"

    def test_doc_id_is_correct(self, standard_fm):
        assert standard_fm["doc_id"] == "ref.documentation-standard"

    def test_type_is_ref(self, standard_fm):
        assert standard_fm["type"] == "ref"

    def test_status_is_active(self, standard_fm):
        assert standard_fm["status"] == "active"

    def test_stability_is_frozen(self, standard_fm):
        assert standard_fm["stability"] == "frozen"

    def test_ai_scope_is_review_only(self, standard_fm):
        assert standard_fm["ai_scope"] == "review_only"

    def test_source_of_truth_is_true(self, standard_fm):
        assert standard_fm["source_of_truth"] is True

    def test_description_no_trailing_period(self, standard_fm):
        desc = standard_fm.get("description", "")
        assert not desc.rstrip().endswith("."), "Description must not end with period"

    def test_tll_days_is_positive(self, standard_fm):
        ttl = standard_fm.get("ttl_days", 0)
        assert isinstance(ttl, (int, float)) and ttl >= 0

    def test_upstream_is_empty(self, standard_fm):
        assert standard_fm.get("upstream") == []

    def test_no_unknown_fields(self, standard_fm, config):
        allowed = set(config["allowed_fields"])
        for field in standard_fm:
            assert field in allowed, f"Unknown field: {field}"

    def test_no_forbidden_fields(self, standard_fm, config):
        forbidden = set(config["forbidden_fields"])
        for field in standard_fm:
            assert field not in forbidden, f"Forbidden field present: {field}"


class TestStandardContent:
    """Content and structure validation for the documentation standard."""

    def test_has_h1(self, standard_body):
        import re
        h1s = [line for line in standard_body.splitlines() if re.match(r"^# ", line)]
        assert len(h1s) >= 1, "Missing H1 heading"

    def test_has_changelog_section(self, standard_body):
        import re
        sections = re.findall(r"^## (.+)$", standard_body, re.MULTILINE)
        upper = [s.upper() for s in sections]
        assert "CHANGELOG" in upper, "Missing CHANGELOG section"

    def test_no_inline_metadata(self, standard_body):
        import re
        patterns = [
            r"^\*\*Version:\*\*", r"^\*\*Last Updated:\*\*", r"^\*\*Date:\*\*",
            r"^Version: ", r"^Date: ",
        ]
        prose = re.sub(r"```[\s\S]*?```", "", standard_body)
        for pattern in patterns:
            assert not re.search(pattern, prose, re.MULTILINE), (
                f"Inline metadata found: {pattern}"
            )

    def test_h1_count_is_one(self, standard_body):
        import re
        prose = re.sub(r"```[\s\S]*?```", "", standard_body)
        h1s = re.findall(r"^# (.+)$", prose, re.MULTILINE)
        assert len(h1s) == 1, f"Expected exactly 1 H1, found {len(h1s)}"

    def test_english_only(self, standard_body):
        import re as _re
        allowed = set("\n\r—–→•✅❌≠≥≤├─│┬└┌┘┐♦▪•°±")
        non_ascii = [ch for ch in standard_body if ord(ch) > 127 and ch not in allowed]
        assert len(non_ascii) == 0, (
            f"Non-English characters found: {non_ascii[:10]!r}"
        )


class TestStandardValidation:
    """Full validator pass/fail tests for the standard."""

    def test_passes_validation(self, standard_result):
        assert standard_result.passed, (
            f"Standard must pass validation. Errors: {standard_result.errors}"
        )

    def test_no_errors(self, standard_result):
        assert len(standard_result.errors) == 0, (
            f"Standard has errors: {standard_result.errors}"
        )

    def test_no_warnings(self, standard_result):
        assert len(standard_result.warnings) == 0, (
            f"Standard has warnings: {standard_result.warnings}"
        )

    def test_fitness_score_is_not_computed(self, standard_result):
        assert standard_result.fitness_score == 0.0, (
            "Fitness score is CI-only telemetry. "
            "Validator does not compute it."
        )
