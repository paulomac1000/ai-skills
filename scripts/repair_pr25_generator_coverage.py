#!/usr/bin/env python3
"""Add generator boundary coverage required by the generator-specific gate; deleted before commit."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "tests/test_contract_boundary_coverage.py"
text = path.read_text(encoding="utf-8")
old = "import importlib\nimport json\nfrom pathlib import Path\n"
new = "import importlib\nimport importlib.util\nimport json\nimport sys\nfrom pathlib import Path\n"
if text.count(old) != 1:
    raise RuntimeError(f"generator coverage import anchor count: {text.count(old)}")
text = text.replace(old, new, 1)
text += r'''


def _python_generator_impl():
    name = "boundary_generate_python_server_impl"
    module_path = Path(__file__).resolve().parents[1] / "skills/mcp-server-architect/tools/generate_python_server_impl.py"
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_python_generator_input_path_and_file_guards(tmp_path: Path) -> None:
    impl = _python_generator_impl()
    impl._validate_inputs("sample_server", "Sample server")
    for package in ("A", "a", "a-b", "_bad"):
        with pytest.raises(ValueError, match="package name"):
            impl._validate_inputs(package, "server")
    for server in ("", "x" * 129, "bad\x01name"):
        with pytest.raises(ValueError, match="server name"):
            impl._validate_inputs("sample_server", server)

    assert impl._safe_relative_path("src/sample.py").as_posix() == "src/sample.py"
    for raw in ("", "src\\sample.py", "/absolute.py", "../escape.py", "src/../escape.py"):
        with pytest.raises(ValueError):
            impl._safe_relative_path(raw)

    regular = tmp_path / "regular.txt"
    regular.write_text("hello", encoding="utf-8")
    assert impl._read_regular_utf8(regular) == "hello"
    with pytest.raises(ValueError, match="exceeds"):
        impl._read_regular_utf8(regular, maximum=1)
    directory = tmp_path / "directory"
    directory.mkdir()
    with pytest.raises(ValueError, match="regular file"):
        impl._read_regular_utf8(directory)
    invalid = tmp_path / "invalid.txt"
    invalid.write_bytes(b"\xff")
    with pytest.raises(ValueError, match="UTF-8"):
        impl._read_regular_utf8(invalid)
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(regular)
    except OSError:
        return
    with pytest.raises(ValueError, match="symlink"):
        impl._read_regular_utf8(link)


def test_python_generator_project_validation_rejects_contract_and_artifact_drift() -> None:
    impl = _python_generator_impl()
    files = impl.project_files("sample_server", "Sample server")
    impl.validate_generated_project(files, "sample_server")

    missing = dict(files)
    missing.pop("README.md")
    with pytest.raises(ValueError, match="incomplete"):
        impl.validate_generated_project(missing, "sample_server")

    wrong_identity = dict(files)
    wrong_identity["pyproject.toml"] = files["pyproject.toml"].replace(
        'name = "sample-server"', 'name = "wrong-name"', 1
    )
    with pytest.raises(ValueError, match="package identity"):
        impl.validate_generated_project(wrong_identity, "sample_server")

    bad_python = dict(files)
    bad_python["src/sample_server/server.py"] = "def broken(:\n"
    with pytest.raises(SyntaxError):
        impl.validate_generated_project(bad_python, "sample_server")

    forbidden_ci = dict(files)
    forbidden_ci[".github/workflows/ci.yml"] += "\ncontents: write\n"
    with pytest.raises(ValueError, match="trusted-CI baseline"):
        impl.validate_generated_project(forbidden_ci, "sample_server")

    weak_ci = dict(files)
    weak_ci[".github/workflows/ci.yml"] = files[".github/workflows/ci.yml"].replace(
        "concurrency:", "parallel-policy:"
    )
    with pytest.raises(ValueError, match="lacks concurrency"):
        impl.validate_generated_project(weak_ci, "sample_server")

    unpinned = dict(files)
    unpinned["Dockerfile"] = files["Dockerfile"].replace("@sha256:", "# sha256:", 1)
    with pytest.raises(ValueError, match="pin its base"):
        impl.validate_generated_project(unpinned, "sample_server")

    source_rebuild = dict(files)
    source_rebuild["Dockerfile"] += "\nCOPY src /app/src\n"
    with pytest.raises(ValueError, match="must not rebuild"):
        impl.validate_generated_project(source_rebuild, "sample_server")


def test_python_generator_capability_validation_rejects_stale_invalid_duplicate_and_missing() -> None:
    impl = _python_generator_impl()
    files = impl.project_files("sample_server", "Sample server")
    prefix = "src/sample_server/capabilities/"
    manifests = sorted(path for path in files if path.startswith(prefix) and path.endswith(".json"))
    assert len(manifests) >= 2

    stale = dict(files)
    document = json.loads(stale[manifests[0]])
    document["active"] = True
    stale[manifests[0]] = json.dumps(document)
    with pytest.raises(ValueError, match="legacy field"):
        impl._validate_capabilities(stale, "sample_server")

    invalid = dict(files)
    document = json.loads(invalid[manifests[0]])
    document.pop("id")
    invalid[manifests[0]] = json.dumps(document)
    with pytest.raises(ValueError):
        impl._validate_capabilities(invalid, "sample_server")

    duplicate = dict(files)
    first = json.loads(duplicate[manifests[0]])
    second = json.loads(duplicate[manifests[1]])
    second["id"] = first["id"]
    duplicate[manifests[1]] = json.dumps(second)
    with pytest.raises(ValueError, match="duplicate generated capability id"):
        impl._validate_capabilities(duplicate, "sample_server")

    without_manifests = {path: value for path, value in files.items() if not path.startswith(prefix)}
    with pytest.raises(ValueError, match="no capability manifests"):
        impl._validate_capabilities(without_manifests, "sample_server")
'''
path.write_text(text, encoding="utf-8")
