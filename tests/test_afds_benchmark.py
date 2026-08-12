"""Deterministic retrieval checks against the recovered documentation corpus."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKEN = re.compile(r"[a-z0-9][a-z0-9.-]*")
QUERIES = [
    ("afds-doc-writer/SKILL.md", "write repair technical documentation evidence ownership verification"),
    ("afds-doc-writer/STANDARD.md", "canonical owner metadata document type factual evidence"),
    ("afds-doc-writer/references/lifecycle-and-impact.md", "upstream downstream conflict review trigger deprecation"),
    ("afds-doc-writer/references/type-playbooks.md", "workflow reference system guide decision contract structure"),
    ("ci-cd-architect/SKILL.md", "audit github actions delivery pipeline quality gates"),
    ("ci-cd-architect/STANDARD.md", "least privilege immutable action build smoke test publish same artifact"),
    ("ci-cd-architect/references/local-quality-gates.md", "pre-commit pre-push latency no network ci parity"),
    ("ci-cd-architect/references/action-sha-maintenance.md", "template full commit sha renovate dependency pin"),
    ("ci-cd-architect/references/failure-patterns.md", "nuget cache workflow token tag pip semgrep failure"),
    ("mcp-server-architect/SKILL.md", "design secure agent friendly mcp server sdk review"),
    ("mcp-server-architect/STANDARD.md", "transport authorization errors cancellation observability maturity"),
    (
        "mcp-server-architect/references/python-official-mcp-sdk.md",
        "official python mcp sdk package mcp protocol revision wheel exact artifact",
    ),
    (
        "mcp-server-architect/references/python-fastmcp-package.md",
        "fastmcp package access token authmiddleware mounted server middleware provider",
    ),
    (
        "mcp-server-architect/references/dotnet-mcp.md",
        "dotnet dependency injection cancellationtoken activity test host",
    ),
    (
        "mcp-server-architect/references/security-and-operations.md",
        "confused deputy tool poisoning health rate limit shutdown",
    ),
    ("mcp-server-consumer/SKILL.md", "invoke mcp capabilities safely efficiently verify"),
    ("mcp-server-consumer/STANDARD.md", "unknown risk defer retry partial execution pagination"),
    ("mcp-server-consumer/references/risk-and-trust.md", "untrusted read prefix downgrade provenance confirmation"),
    (
        "mcp-server-consumer/references/error-recovery-and-workflows.md",
        "conflict refresh compensation timeout partial batch",
    ),
]


@dataclass(frozen=True)
class Document:
    key: str
    text: str


def tokens(value: str) -> list[str]:
    return TOKEN.findall(value.lower())


def documents() -> list[Document]:
    result = []
    for path in sorted((ROOT / "skills").glob("**/*.md")):
        result.append(
            Document(
                path.relative_to(ROOT / "skills").as_posix(),
                path.read_text(encoding="utf-8"),
            )
        )
    return result


class Ranker:
    def __init__(self, items: list[Document]):
        self.items = items
        self.counts = [Counter(tokens(item.text)) for item in items]
        self.lengths = [sum(count.values()) for count in self.counts]
        self.average = sum(self.lengths) / len(self.lengths)
        frequency = Counter(term for count in self.counts for term in count)
        self.idf = {term: math.log(1 + (len(items) - value + 0.5) / (value + 0.5)) for term, value in frequency.items()}

    def rank(self, query: str) -> list[int]:
        scored = []
        for index, count in enumerate(self.counts):
            score = 0.0
            for term in tokens(query):
                frequency = count.get(term, 0)
                if frequency:
                    score += (
                        self.idf.get(term, 0.0)
                        * frequency
                        / (frequency + 1.5 * (0.25 + 0.75 * self.lengths[index] / self.average))
                    )
            scored.append((score, self.items[index].key, index))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [index for _, _, index in scored]


def evaluate() -> tuple[float, float, float]:
    items = documents()
    ranker = Ranker(items)
    positions = []
    context_sizes = []
    for target, query in QUERIES:
        ranking = ranker.rank(query)
        position = next(index + 1 for index, item_index in enumerate(ranking) if items[item_index].key == target)
        positions.append(position)
        context_sizes.append(sum(len(items[item_index].text) for item_index in ranking[:3]))
    recall_at_three = sum(position <= 3 for position in positions) / len(positions)
    mrr = sum(1 / position for position in positions) / len(positions)
    return recall_at_three, mrr, sum(context_sizes) / len(context_sizes)


def test_recovered_documents_remain_retrievable_without_monolithic_context() -> None:
    items = documents()
    recall_at_three, mrr, average_context = evaluate()
    assert len(items) >= 20
    assert len(QUERIES) >= 19
    assert recall_at_three >= 0.88
    assert mrr >= 0.78
    assert average_context <= 24_000
