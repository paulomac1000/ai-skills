"""Apply the precise mypy type widening required by the AST walker."""

from __future__ import annotations

from .common import replace_once


def stage(text: str) -> str:
    text = replace_once(
        text,
        "from typing import Literal\n",
        "from typing import Literal, cast\n",
        label="audit AST cast import",
    )
    return replace_once(
        text,
        "    for node in tree.body:\n",
        "    for node in cast(list[ast.AST], tree.body):\n",
        label="audit AST statement widening",
    )
