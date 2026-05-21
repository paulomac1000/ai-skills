"""Shared fixtures for documentation validation tests."""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "skills" / "afds-doc-writer"
sys.path.insert(0, str(SCRIPTS_DIR))

from docs_validate import (
    _extract_all_section_names,
    _make_check_registry,
    calculate_fitness_score,
    check_balanced_fences,
    check_mandatory_sections,
    load_config,
    load_markdown_file,
    validate_file,
)
from docs_validate import ValidationResult
from copy import deepcopy


@pytest.fixture(scope="session")
def repo_root():
    return REPO_ROOT


@pytest.fixture(scope="session")
def config(repo_root):
    config_path = repo_root / "skills" / "afds-doc-writer" / "afds_config.yaml"
    return load_config(config_path if config_path.exists() else None)


@pytest.fixture(scope="session")
def check_registry(config):
    return _make_check_registry(config)


@pytest.fixture(scope="session")
def standard_path(repo_root):
    return repo_root / "skills" / "afds-doc-writer" / "docs_standards.md"


@pytest.fixture(scope="session")
def standard_fm_body(standard_path):
    fm, body = load_markdown_file(standard_path)
    if fm is None:
        raise ValueError(f"Failed to parse {standard_path}: {body}")
    return fm, body


@pytest.fixture(scope="session")
def standard_fm(standard_fm_body):
    return standard_fm_body[0]


@pytest.fixture(scope="session")
def standard_body(standard_fm_body):
    return standard_fm_body[1]


@pytest.fixture(scope="session")
def template_path(repo_root):
    return repo_root / "skills" / "afds-doc-writer" / "docs-template.md"


@pytest.fixture(scope="session")
def template_fm_body(template_path):
    fm, body = load_markdown_file(template_path)
    if fm is None:
        raise ValueError(f"Failed to parse {template_path}: {body}")
    return fm, body


@pytest.fixture(scope="session")
def template_fm(template_fm_body):
    return template_fm_body[0]


@pytest.fixture(scope="session")
def template_body(template_fm_body):
    return template_fm_body[1]


@pytest.fixture(scope="session")
def standard_result(standard_path, config, check_registry):
    return validate_file(standard_path, config, check_registry)


@pytest.fixture(scope="session")
def template_result(template_path, config, check_registry):
    return validate_file(template_path, config, check_registry)


@pytest.fixture(scope="session")
def mcp_path(repo_root):
    return repo_root / "skills" / "mcp-server-architect" / "mcp-server-standards.md"


@pytest.fixture(scope="session")
def mcp_fm_body(mcp_path):
    fm, body = load_markdown_file(mcp_path)
    if fm is None:
        raise ValueError(f"Failed to parse {mcp_path}: {body}")
    return fm, body


@pytest.fixture(scope="session")
def mcp_fm(mcp_fm_body):
    return mcp_fm_body[0]


@pytest.fixture(scope="session")
def mcp_body(mcp_fm_body):
    return mcp_fm_body[1]


@pytest.fixture(scope="session")
def mcp_result(mcp_path, config, check_registry):
    return validate_file(mcp_path, config, check_registry)
