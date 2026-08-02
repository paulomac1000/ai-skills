"""Patch executable command evidence extraction."""

from __future__ import annotations

from textwrap import dedent

from .common import read, replace_between, replace_once


def stage() -> str:
    path = "skills/agents-md-architect/tools/audit_agents_md.py"
    text = read(path)
    text = replace_once(
        text,
        "import argparse\nimport json\n",
        "import argparse\nimport ast\nimport json\n",
        label=f"{path} ast import",
    )
    text = replace_between(
        text,
        "def _extract_gate_invocations(text: str) -> set[str]:\n",
        "def _entrypoint_invocations(discovery: Discovery) -> set[str]:\n",
        dedent(
            '''\
            def _add_command_segments(invocations: set[str], command: str) -> None:
                for segment in re.split(r"\\s*(?:&&|\\|\\||;)\\s*", command):
                    normalized = _normalize_invocation(segment.strip())
                    if normalized is not None:
                        invocations.add(normalized)


            YAML_COMMAND = re.compile(
                r"^(?P<indent>[ \\t]*)(?:-\\s*)?"
                r"(?P<key>run|script|command|bash|pwsh|powershell|sh|cmds):\\s*(?P<value>.*)$",
                re.I,
            )


            def _unquote_scalar(value: str) -> str:
                stripped = value.strip()
                if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in "'\\\"":
                    return stripped[1:-1]
                return stripped


            def _extract_yaml_invocations(text: str) -> set[str]:
                invocations: set[str] = set()
                lines = text.splitlines()
                index = 0
                while index < len(lines):
                    raw_line = lines[index]
                    stripped = raw_line.strip()
                    if not stripped or stripped.startswith("#"):
                        index += 1
                        continue
                    match = YAML_COMMAND.match(raw_line)
                    if match is None:
                        index += 1
                        continue
                    indentation = len(match.group("indent").replace("\\t", "    "))
                    value = match.group("value").strip()
                    if value and value not in {"|", ">", "|-", "|+", ">-", ">+"}:
                        _add_command_segments(invocations, _unquote_scalar(value))
                        index += 1
                        continue

                    index += 1
                    while index < len(lines):
                        nested = lines[index]
                        nested_stripped = nested.strip()
                        nested_indent = len(nested) - len(nested.lstrip(" "))
                        if nested_stripped and nested_indent <= indentation:
                            break
                        if nested_stripped and not nested_stripped.startswith("#"):
                            command = nested_stripped.removeprefix("- ").strip()
                            _add_command_segments(invocations, _unquote_scalar(command))
                        index += 1
                return invocations


            def _literal_python_command(node: ast.AST) -> str | None:
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    return node.value
                if isinstance(node, (ast.List, ast.Tuple)):
                    values: list[str] = []
                    for element in node.elts:
                        if not isinstance(element, ast.Constant) or not isinstance(element.value, str):
                            return None
                        values.append(element.value)
                    return shlex.join(values)
                return None


            def _extract_python_invocations(text: str) -> set[str]:
                try:
                    tree = ast.parse(text)
                except SyntaxError:
                    return set()
                invocations: set[str] = set()
                subprocess_calls = {"run", "call", "check_call", "check_output", "Popen"}
                subprocess_modules = {"subprocess"}
                os_modules = {"os"}
                subprocess_functions: set[str] = set()
                system_functions: set[str] = set()

                for node in tree.body:
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            local_name = alias.asname or alias.name
                            if alias.name == "subprocess":
                                subprocess_modules.add(local_name)
                            elif alias.name == "os":
                                os_modules.add(local_name)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module == "subprocess":
                            for alias in node.names:
                                if alias.name in subprocess_calls:
                                    subprocess_functions.add(alias.asname or alias.name)
                        elif node.module == "os":
                            for alias in node.names:
                                if alias.name == "system":
                                    system_functions.add(alias.asname or alias.name)

                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    accepted = False
                    if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                        owner = node.func.value.id
                        accepted = (
                            owner in subprocess_modules and node.func.attr in subprocess_calls
                        ) or (owner in os_modules and node.func.attr == "system")
                    elif isinstance(node.func, ast.Name):
                        accepted = (
                            node.func.id in subprocess_functions
                            or node.func.id in system_functions
                        )
                    if not accepted:
                        continue
                    argument = node.args[0] if node.args else None
                    if argument is None:
                        argument = next(
                            (
                                keyword.value
                                for keyword in node.keywords
                                if keyword.arg in {"args", "command"}
                            ),
                            None,
                        )
                    if argument is None:
                        continue
                    command = _literal_python_command(argument)
                    if command is not None:
                        _add_command_segments(invocations, command)
                return invocations


            def _extract_shell_invocations(text: str) -> set[str]:
                invocations: set[str] = set()
                heredoc_end: str | None = None
                for raw_line in text.splitlines():
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


            def _extract_powershell_invocations(text: str) -> set[str]:
                invocations: set[str] = set()
                in_block_comment = False
                here_string_end: str | None = None
                for raw_line in text.splitlines():
                    line = raw_line.strip()
                    if in_block_comment:
                        if "#>" in line:
                            in_block_comment = False
                        continue
                    if here_string_end is not None:
                        if line == here_string_end:
                            here_string_end = None
                        continue
                    if line.startswith("<#"):
                        in_block_comment = "#>" not in line
                        continue
                    if not line or line.startswith("#"):
                        continue
                    if line.endswith('@"') or line.endswith("@'"):
                        here_string_end = '"@' if line.endswith('@"') else "'@"
                        continue
                    _add_command_segments(invocations, line)
                return invocations


            def _extract_recipe_invocations(text: str, *, makefile: bool) -> set[str]:
                invocations: set[str] = set()
                in_recipe = False
                for raw_line in text.splitlines():
                    if makefile:
                        if raw_line.startswith("\\t"):
                            _add_command_segments(invocations, raw_line.lstrip().lstrip("@-+"))
                        continue
                    stripped = raw_line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    if not raw_line[:1].isspace():
                        in_recipe = stripped.endswith(":")
                        continue
                    if in_recipe:
                        _add_command_segments(invocations, stripped)
                return invocations


            def _extract_jenkins_invocations(text: str) -> set[str]:
                invocations: set[str] = set()
                pattern = re.compile(
                    r"\\b(?:sh|bat|powershell|pwsh)\\s*(?:\\(\\s*)?(?:script\\s*:\\s*)?"
                    r"(?P<quote>['\\\"])(?P<command>.*?)(?P=quote)"
                )
                for match in pattern.finditer(text):
                    _add_command_segments(invocations, match.group("command"))
                return invocations


            def _extract_gate_invocations(relative: str, text: str) -> set[str]:
                path = Path(relative)
                name = path.name
                suffix = path.suffix.casefold()
                if suffix in {".yml", ".yaml"}:
                    return _extract_yaml_invocations(text)
                if name == "Jenkinsfile":
                    return _extract_jenkins_invocations(text)
                if name.casefold() == "makefile":
                    return _extract_recipe_invocations(text, makefile=True)
                if name.casefold() == "justfile":
                    return _extract_recipe_invocations(text, makefile=False)
                if suffix == ".py":
                    return _extract_python_invocations(text)
                if suffix == ".ps1":
                    return _extract_powershell_invocations(text)
                if suffix == ".sh" or not suffix and relative.startswith("bin/"):
                    return _extract_shell_invocations(text)
                return set()


            '''
        ),
        label=f"{path} executable gate extraction",
    )
    text = replace_once(
        text,
        "        commands.update(_extract_gate_invocations(result.text))\n",
        "        commands.update(_extract_gate_invocations(relative, result.text))\n",
        label=f"{path} gate extraction call",
    )
    return text
