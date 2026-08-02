"""Patch Markdown parsing and bounded file reads."""

from __future__ import annotations

from textwrap import dedent

from .common import read, replace_between, replace_once


def stage() -> str:
    path = "skills/agents-md-architect/tools/agents_md_parse.py"
    text = read(path)
    text = replace_once(
        text,
        "import re\nfrom collections.abc import Iterator, Sequence\n",
        "import os\nimport re\nimport stat\nfrom collections.abc import Iterator, Sequence\n",
        label=f"{path} imports",
    )
    text = replace_between(
        text,
        "def strip_blockquote_prefix(line: str) -> str:\n",
        "def _is_fence_closer(line: str, character: str, minimum_length: int) -> bool:\n",
        dedent(
            '''\
            def strip_blockquote_prefix(line: str) -> str:
                """Remove CommonMark blockquote prefixes for active-line parsing."""
                return _blockquote_depth_and_content(line)[1]


            LIST_ITEM = re.compile(
                r"^(?P<indent> {0,3})(?P<marker>(?:[*+-]|\\d{1,9}[.)]))"
                r"(?P<padding>(?: {1,4}|\\t))(?P<content>.*)$"
            )


            def _list_container_content(
                line: str,
                active_indents: tuple[int, ...],
                *,
                allow_new_item: bool,
            ) -> tuple[str, tuple[int, ...]]:
                """Strip active list-item indentation before parsing Markdown fences."""
                stack = list(active_indents)
                if line.strip():
                    while stack and not line.startswith(" " * stack[-1]):
                        stack.pop()

                active_indent = stack[-1] if stack else 0
                content = line[active_indent:] if active_indent else line
                if not allow_new_item:
                    return content, tuple(stack)

                match = LIST_ITEM.fullmatch(content)
                if match is None:
                    return content, tuple(stack)

                padding = match.group("padding")
                padding_width = 4 if padding == "\\t" else len(padding)
                content_indent = (
                    active_indent
                    + len(match.group("indent"))
                    + len(match.group("marker"))
                    + padding_width
                )
                while stack and stack[-1] >= content_indent:
                    stack.pop()
                stack.append(content_indent)
                return match.group("content"), tuple(stack)


            '''
        ),
        label=f"{path} list containers",
    )
    text = replace_between(
        text,
        "def parse_visible_lines(text: str) -> tuple[list[tuple[int, str]], int | None]:\n",
        "def read_utf8_bounded(path: Path, max_bytes: int = MAX_INSTRUCTION_FILE_BYTES) -> ReadResult:\n",
        dedent(
            '''\
            def parse_visible_lines(text: str) -> tuple[list[tuple[int, str]], int | None]:
                """Return active lines outside fenced blocks and a stable unclosed-fence line."""
                visible: list[tuple[int, str]] = []
                fence_character: str | None = None
                minimum_length = 0
                fence_start: int | None = None
                fence_container: tuple[int, tuple[int, ...]] | None = None
                abandoned_fence_start: int | None = None
                list_indents: tuple[int, ...] = ()
                current_quote_depth = 0

                for line_number, source_line in enumerate(text.splitlines(), start=1):
                    quote_depth, container_line = _blockquote_depth_and_content(source_line)
                    if quote_depth != current_quote_depth:
                        list_indents = ()
                        current_quote_depth = quote_depth

                    line, candidate_indents = _list_container_content(
                        container_line,
                        list_indents,
                        allow_new_item=fence_character is None,
                    )
                    current_container = (quote_depth, candidate_indents)
                    if fence_character is not None and current_container != fence_container:
                        abandoned_fence_start = abandoned_fence_start or fence_start
                        fence_character = None
                        minimum_length = 0
                        fence_start = None
                        fence_container = None
                        line, candidate_indents = _list_container_content(
                            container_line,
                            candidate_indents,
                            allow_new_item=True,
                        )
                        current_container = (quote_depth, candidate_indents)
                    list_indents = candidate_indents

                    if fence_character is None:
                        opener = FENCE_OPENER.fullmatch(line)
                        if opener is not None:
                            marker = opener.group("marker")
                            info = opener.group("info")
                            if marker[0] != "`" or "`" not in info:
                                fence_character = marker[0]
                                minimum_length = len(marker)
                                fence_start = line_number
                                fence_container = current_container
                                continue
                        visible.append((line_number, source_line))
                        continue

                    if _is_fence_closer(line, fence_character, minimum_length):
                        fence_character = None
                        minimum_length = 0
                        fence_start = None
                        fence_container = None

                return visible, fence_start or abandoned_fence_start


            '''
        ),
        label=f"{path} visible-line parser",
    )
    text = replace_between(
        text,
        "def read_utf8_bounded(path: Path, max_bytes: int = MAX_INSTRUCTION_FILE_BYTES) -> ReadResult:\n",
        "def _iter_code_spans(line: str) -> Iterator[str]:\n",
        dedent(
            '''\
            def read_utf8_bounded(path: Path, max_bytes: int = MAX_INSTRUCTION_FILE_BYTES) -> ReadResult:
                """Read at most max_bytes plus one from a regular file without following symlinks."""
                flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
                nofollow = getattr(os, "O_NOFOLLOW", 0)
                if nofollow:
                    flags |= nofollow
                else:
                    try:
                        if path.is_symlink():
                            return ReadResult(None, 0, "input.read-error", "Refusing to read a symlink.")
                    except OSError as error:
                        return ReadResult(None, 0, "input.read-error", f"Could not inspect input file: {error}")

                try:
                    descriptor = os.open(path, flags)
                except OSError as error:
                    return ReadResult(None, 0, "input.read-error", f"Could not open input file: {error}")

                try:
                    metadata = os.fstat(descriptor)
                    if not stat.S_ISREG(metadata.st_mode):
                        return ReadResult(None, 0, "input.read-error", "Input is not a regular file.")
                    if metadata.st_size > max_bytes:
                        return ReadResult(
                            None,
                            metadata.st_size,
                            "input.too-large",
                            (
                                f"Input file is {metadata.st_size} bytes; "
                                f"maximum supported size is {max_bytes} bytes."
                            ),
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
        ),
        label=f"{path} bounded read",
    )
    return text
