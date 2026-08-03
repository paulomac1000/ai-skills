from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def replace_once(text: str, old: str, new: str, path: Path) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected exactly one match in {path}: {old[:80]!r}; found {count}")
    return text.replace(old, new, 1)


def replace_between(text: str, start: str, end: str, replacement: str, path: Path) -> str:
    start_index = text.find(start)
    end_index = text.find(end, start_index + len(start))
    if start_index < 0 or end_index < 0:
        raise RuntimeError(f"could not find replacement boundaries in {path}")
    return text[:start_index] + replacement + text[end_index:]


def main() -> int:
    staged: dict[Path, str] = {}

    example = ROOT / "skills/mcp-server-architect/examples/python/server_composition.py.example"
    staged[example] = '''"""Minimal official-SDK v2 composition example; use the generator for a complete project."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from mcp.server.mcpserver import Context, MCPServer


@dataclass(frozen=True, slots=True)
class AppContext:
    service: "InventoryService"


class InventoryService:
    async def list_items(self) -> list[dict[str, str]]:
        return [{"item_id": "example", "name": "Example item"}]


@asynccontextmanager
async def lifespan(_server: MCPServer[AppContext]) -> AsyncIterator[AppContext]:
    yield AppContext(service=InventoryService())


mcp = MCPServer(
    "inventory-mcp",
    version="0.1.0",
    instructions="List items before using their stable item_id in follow-up tools.",
    lifespan=lifespan,
)


@mcp.tool()
async def list_items(ctx: Context[AppContext]) -> dict[str, object]:
    """List bounded inventory summaries in stable identifier order."""
    items = await ctx.request_context.lifespan_context.service.list_items()
    return {"success": True, "data": items}


if __name__ == "__main__":
    mcp.run()
'''

    generator = ROOT / "skills/mcp-server-architect/tools/generate_python_server_impl.py"
    generator_text = generator.read_text(encoding="utf-8")
    generator_text = replace_once(
        generator_text,
        "rejects oversized or excessively fragmented bodies before entering FastMCP.",
        "rejects oversized or excessively fragmented bodies before entering the MCP SDK application.",
        generator,
    )
    staged[generator] = generator_text

    audit = ROOT / "skills/agents-md-architect/tools/audit_agents_md.py"
    audit_text = audit.read_text(encoding="utf-8")
    shell_start = "def _extract_shell_invocations(text: str) -> set[str]:\n"
    shell_end = "def _extract_powershell_invocations(text: str) -> set[str]:\n"
    shell_replacement = '''def _shell_line_continues(line: str) -> bool:
    """Return whether the physical shell line ends in an active backslash-newline."""
    quote: str | None = None
    escaped = False
    for character in line.rstrip():
        if quote == "'":
            if character == "'":
                quote = None
            continue
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character in "'\\\"":
            quote = character if quote is None else None if quote == character else quote
    return escaped


def _logical_shell_lines(text: str) -> list[str]:
    """Join backslash-continued physical lines before shell normalization."""
    logical: list[str] = []
    pending = ""
    for raw_line in text.splitlines():
        candidate = raw_line.rstrip()
        combined = f"{pending}{candidate.lstrip()}" if pending else candidate
        if _shell_line_continues(combined):
            pending = f"{combined.rstrip()[:-1]} "
            continue
        logical.append(combined)
        pending = ""
    if pending:
        logical.append(pending.rstrip())
    return logical


def _extract_shell_invocations(text: str) -> set[str]:
    invocations: set[str] = set()
    heredoc_end: str | None = None
    for raw_line in _logical_shell_lines(text):
        line = raw_line.strip()
        if heredoc_end is not None:
            if line == heredoc_end:
                heredoc_end = None
            continue
        if not line or line.startswith("#"):
            continue
        heredoc = re.search(r"<<-?\\s*(['\\\"]?)([A-Za-z_][A-Za-z0-9_]*)\\1", line)
        if heredoc is not None:
            command = line[: heredoc.start()].rstrip()
            if command:
                _add_command_segments(invocations, command)
            heredoc_end = heredoc.group(2)
            continue
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\\s*\\(\\)\\s*\\{?", line):
            continue
        if re.fullmatch(r"[{}]", line):
            continue
        _add_command_segments(invocations, line)
    return invocations


'''
    audit_text = replace_between(audit_text, shell_start, shell_end, shell_replacement, audit)
    staged[audit] = audit_text

    parser = ROOT / "skills/agents-md-architect/tools/agents_md_parse.py"
    parser_text = parser.read_text(encoding="utf-8")
    read_start = "def read_utf8_bounded(path: Path, max_bytes: int = MAX_INSTRUCTION_FILE_BYTES) -> ReadResult:\n"
    read_end = "def _iter_code_spans(line: str) -> Iterator[str]:\n"
    read_replacement = '''def _supports_component_nofollow() -> bool:
    return bool(
        getattr(os, "O_NOFOLLOW", 0)
        and getattr(os, "O_DIRECTORY", 0)
        and os.open in getattr(os, "supports_dir_fd", set())
    )


def _open_component_safe(path: Path, flags: int) -> int:
    """Open an absolute path without following any intermediate or final symlink."""
    absolute = path.absolute()
    parts = absolute.parts
    if len(parts) < 2:
        raise OSError("input path has no final component")
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory = os.open(parts[0], directory_flags)
    try:
        for component in parts[1:-1]:
            child = os.open(component, directory_flags, dir_fd=directory)
            os.close(directory)
            directory = child
        return os.open(parts[-1], flags | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory)
    finally:
        os.close(directory)


def read_utf8_bounded(path: Path, max_bytes: int = MAX_INSTRUCTION_FILE_BYTES) -> ReadResult:
    """Read at most max_bytes plus one from a stable, component-confined regular file."""
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    expected_identity: os.stat_result | None = None
    component_safe = _supports_component_nofollow()
    if not component_safe:
        try:
            expected_identity = os.lstat(path)
            if stat.S_ISLNK(expected_identity.st_mode):
                return ReadResult(None, 0, "input.read-error", "Refusing to read a symlink.")
        except OSError as error:
            return ReadResult(None, 0, "input.read-error", f"Could not inspect input file: {error}")

    try:
        descriptor = _open_component_safe(path, flags) if component_safe else os.open(path, flags)
    except OSError as error:
        return ReadResult(None, 0, "input.read-error", f"Could not open input file: {error}")

    try:
        metadata = os.fstat(descriptor)
        if expected_identity is not None:
            try:
                current_identity = os.lstat(path)
            except OSError as error:
                return ReadResult(None, 0, "input.read-error", f"Could not re-inspect input file: {error}")
            if not os.path.samestat(expected_identity, metadata) or not os.path.samestat(current_identity, metadata):
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
                f"Input file is {metadata.st_size} bytes; maximum supported size is {max_bytes} bytes.",
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
    parser_text = replace_between(parser_text, read_start, read_end, read_replacement, parser)
    staged[parser] = parser_text

    codex_tests = ROOT / "tests/test_agents_md_codex_followup.py"
    codex_text = codex_tests.read_text(encoding="utf-8")
    codex_text = replace_once(codex_text, "import stat\n", "import os\nimport stat\n", codex_tests)
    codex_append = '''


def test_github_literal_run_joins_shell_continuations(tmp_path: Path) -> None:
    write(
        tmp_path / ".github/workflows/ci.yml",
        """name: CI

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: |
          python scripts/ci.py \\
            --strict
""",
    )
    write(
        tmp_path / "AGENTS.md",
        valid_application().replace("python scripts/ci.py", "python scripts/ci.py --strict"),
    )
    _, findings = audit_module.audit(tmp_path, "application", "single", "en")
    assert "commands.unlocated-full-gate" not in codes(findings)


def test_component_safe_reader_rejects_intermediate_symlink(tmp_path: Path) -> None:
    if not parser._supports_component_nofollow():
        pytest.skip("component-wise no-follow open is not available")
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    write(outside / "secret.txt", "outside")
    (tmp_path / "redirect").symlink_to(outside, target_is_directory=True)
    result = parser.read_utf8_bounded(tmp_path / "redirect/secret.txt")
    assert result.code == "input.read-error"
    assert result.text is None
'''
    if "test_github_literal_run_joins_shell_continuations" in codex_text:
        raise RuntimeError("shell continuation regression already exists")
    staged[codex_tests] = codex_text.rstrip() + codex_append + "\n"

    migration_tests = ROOT / "tests/test_mcp_migration_standard.py"
    migration_text = migration_tests.read_text(encoding="utf-8")
    migration_append = '''


def test_published_python_composition_example_uses_sdk_v2() -> None:
    example = (MCP / "examples/python/server_composition.py.example").read_text(encoding="utf-8")
    assert "from mcp.server.mcpserver import Context, MCPServer" in example
    assert "MCPServer[AppContext]" in example
    assert "Context[AppContext]" in example
    assert 'version="0.1.0"' in example
    assert "mcp.server.fastmcp" not in example
    assert "ServerSession" not in example
    assert "stateless_http=True" not in example
    compile(example, "server_composition.py.example", "exec")
'''
    if "test_published_python_composition_example_uses_sdk_v2" in migration_text:
        raise RuntimeError("example SDK regression already exists")
    staged[migration_tests] = migration_text.rstrip() + migration_append + "\n"

    for path, content in staged.items():
        path.write_text(content, encoding="utf-8", newline="")
        print(path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
