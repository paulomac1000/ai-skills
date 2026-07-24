#!/usr/bin/env python3
"""Apply the reviewed one-time typing boundary fix to the consumer engine."""

from __future__ import annotations

from pathlib import Path

TARGET = Path("skills/mcp-server-consumer/tools/decision_engine.py")


def replace_once(text: str, old: str, new: str) -> str:
    """Replace one expected fragment, while allowing an already-applied result."""
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected one source fragment, found {count}: {old[:80]!r}")
    return text.replace(old, new)


def main() -> int:
    """Widen untrusted public inputs before narrowing them at runtime."""
    text = TARGET.read_text(encoding="utf-8")
    text = replace_once(
        text,
        """    if normalized is Risk.DANGEROUS:
        return Decision.CONFIRM_THEN_INVOKE if intent is UserIntent.EXPLICIT_BY_NAME else Decision.REJECT
    return Decision.DEFER
""",
        """    if normalized is Risk.DANGEROUS:
        return Decision.CONFIRM_THEN_INVOKE if intent is UserIntent.EXPLICIT_BY_NAME else Decision.REJECT
""",
    )
    text = replace_once(
        text,
        """def get_error_strategy(
    error_code: str | None,
    manifest: Mapping[str, Any] | None = None,
) -> ErrorStrategy:
""",
        """def get_error_strategy(
    error_code: str | None,
    manifest: object = None,
) -> ErrorStrategy:
""",
    )
    text = replace_once(
        text,
        """def should_retry(
    *,
    error_code: str | None,
    attempt: int,
    operation_idempotent: bool,
    manifest: Mapping[str, Any] | None = None,
    response_retryable: bool | None = None,
    precondition_refreshed: bool = False,
    reconciliation_completed: bool = False,
) -> bool:
""",
        """def should_retry(
    *,
    error_code: str | None,
    attempt: object,
    operation_idempotent: object,
    manifest: object = None,
    response_retryable: object = None,
    precondition_refreshed: object = False,
    reconciliation_completed: object = False,
) -> bool:
""",
    )
    text = replace_once(
        text,
        """    if isinstance(content, Sequence) and not isinstance(content, (str, bytes, bytearray)):
        messages = [
            item.get("text")
            for item in content
            if isinstance(item, Mapping) and isinstance(item.get("text"), str)
        ]
        if messages:
            return "MCP_TOOL_ERROR", "\n".join(messages)
""",
        """    if isinstance(content, Sequence) and not isinstance(content, (str, bytes, bytearray)):
        messages: list[str] = []
        for item in content:
            if isinstance(item, Mapping):
                item_text = item.get("text")
                if isinstance(item_text, str):
                    messages.append(item_text)
        if messages:
            return "MCP_TOOL_ERROR", "\n".join(messages)
""",
    )
    text = replace_once(
        text,
        "def handle_response(response: Mapping[str, Any]) -> ResponseResult:",
        "def handle_response(response: object) -> ResponseResult:",
    )
    text = replace_once(
        text,
        """def select_efficient_tool(
    tools: Iterable[Mapping[str, Any]],
    *,
    required_capabilities: Iterable[str],
""",
        """def select_efficient_tool(
    tools: Iterable[object],
    *,
    required_capabilities: Iterable[object],
""",
    )
    text = replace_once(
        text,
        "def choose_initial_detail_params(input_schema: Mapping[str, Any]) -> dict[str, Any]:",
        "def choose_initial_detail_params(input_schema: object) -> dict[str, Any]:",
    )
    text = replace_once(
        text,
        """def get_pagination_decision(
    meta: Mapping[str, Any],
    *,
    outcome_satisfied: bool,
    pages_seen: int,
    max_pages: int,
""",
        """def get_pagination_decision(
    meta: object,
    *,
    outcome_satisfied: object,
    pages_seen: object,
    max_pages: object,
""",
    )
    text = replace_once(
        text,
        """    if type(pages_seen) is not int or type(max_pages) is not int or pages_seen < 0 or max_pages <= 0:
        return PaginationDecision(False, reason="invalid pagination bounds")
    if outcome_satisfied:
""",
        """    if (
        type(outcome_satisfied) is not bool
        or type(pages_seen) is not int
        or type(max_pages) is not int
        or pages_seen < 0
        or max_pages <= 0
    ):
        return PaginationDecision(False, reason="invalid pagination bounds")
    if outcome_satisfied:
""",
    )
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
