from __future__ import annotations

import ast
import os
from pathlib import Path

ROOT = Path.cwd()


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def replace_between(text: str, start: str, end: str, replacement: str, label: str) -> str:
    start_index = text.find(start)
    if start_index < 0:
        raise RuntimeError(f"{label}: start marker missing")
    end_index = text.find(end, start_index)
    if end_index < 0:
        raise RuntimeError(f"{label}: end marker missing")
    return text[:start_index] + replacement + text[end_index:]


def stage(path: str, text: str, staged: dict[str, str]) -> None:
    if path.endswith(".py"):
        ast.parse(text, filename=path)
    staged[path] = text


staged: dict[str, str] = {}

audit_path = "skills/agents-md-architect/tools/audit_agents_md.py"
audit = read(audit_path)
yaml_code = r'''YAML_MAPPING = re.compile(
    r"^(?P<indent> *)(?P<list>-\s*)?(?P<key>[A-Za-z_][A-Za-z0-9_-]*):(?:\s*(?P<value>.*))?$"
)
YAML_BLOCK_STYLES = {"|", ">", "|-", "|+", ">-", ">+"}


def _yaml_indent(line: str) -> int | None:
    prefix = line[: len(line) - len(line.lstrip(" \t"))]
    return None if "\t" in prefix else len(prefix)


def _strip_yaml_comment(value: str) -> str:
    quote: str | None = None
    escaped = False
    for index, character in enumerate(value):
        if escaped:
            escaped = False
            continue
        if character == "\\" and quote == '"':
            escaped = True
            continue
        if character in "'\"":
            if quote is None:
                quote = character
            elif quote == character:
                quote = None
            continue
        if character == "#" and quote is None and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    return value.rstrip()


def _unquote_scalar(value: str) -> str:
    stripped = _strip_yaml_comment(value).strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in "'\"":
        return stripped[1:-1]
    return stripped


def _fold_yaml_lines(lines: list[str]) -> str:
    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        if line:
            current.append(line.strip())
            continue
        if current:
            paragraphs.append(" ".join(current))
            current = []
        paragraphs.append("")
    if current:
        paragraphs.append(" ".join(current))
    return "\n".join(paragraphs).strip()


def _read_yaml_scalar(
    lines: list[str],
    index: int,
    parent_indent: int,
    raw_value: str,
) -> tuple[str, str | None, int]:
    value = _strip_yaml_comment(raw_value).strip()
    if value not in YAML_BLOCK_STYLES:
        return _unquote_scalar(value), None, index + 1

    body: list[str] = []
    cursor = index + 1
    while cursor < len(lines):
        candidate = lines[cursor]
        candidate_indent = _yaml_indent(candidate)
        if candidate.strip() and (candidate_indent is None or candidate_indent <= parent_indent):
            break
        body.append(candidate)
        cursor += 1

    nonblank_indents = [
        indent
        for line in body
        if line.strip() and (indent := _yaml_indent(line)) is not None
    ]
    content_indent = min(nonblank_indents, default=parent_indent + 1)
    content = [line[content_indent:].rstrip() if line.strip() else "" for line in body]
    style = value[0]
    if style == "|":
        return "\n".join(content).strip("\n"), style, cursor
    return _fold_yaml_lines(content), style, cursor


def _yaml_scalar_nodes(text: str) -> list[tuple[tuple[str, ...], str, str | None]]:
    lines = text.splitlines()
    stack: list[tuple[int, str]] = []
    nodes: list[tuple[tuple[str, ...], str, str | None]] = []
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        indent = _yaml_indent(raw_line)
        if indent is None or not stripped or stripped.startswith("#"):
            index += 1
            continue

        while stack and stack[-1][0] >= indent:
            stack.pop()
        match = YAML_MAPPING.fullmatch(raw_line)
        if match is None:
            if stripped.startswith("- "):
                stack.append((indent, "[]"))
                value = _unquote_scalar(stripped[2:])
                if value:
                    nodes.append((tuple(item[1] for item in stack), value, None))
            index += 1
            continue

        is_list_item = match.group("list") is not None
        if is_list_item:
            stack.append((indent, "[]"))
        key = match.group("key")
        raw_value = match.group("value") or ""
        path = tuple(item[1] for item in stack) + (key,)
        cleaned = _strip_yaml_comment(raw_value).strip()
        if not cleaned:
            stack.append((indent + (1 if is_list_item else 0), key))
            index += 1
            continue

        value, style, next_index = _read_yaml_scalar(lines, index, indent, raw_value)
        if value:
            nodes.append((path, value, style))
        index = next_index
    return nodes


def _yaml_node_is_executable(relative: str, path: tuple[str, ...]) -> bool:
    name = Path(relative).name.casefold()
    if relative.startswith(".github/workflows/"):
        return len(path) == 5 and path[0] == "jobs" and path[2:] == ("steps", "[]", "run")
    if relative == ".circleci/config.yml":
        return (
            len(path) == 5
            and path[0] == "jobs"
            and path[2:] == ("steps", "[]", "run")
        ) or (
            len(path) == 6
            and path[0] == "jobs"
            and path[2:] == ("steps", "[]", "run", "command")
        )
    if name in {"azure-pipelines.yml", "azure-pipelines.yaml"}:
        return len(path) >= 3 and path[-3] == "steps" and path[-2] == "[]" and path[-1] in {
            "script",
            "bash",
            "pwsh",
            "powershell",
        }
    if name in {"taskfile.yml", "taskfile.yaml"}:
        return (
            len(path) == 4
            and path[0] == "tasks"
            and path[2:] == ("cmds", "[]")
        ) or (
            len(path) == 5
            and path[0] == "tasks"
            and path[2:] == ("cmds", "[]", "cmd")
        )
    if relative == ".gitlab-ci.yml":
        executable_keys = {"script", "before_script", "after_script"}
        return (len(path) >= 2 and path[-2] in executable_keys and path[-1] == "[]") or path[-1] in executable_keys
    return False


def _extract_yaml_invocations(relative: str, text: str) -> set[str]:
    invocations: set[str] = set()
    for path, value, style in _yaml_scalar_nodes(text):
        if not _yaml_node_is_executable(relative, path):
            continue
        if style == "|":
            invocations.update(_extract_shell_invocations(value))
        else:
            _add_command_segments(invocations, value)
    return invocations


'''
audit = replace_between(audit, "YAML_COMMAND = re.compile(", "def _literal_python_command", yaml_code, "yaml parser")
audit = replace_once(
    audit,
    '        return _extract_yaml_invocations(text)\n',
    '        return _extract_yaml_invocations(relative, text)\n',
    "yaml dispatcher",
)
stage(audit_path, audit, staged)

parser_path = "skills/agents-md-architect/tools/agents_md_parse.py"
parser_text = read(parser_path)
reader_code = r'''def read_utf8_bounded(path: Path, max_bytes: int = MAX_INSTRUCTION_FILE_BYTES) -> ReadResult:
    """Read at most max_bytes plus one from a stable regular-file identity."""
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    expected_identity: os.stat_result | None = None
    if nofollow:
        flags |= nofollow
    else:
        try:
            expected_identity = os.lstat(path)
            if stat.S_ISLNK(expected_identity.st_mode):
                return ReadResult(None, 0, "input.read-error", "Refusing to read a symlink.")
        except OSError as error:
            return ReadResult(None, 0, "input.read-error", f"Could not inspect input file: {error}")

    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        return ReadResult(None, 0, "input.read-error", f"Could not open input file: {error}")

    try:
        metadata = os.fstat(descriptor)
        if expected_identity is not None and not os.path.samestat(expected_identity, metadata):
            return ReadResult(
                None,
                0,
                "input.read-error",
                "Input file identity changed while opening; refusing to follow a replacement.",
            )
        if not stat.S_ISREG(metadata.st_mode):
            return ReadResult(None, 0, "input.read-error", "Input is not a regular file.")
        if metadata.st_size > max_bytes:
            return ReadResult(
                None,
                metadata.st_size,
                "input.too-large",
                (f"Input file is {metadata.st_size} bytes; maximum supported size is {max_bytes} bytes."),
            )
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            payload = stream.read(max_bytes + 1)
    except OSError as error:
        return ReadResult(None, 0, "input.read-error", f"Could not read input file: {error}")
    finally:
        if descriptor >= 0:
            os.close(descriptor)

    if len(payload) > max_bytes:
        return ReadResult(
            None,
            len(payload),
            "input.too-large",
            f"Input file exceeds the maximum supported size of {max_bytes} bytes.",
        )
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        return ReadResult(
            None,
            len(payload),
            "input.invalid-utf8",
            f"Input file is not valid UTF-8 at byte {error.start}.",
        )
    return ReadResult(text, len(payload), None, None)


'''
parser_text = replace_between(parser_text, "def read_utf8_bounded", "def _iter_code_spans", reader_code, "bounded reader")
stage(parser_path, parser_text, staged)

discovery_path = "skills/agents-md-architect/tools/discover_repository.py"
discovery_text = read(discovery_path)
probe_code = r'''@dataclass
class _DiscoveryBudget:
    limit: int
    seen: int = 0
    exhausted: bool = False

    def consume(self) -> bool:
        self.seen += 1
        if self.seen > self.limit:
            self.exhausted = True
            return False
        return True


def _is_dotnet_project_directory(directory: Path, budget: _DiscoveryBudget) -> bool | None:
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if not budget.consume():
                    return None
                if entry.is_symlink():
                    continue
                if entry.is_file(follow_symlinks=False) and Path(entry.name).suffix.casefold() in DOTNET_PROJECT_SUFFIXES:
                    return True
    except OSError:
        return False
    return False


def _is_dotnet_bin_output(
    project_directory: Path,
    candidate: Path,
    budget: _DiscoveryBudget,
) -> bool | None:
    project = _is_dotnet_project_directory(project_directory, budget)
    if project is None or not project:
        return project
    script_suffixes = {"", ".py", ".rb", ".ps1", ".sh"}
    compiled_suffixes = {".dll", ".exe", ".json", ".pdb", ".so", ".dylib"}
    try:
        with os.scandir(candidate) as entries:
            for entry in entries:
                if not budget.consume():
                    return None
                if entry.is_symlink():
                    return False
                if entry.is_file(follow_symlinks=False):
                    suffix = Path(entry.name).suffix.casefold()
                    if suffix in script_suffixes or suffix not in compiled_suffixes:
                        return False
                elif not entry.is_dir(follow_symlinks=False):
                    return False
    except OSError:
        return False
    return True


def _is_ignored_directory(
    root: Path,
    current: Path,
    name: str,
    budget: _DiscoveryBudget,
) -> bool | None:
    if name in CACHE_DIRECTORIES or name in GENERIC_BUILD_DIRECTORIES:
        return True
    if name == "obj":
        return _is_dotnet_project_directory(current, budget)
    if name == "bin":
        return _is_dotnet_bin_output(current, current / name, budget)
    if name == "target":
        return (current / "Cargo.toml").is_file()
    return False


'''
discovery_text = replace_between(
    discovery_text,
    "def _is_dotnet_project_directory",
    "def _classify_ecosystems",
    probe_code,
    "discovery probes",
)
discovery_text = replace_once(
    discovery_text,
    "    entries_seen = 0\n    stop = False\n",
    "    budget = _DiscoveryBudget(MAX_DISCOVERY_ENTRIES)\n    stop = False\n",
    "discovery budget initialization",
)
discovery_text = replace_once(
    discovery_text,
    "                    entries_seen += 1\n                    if entries_seen > MAX_DISCOVERY_ENTRIES:\n",
    "                    if not budget.consume():\n",
    "main discovery budget",
)
discovery_text = replace_once(
    discovery_text,
    "                            if _is_ignored_directory(safe_root, current, entry.name):\n                                continue\n",
    "                            ignored = _is_ignored_directory(safe_root, current, entry.name, budget)\n"
    "                            if ignored is None:\n"
    "                                issues.add(f\"discovery entries exceed {MAX_DISCOVERY_ENTRIES}\")\n"
    "                                stop = True\n"
    "                                break\n"
    "                            if ignored:\n"
    "                                continue\n",
    "budgeted ignored directories",
)
stage(discovery_path, discovery_text, staged)

test_path = "tests/test_agents_md_codex_followup.py"
tests = read(test_path)
tests = replace_once(
    tests,
    '        lambda _descriptor: SimpleNamespace(st_mode=stat.S_IFREG, st_size=1),\n',
    '        lambda _descriptor: SimpleNamespace(st_mode=stat.S_IFREG, st_size=1, st_dev=1, st_ino=1),\n',
    "bounded reader test metadata",
)
tests = replace_once(
    tests,
    '    monkeypatch.setattr(parser.os, "open", lambda *_args, **_kwargs: 42)\n',
    '    monkeypatch.setattr(parser.os, "open", lambda *_args, **_kwargs: 42)\n'
    '    if not getattr(parser.os, "O_NOFOLLOW", 0):\n'
    '        monkeypatch.setattr(\n'
    '            parser.os,\n'
    '            "lstat",\n'
    '            lambda _path: SimpleNamespace(st_mode=stat.S_IFREG, st_size=1, st_dev=1, st_ino=1),\n'
    '        )\n',
    "bounded reader test lstat",
)
new_tests = r'''


def test_github_env_command_does_not_establish_gate_evidence(tmp_path: Path) -> None:
    write(
        tmp_path / ".github/workflows/ci.yml",
        """name: CI

env:
  command: python scripts/ghost.py

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo real gate
""",
    )
    write(
        tmp_path / "AGENTS.md",
        valid_application().replace("python scripts/ci.py", "python scripts/ghost.py"),
    )
    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "commands.unlocated-full-gate" in codes(findings)


def test_github_folded_run_reconstructs_executable_command(tmp_path: Path) -> None:
    write(
        tmp_path / ".github/workflows/ci.yml",
        """name: CI

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: >
          python -m
          pytest
""",
    )
    write(
        tmp_path / "AGENTS.md",
        valid_application().replace("python scripts/ci.py", "python -m pytest"),
    )
    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "commands.unlocated-full-gate" not in codes(findings)


def test_dotnet_probe_consumes_shared_discovery_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe_entries = 0
    scandir_calls = 0

    class FakeEntry:
        def __init__(self, name: str, *, directory: bool = False) -> None:
            self.name = name
            self.path = str(tmp_path / name)
            self.directory = directory

        def is_symlink(self) -> bool:
            return False

        def is_dir(self, *, follow_symlinks: bool) -> bool:
            assert follow_symlinks is False
            return self.directory

        def is_file(self, *, follow_symlinks: bool) -> bool:
            assert follow_symlinks is False
            return not self.directory

    class FakeScandir:
        def __init__(self, entries: list[FakeEntry], *, probe: bool = False) -> None:
            self.entries = iter(entries)
            self.probe = probe

        def __enter__(self) -> FakeScandir:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def __iter__(self) -> FakeScandir:
            return self

        def __next__(self) -> FakeEntry:
            nonlocal probe_entries
            if self.probe:
                probe_entries += 1
                if probe_entries > 3:
                    raise AssertionError(".NET probe consumed past the shared budget")
                return FakeEntry(f"sibling-{probe_entries}.txt")
            return next(self.entries)

    def fake_scandir(_path: object) -> FakeScandir:
        nonlocal scandir_calls
        scandir_calls += 1
        if scandir_calls == 1:
            return FakeScandir([FakeEntry("obj", directory=True)])
        return FakeScandir([], probe=True)

    monkeypatch.setattr(discovery, "MAX_DISCOVERY_ENTRIES", 2)
    monkeypatch.setattr(discovery.os, "scandir", fake_scandir)
    result = discovery.discover(tmp_path)
    assert probe_entries == 2
    assert any("discovery entries exceed" in issue for issue in result.issues)


def test_no_nofollow_fallback_rejects_changed_file_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = SimpleNamespace(st_mode=stat.S_IFREG, st_size=1, st_dev=1, st_ino=10)
    after = SimpleNamespace(st_mode=stat.S_IFREG, st_size=1, st_dev=1, st_ino=11)
    closed: list[int] = []

    monkeypatch.setattr(parser.os, "O_NOFOLLOW", 0, raising=False)
    monkeypatch.setattr(parser.os, "lstat", lambda _path: before)
    monkeypatch.setattr(parser.os, "open", lambda *_args, **_kwargs: 42)
    monkeypatch.setattr(parser.os, "fstat", lambda _descriptor: after)
    monkeypatch.setattr(parser.os, "close", closed.append)
    monkeypatch.setattr(
        parser.os,
        "fdopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("changed identity must not be read")),
    )

    result = parser.read_utf8_bounded(Path("ignored"), max_bytes=8)
    assert result.code == "input.read-error"
    assert "identity changed" in (result.message or "")
    assert closed == [42]
'''
if "test_github_env_command_does_not_establish_gate_evidence" in tests:
    raise RuntimeError("follow-up tests already present")
tests = tests.rstrip() + new_tests + "\n"
stage(test_path, tests, staged)

for path, text in staged.items():
    destination = ROOT / path
    temporary = destination.with_name(destination.name + ".review-fix")
    temporary.write_text(text, encoding="utf-8", newline="\n")

for path in staged:
    destination = ROOT / path
    temporary = destination.with_name(destination.name + ".review-fix")
    os.replace(temporary, destination)

print("Updated:")
for path in sorted(staged):
    print(path)
