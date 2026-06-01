"""Shared fixtures for documentation validation tests."""

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CONSUMER_DIR = REPO_ROOT / "skills" / "mcp-server-consumer"
DOCS_VALIDATE_PATH = REPO_ROOT / "skills" / "afds-doc-writer" / "docs_validate.py"

sys.path.insert(0, str(CONSUMER_DIR))

spec = importlib.util.spec_from_file_location("docs_validate", DOCS_VALIDATE_PATH)
if spec is None or spec.loader is None:
    raise ImportError(f"Failed to load {DOCS_VALIDATE_PATH}")
docs_validate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = docs_validate
spec.loader.exec_module(docs_validate)

_make_check_registry = docs_validate._make_check_registry
load_config = docs_validate.load_config
load_markdown_file = docs_validate.load_markdown_file
validate_file = docs_validate.validate_file


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


@pytest.fixture(scope="session")
def consumer_path(repo_root):
    return repo_root / "skills" / "mcp-server-consumer" / "mcp-consumer-standards.md"


@pytest.fixture(scope="session")
def consumer_fm_body(consumer_path):
    fm, body = load_markdown_file(consumer_path)
    if fm is None:
        raise ValueError(f"Failed to parse {consumer_path}: {body}")
    return fm, body


@pytest.fixture(scope="session")
def consumer_fm(consumer_fm_body):
    return consumer_fm_body[0]


@pytest.fixture(scope="session")
def consumer_body(consumer_fm_body):
    return consumer_fm_body[1]


@pytest.fixture(scope="session")
def consumer_result(consumer_path, config, check_registry):
    return validate_file(consumer_path, config, check_registry)
