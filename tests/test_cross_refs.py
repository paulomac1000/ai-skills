"""Cross-reference consistency tests between documentation files."""


class TestCrossReferences:
    """Verify upstream/downstream links are consistent."""

    def test_template_upstream_includes_standard(self, standard_fm, template_fm):
        template_up = template_fm.get("upstream", [])
        assert "ref.documentation-standard" in template_up, (
            "Template must list standard as upstream"
        )

    def test_standard_self_consistency(self, standard_fm):
        doc_id = standard_fm.get("doc_id")
        upstream = standard_fm.get("upstream", [])
        for ref in upstream:
            assert isinstance(ref, str), f"Upstream ref must be string: {ref!r}"
            assert ref != doc_id, f"Document must not list itself as upstream: {ref}"

    def test_template_self_consistency(self, template_fm):
        doc_id = template_fm.get("doc_id")
        upstream = template_fm.get("upstream", [])
        for ref in upstream:
            assert isinstance(ref, str), f"Upstream ref must be string: {ref!r}"
            assert ref != doc_id, f"Document must not list itself as upstream: {ref}"


class TestDocumentIdConsistency:
    """Verify doc_id conventions across both documents."""

    def test_standard_doc_id_follows_convention(self, standard_fm):
        doc_id = standard_fm["doc_id"]
        parts = doc_id.split(".")
        assert len(parts) == 2, f"doc_id must have exactly 2 parts: {doc_id}"
        assert parts[0] == "ref", f"First part must be type prefix: {doc_id}"
        assert parts[1] == "documentation-standard"

    def test_template_doc_id_follows_convention(self, template_fm):
        doc_id = template_fm["doc_id"]
        parts = doc_id.split(".")
        assert len(parts) == 2, f"doc_id must have exactly 2 parts: {doc_id}"
        assert parts[0] == "ref", f"First part must be type prefix: {doc_id}"
        assert parts[1] == "docs-template"


class TestTypeConsistency:
    """Verify document types used in frontmatter match the config."""

    def test_standard_type_in_config(self, standard_fm, config):
        doc_type = standard_fm["type"]
        valid_types = list(config["types"].keys())
        assert doc_type in valid_types, f"Type '{doc_type}' not in config: {valid_types}"

    def test_template_type_in_config(self, template_fm, config):
        doc_type = template_fm["type"]
        valid_types = list(config["types"].keys())
        assert doc_type in valid_types, f"Type '{doc_type}' not in config: {valid_types}"

    def test_status_values_in_config(self, standard_fm, template_fm, config):
        valid_statuses = config["statuses"]
        assert standard_fm["status"] in valid_statuses
        assert template_fm["status"] in valid_statuses

    def test_stability_values_in_config(self, standard_fm, template_fm, config):
        valid = config["stability_values"]
        assert standard_fm.get("stability", "stable") in valid
        assert template_fm.get("stability", "stable") in valid


class TestTemplateCoverage:
    """Verify the template covers all configured document types."""

    def test_template_has_matching_type_sections(self, template_body, config):
        for type_name in config["types"]:
            assert f"### {type_name.title()}" in template_body or \
                   type_name in template_body, (
                f"Template missing frontmatter example for type: {type_name}"
            )

    def test_template_example_types_are_ordered(self, template_body, config):
        base_order = list(config["types"].keys())
        positions = {}
        for t in base_order:
            idx = template_body.find(f"### {t.title()}")
            if idx >= 0:
                positions[t] = idx
        sorted_positions = sorted(positions.items(), key=lambda x: x[1])
        sorted_types = [t for t, _ in sorted_positions]
        expected = [t for t in base_order if t in sorted_types]
        assert sorted_types == expected, (
            f"Template type sections must follow config order. "
            f"Expected: {expected}, got: {sorted_types}"
        )
