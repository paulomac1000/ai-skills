"""Deterministic retrieval checks against the real release documentation."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKEN = re.compile(r"[a-z0-9][a-z0-9.-]*")
QUERIES = [
    ("afds-doc-writer/SKILL.md", "write technical documentation from evidence"),
    ("afds-doc-writer/STANDARD.md", "canonical owner metadata verification normative docs"),
    ("ci-cd-architect/SKILL.md", "audit github actions delivery pipeline"),
    ("ci-cd-architect/STANDARD.md", "least privilege immutable actions tested artifact rollback"),
    ("mcp-server-architect/SKILL.md", "build secure agent friendly mcp server"),
    ("mcp-server-architect/STANDARD.md", "mcp transport authorization errors cancellation observability"),
    ("mcp-server-consumer/SKILL.md", "invoke mcp tools safely efficiently"),
    ("mcp-server-consumer/STANDARD.md", "confirmation destructive retry partial execution sensitive data"),
    ("pre-commit-architect/SKILL.md", "design fast local git hooks"),
    ("pre-commit-architect/STANDARD.md", "pre-commit latency budget ci parity no network"),
    ("afds-doc-writer/STANDARD.md", "duplicate docs historical scaffolding first stable release"),
    ("ci-cd-architect/STANDARD.md", "cache key artifact digest publication recovery"),
    ("mcp-server-architect/STANDARD.md", "stdio stdout protocol logs stderr"),
    ("mcp-server-consumer/STANDARD.md", "unknown effect defer target permission"),
    ("pre-commit-architect/STANDARD.md", "pre-push compilation unit tests documentation validation"),
]


@dataclass(frozen=True)
class Document:
    """One indexed skill document."""

    key: str
    text: str


def tokens(value: str) -> list[str]:
    """Tokenize text for the small deterministic ranker."""
    return TOKEN.findall(value.lower())


def documents() -> list[Document]:
    """Load the actual SKILL and STANDARD files shipped by the repository."""
    result = []
    for path in sorted((ROOT / "skills").glob("*/*.md")):
        result.append(Document(path.relative_to(ROOT / "skills").as_posix(), path.read_text(encoding="utf-8")))
    return result


class Ranker:
    """Small BM25-like ranker used only for deterministic regression tests."""

    def __init__(self, items: list[Document]):
        self.items = items
        self.counts = [Counter(tokens(item.text)) for item in items]
        self.lengths = [sum(count.values()) for count in self.counts]
        self.average = sum(self.lengths) / len(self.lengths)
        frequency = Counter(term for count in self.counts for term in count)
        self.idf = {
            term: math.log(1 + (len(items) - value + 0.5) / (value + 0.5))
            for term, value in frequency.items()
        }

    def rank(self, query: str) -> list[int]:
        """Return document indexes ordered by descending lexical relevance."""
        scored = []
        for index, count in enumerate(self.counts):
            score = 0.0
            for term in tokens(query):
                frequency = count.get(term, 0)
                if frequency:
                    score += self.idf.get(term, 0.0) * frequency / (
                        frequency + 1.5 * (0.25 + 0.75 * self.lengths[index] / self.average)
                    )
            scored.append((score, self.items[index].key, index))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [index for _, _, index in scored]


def evaluate() -> tuple[float, float, float]:
    """Return recall at three, MRR, and average top-three context size."""
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


def test_real_skill_documents_remain_retrievable_without_context_bloat() -> None:
    items = documents()
    recall_at_three, mrr, average_context = evaluate()
    assert len(items) == 10
    assert len(QUERIES) == 15
    assert recall_at_three >= 0.90
    assert mrr >= 0.80
    assert average_context <= 28_000
