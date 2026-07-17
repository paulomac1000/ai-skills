"""Static safety checks for bundled workflow templates."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "skills/ci-cd-architect/templates"
ACTION = re.compile(r"uses:\s*([^\s@]+)@([^\s#]+)")
FULL_SHA = re.compile(r"[0-9a-f]{40}")


def template_files() -> list[Path]:
    """Return all supported workflow templates."""
    return sorted(TEMPLATES.glob("*.yml.template"))


def test_expected_templates_are_present() -> None:
    assert {path.name for path in template_files()} == {
        "ci.yml.template",
        "docs-validation.yml.template",
        "dotnet-ci.yml.template",
        "publish.yml.template",
    }


def test_third_party_actions_are_pinned_to_full_commits() -> None:
    for path in template_files():
        text = path.read_text(encoding="utf-8")
        matches = ACTION.findall(text)
        assert matches, path
        for _, revision in matches:
            assert FULL_SHA.fullmatch(revision), (path, revision)


def test_checkout_never_persists_credentials() -> None:
    for path in template_files():
        text = path.read_text(encoding="utf-8")
        if "actions/checkout@" in text:
            assert "persist-credentials: false" in text


def test_templates_define_permissions_and_timeouts() -> None:
    for path in template_files():
        text = path.read_text(encoding="utf-8")
        assert "permissions:" in text
        assert "timeout-minutes:" in text


def test_templates_render_to_valid_yaml() -> None:
    """Replace neutral placeholders and parse each rendered workflow."""
    import yaml

    values = {
        "<TIMEOUT_MINUTES>": "15",
        "<PYTHON_VERSION>": "3.12",
        "<INSTALL_COMMAND>": "python -m pip install -r requirements.txt",
        "<TEST_COMMAND>": "python -m pytest",
        "<DOTNET_VERSION>": "10.0.x",
        "<SOLUTION_PATH>": "src/App.sln",
        "<VALIDATOR_PATH>": "scripts/validate.py",
        "<VALIDATION_COMMAND>": "python scripts/validate.py",
    }
    for path in template_files():
        rendered = path.read_text(encoding="utf-8")
        for token, value in values.items():
            rendered = rendered.replace(token, value)
        assert not re.search(r"<[A-Z_]+>", rendered)
        assert isinstance(yaml.safe_load(rendered), dict)
