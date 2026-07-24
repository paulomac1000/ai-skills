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
        """    if normalized is Risk.DANGEROUS:\n        return Decision.CONFIRM_THEN_INVOKE if intent is UserIntent.EXPLICIT_BY_NAME else Decision.REJECT\n    return Decision.DEFER\n""",
        """    if normalized is Risk.DANGEROUS:\n        return Decision.CONFIRM_THEN_INVOKE if intent is UserIntent.EXPLICIT_BY_NAME else Decision.REJECT\n""",
    )
    text = replace_once(
        text,
        """def get_error_strategy(\n    error_code: str | None,\n    manifest: Mapping[str, Any] | None = None,\n) -> ErrorStrategy:\n""",
        """def get_error_strategy(\n    error_code: str | None,\n    manifest: object = None,\n) -> ErrorStrategy:\n""",
    )
    text = replace_once(
        text,
        """def should_retry(\n    *,\n    error_code: str | None,\n    attempt: int,\n    operation_idempotent: bool,\n    manifest: Mapping[str, Any] | None = None,\n    response_retryable: bool | None = None,\n    precondition_refreshed: bool = False,\n    reconciliation_completed: bool = False,\n) -> bool:\n""",
        """def should_retry(\n    *,\n    error_code: str | None,\n    attempt: object,\n    operation_idempotent: object,\n    manifest: object = None,\n    response_retryable: object = None,\n    precondition_refreshed: object = False,\n    reconciliation_completed: object = False,\n) -> bool:\n""",
    )
    text = replace_once(
        text,
        """    if isinstance(content, Sequence) and not isinstance(content, (str, bytes, bytearray)):\n        messages = [\n            item.get(\"text\") for item in content if isinstance(item, Mapping) and isinstance(item.get(\"text\"), str)\n        ]\n        if messages:\n            return \"MCP_TOOL_ERROR\", \"\\n\".join(messages)\n""",
        """    if isinstance(content, Sequence) and not isinstance(content, (str, bytes, bytearray)):\n        messages: list[str] = []\n        for item in content:\n            if isinstance(item, Mapping):\n                item_text = item.get(\"text\")\n                if isinstance(item_text, str):\n                    messages.append(item_text)\n        if messages:\n            return \"MCP_TOOL_ERROR\", \"\\n\".join(messages)\n""",
    )
    text = replace_once(
        text,
        "def handle_response(response: Mapping[str, Any]) -> ResponseResult:",
        "def handle_response(response: object) -> ResponseResult:",
    )
    text = replace_once(
        text,
        """def select_efficient_tool(\n    tools: Iterable[Mapping[str, Any]],\n    *,\n    required_capabilities: Iterable[str],\n""",
        """def select_efficient_tool(\n    tools: Iterable[object],\n    *,\n    required_capabilities: Iterable[object],\n""",
    )
    text = replace_once(
        text,
        "def choose_initial_detail_params(input_schema: Mapping[str, Any]) -> dict[str, Any]:",
        "def choose_initial_detail_params(input_schema: object) -> dict[str, Any]:",
    )
    text = replace_once(
        text,
        """def get_pagination_decision(\n    meta: Mapping[str, Any],\n    *,\n    outcome_satisfied: bool,\n    pages_seen: int,\n    max_pages: int,\n""",
        """def get_pagination_decision(\n    meta: object,\n    *,\n    outcome_satisfied: object,\n    pages_seen: object,\n    max_pages: object,\n""",
    )
    text = replace_once(
        text,
        """    if type(pages_seen) is not int or type(max_pages) is not int or pages_seen < 0 or max_pages <= 0:\n        return PaginationDecision(False, reason=\"invalid pagination bounds\")\n    if outcome_satisfied:\n""",
        """    if (\n        type(outcome_satisfied) is not bool\n        or type(pages_seen) is not int\n        or type(max_pages) is not int\n        or pages_seen < 0\n        or max_pages <= 0\n    ):\n        return PaginationDecision(False, reason=\"invalid pagination bounds\")\n    if outcome_satisfied:\n""",
    )
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
