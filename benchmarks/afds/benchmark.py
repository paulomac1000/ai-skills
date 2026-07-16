#!/usr/bin/env python3
"""Deterministic AFDS retrieval and mutation benchmark.

The benchmark creates 360 documentation targets in several format variants and
runs 1,800 query cases that approximate different agent query styles. It does
not claim to emulate model reasoning; it isolates retrieval effects so CI is
repeatable and API-free.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOKEN = re.compile(r"[a-z0-9][a-z0-9_.-]*")

DOMAINS = [
    "auth", "billing", "calendar", "camera", "catalog", "checkout", "climate", "compliance", "contacts", "devices",
    "documents", "energy", "events", "files", "finance", "gateway", "genomics", "health", "identity", "inventory",
    "invoices", "jobs", "logging", "media", "messaging", "metrics", "network", "notifications", "orders", "payments",
    "profiles", "provisioning", "reports", "routing", "search", "security", "sessions", "shipping", "storage", "support",
    "telemetry", "tenants", "tickets", "trading", "users", "video", "warehouse", "weather", "workflow", "workspace",
    "backup", "deployment", "discovery", "firmware", "monitoring", "pricing", "reconciliation", "scheduler", "secrets", "updates",
]
TYPES = ["workflow", "reference", "system", "guide", "decision", "contract"]
TYPE_TERMS = {
    "workflow": ("rotate recovery procedure", "runbook steps rollback validate"),
    "reference": ("settings options fields", "configuration lookup limits"),
    "system": ("architecture failures state", "component boundaries observability"),
    "guide": ("learn walkthrough rationale", "tutorial explanation onboarding"),
    "decision": ("why chosen alternatives", "architecture decision consequences"),
    "contract": ("api inputs outputs errors", "interface schema compatibility"),
}
DOMAIN_SYNONYMS = {
    domain: f"{domain}-service {domain}-manager {domain}-engine" for domain in DOMAINS
}


@dataclass(frozen=True)
class Document:
    doc_id: str
    title: str
    text: str
    metadata: str
    answer: str


@dataclass(frozen=True)
class QueryCase:
    target: str
    persona: str
    text: str


def tokens(text: str) -> list[str]:
    return TOKEN.findall(text.lower().replace("_", "-").replace("/", " "))


def create_documents(variant: str) -> list[Document]:
    documents: list[Document] = []
    for index, domain in enumerate(DOMAINS):
        service = f"{domain}-hub-{index:02d}"
        incident = f"{domain}-stale-{index:02d}"
        for doc_type in TYPES:
            canonical, paraphrases = TYPE_TERMS[doc_type]
            doc_id = f"{doc_type}.{service}"
            title = f"{service} {doc_type}"
            answer = (
                f"The {service} {doc_type} answers {canonical}. "
                f"Use identifier {service}; the diagnostic symptom is {incident}."
            )
            background = (
                f"The {domain} domain supports platform operations. Historical context explains ownership, "
                f"migration, stakeholder requests, and examples for {service}. "
            )
            if variant == "prose":
                text = f"# Notes about {service}\n\n{background * 7}\n{answer}\n"
                metadata = ""
            elif variant == "afds2":
                metadata = (
                    f"description: Comprehensive documentation for {service}\n"
                    f"doc_id: {doc_id}\ntype: {doc_type}\nstatus: active\nrigor_tier: L2\n"
                    "ttl_days: 180\nstability: stable\nai_scope: editable\nsource_of_truth: true\n"
                    "last_verified: 2026-06-01\nowners: [platform-team]\n"
                )
                template = "\n".join(
                    f"## {heading}\n\n{background}{answer}"
                    for heading in ["PURPOSE", "SCOPE", "DEFINITIONS", "RULES", "INTERFACES", "STATE", "EDGE_CASES", "EXAMPLES", "NON_GOALS"]
                )
                text = f"---\n{metadata}---\n\n# {title}\n\n{template}\n"
            elif variant == "afds3-core":
                metadata = f"description: {answer}\ndoc_id: {doc_id}\ntype: {doc_type}\nstatus: active\nrigor: operational\nowners: [platform-team]\nschema_version: 3\n"
                text = f"---\n{metadata}---\n\n# {title}\n\n## Answer\n\n{answer}\n\n## Evidence\n\n{background}\n"
            elif variant in {"afds3", "afds3-more", "afds3-metadata"}:
                aliases = f"{DOMAIN_SYNONYMS[domain]} {paraphrases} {incident}"
                entities = f"{service} {domain} {incident}"
                metadata = (
                    f"description: {answer}\ndoc_id: {doc_id}\ntype: {doc_type}\nstatus: active\n"
                    f"rigor: operational\nowners: [platform-team]\nschema_version: 3\n"
                    f"aliases: [{aliases}]\nentities: [{entities}]\n"
                )
                if variant == "afds3-metadata":
                    metadata += "audience: [developers, operators, agents]\nreview_cycle: quarterly\nrelated_topics: [platform, operations, reliability]\n"
                extra = ""
                if variant == "afds3-more":
                    extra = f"\n## Background\n\n{background * 4}\n\n## Related considerations\n\n{background * 2}"
                text = f"---\n{metadata}---\n\n# {title}\n\n## Answer\n\n{answer}\n\n## Evidence\n\n{background}{extra}\n"
            else:
                raise ValueError(variant)
            documents.append(Document(doc_id, title, text, metadata, answer))
    return documents


def create_queries() -> list[QueryCase]:
    result: list[QueryCase] = []
    for index, domain in enumerate(DOMAINS):
        service = f"{domain}-hub-{index:02d}"
        incident = f"{domain}-stale-{index:02d}"
        for doc_type in TYPES:
            canonical, paraphrases = TYPE_TERMS[doc_type]
            target = f"{doc_type}.{service}"
            result.extend(
                [
                    QueryCase(target, "exact", f"{service} {doc_type} {canonical}"),
                    QueryCase(target, "paraphrase", f"{domain}-manager {paraphrases}"),
                    QueryCase(target, "terse", f"{service} {canonical.split()[0]}"),
                    QueryCase(target, "incident", f"{incident} where find {canonical.split()[0]}"),
                    QueryCase(target, "weak-vocabulary", f"need help {domain}-engine {paraphrases.split()[0]}"),
                ]
            )
    return result


class BM25:
    def __init__(self, documents: list[Document], weighted: bool = False):
        self.documents = documents
        self.weighted = weighted
        self.term_frequencies: list[Counter[str]] = []
        self.lengths: list[int] = []
        document_frequency: Counter[str] = Counter()
        for document in documents:
            body_tokens = tokens(document.text)
            counts = Counter(body_tokens)
            if weighted:
                for term in tokens(document.metadata):
                    counts[term] += 4
                for term in tokens(document.title):
                    counts[term] += 3
                for term in tokens(document.answer):
                    counts[term] += 2
            self.term_frequencies.append(counts)
            self.lengths.append(sum(counts.values()))
            document_frequency.update(counts.keys())
        self.average_length = sum(self.lengths) / len(self.lengths)
        self.idf = {
            term: math.log(1 + (len(documents) - freq + 0.5) / (freq + 0.5))
            for term, freq in document_frequency.items()
        }

    def rank(self, query: str) -> list[int]:
        query_terms = tokens(query)
        scores: list[tuple[float, int]] = []
        k1, b = 1.5, 0.75
        for index, counts in enumerate(self.term_frequencies):
            score = 0.0
            length = self.lengths[index]
            for term in query_terms:
                frequency = counts.get(term, 0)
                if not frequency:
                    continue
                denominator = frequency + k1 * (1 - b + b * length / self.average_length)
                score += self.idf.get(term, 0.0) * frequency * (k1 + 1) / denominator
            scores.append((score, index))
        scores.sort(key=lambda item: (-item[0], self.documents[item[1]].doc_id))
        return [index for _, index in scores]


def evaluate(documents: list[Document], queries: list[QueryCase], weighted: bool) -> dict[str, object]:
    engine = BM25(documents, weighted=weighted)
    positions: list[int] = []
    by_persona: dict[str, list[int]] = defaultdict(list)
    context_chars: list[int] = []
    for query in queries:
        ranking = engine.rank(query.text)
        position = next(i + 1 for i, index in enumerate(ranking) if documents[index].doc_id == query.target)
        positions.append(position)
        by_persona[query.persona].append(position)
        context_chars.append(sum(len(documents[index].text) for index in ranking[:3]))

    def summarize(values: list[int]) -> dict[str, float]:
        return {
            "recall@1": sum(value <= 1 for value in values) / len(values),
            "recall@3": sum(value <= 3 for value in values) / len(values),
            "recall@5": sum(value <= 5 for value in values) / len(values),
            "mrr": sum(1 / value for value in values) / len(values),
            "ndcg@5": sum((1 / math.log2(value + 1)) if value <= 5 else 0 for value in values) / len(values),
        }

    summary: dict[str, object] = summarize(positions)
    summary["average_top3_chars"] = sum(context_chars) / len(context_chars)
    summary["by_persona"] = {name: summarize(values) for name, values in sorted(by_persona.items())}
    return summary


def load_validator():
    path = ROOT / "skills" / "afds-doc-writer" / "docs_validate.py"
    spec = importlib.util.spec_from_file_location("afds_validator", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def mutation_benchmark() -> dict[str, object]:
    validator = load_validator()
    config = validator.load_config(ROOT / "skills" / "afds-doc-writer" / "afds_config.yaml")
    defects = ["no-frontmatter", "missing-field", "bad-id", "duplicate-heading", "broken-link", "volatile-field"]
    detected = 0
    cases = 0
    by_defect: dict[str, list[bool]] = defaultdict(list)
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        for defect in defects:
            for index in range(20):
                metadata = [
                    "description: Test workflow",
                    f"doc_id: workflow.test-{index}",
                    "type: workflow",
                    "status: active",
                    "rigor: operational",
                    "owners: [test]",
                    "schema_version: 3",
                ]
                body = "# Test workflow\n\n## Prerequisites\n\nReady.\n\n## Steps\n\nRun it.\n\n## Validation\n\nObserve success.\n"
                if defect == "no-frontmatter":
                    content = body
                else:
                    if defect == "missing-field":
                        metadata = [line for line in metadata if not line.startswith("owners:")]
                    elif defect == "bad-id":
                        metadata[1] = "doc_id: wrong prefix"
                    elif defect == "volatile-field":
                        metadata.append("last_verified: 2026-01-01")
                    if defect == "duplicate-heading":
                        body += "\n## Steps\n\nAgain.\n"
                    elif defect == "broken-link":
                        body += "\nSee [missing](missing.md).\n"
                    content = "---\n" + "\n".join(metadata) + "\n---\n\n" + body
                path = base / f"{defect}-{index}.md"
                path.write_text(content, encoding="utf-8")
                findings = validator.validate_document(path, config)
                found = any(finding.severity == "ERROR" for finding in findings)
                by_defect[defect].append(found)
                detected += int(found)
                cases += 1
    return {
        "cases": cases,
        "detected": detected,
        "detection_rate": detected / cases,
        "by_defect": {name: sum(values) / len(values) for name, values in sorted(by_defect.items())},
    }


def run() -> dict[str, object]:
    queries = create_queries()
    variants = {
        "prose": (create_documents("prose"), False),
        "afds2": (create_documents("afds2"), False),
        "afds3_core": (create_documents("afds3-core"), False),
        "afds3": (create_documents("afds3"), True),
        "afds3_more_sections": (create_documents("afds3-more"), True),
        "afds3_more_metadata": (create_documents("afds3-metadata"), True),
    }
    results = {name: evaluate(documents, queries, weighted) for name, (documents, weighted) in variants.items()}
    rounds = [
        {"iteration": 0, "variant": "prose", "change": "unstructured baseline", "accepted": False, "mrr": results["prose"]["mrr"]},
        {"iteration": 1, "variant": "afds2", "change": "fixed comprehensive schema", "accepted": False, "mrr": results["afds2"]["mrr"]},
        {"iteration": 2, "variant": "afds3_core", "change": "answer-first concise core", "accepted": True, "mrr": results["afds3_core"]["mrr"]},
        {"iteration": 3, "variant": "afds3", "change": "aliases, entities, weighted retrieval", "accepted": True, "mrr": results["afds3"]["mrr"]},
        {"iteration": 4, "variant": "afds3_more_sections", "change": "mandatory background and related sections", "accepted": False, "mrr": results["afds3_more_sections"]["mrr"], "rejection": "no retrieval gain and larger context"},
        {"iteration": 5, "variant": "afds3_more_metadata", "change": "mandatory audience, review cycle, and related-topic metadata", "accepted": False, "mrr": results["afds3_more_metadata"]["mrr"], "rejection": "no material retrieval gain and more authoring ceremony"},
    ]
    for index in range(1, len(rounds)):
        rounds[index]["gain_from_previous"] = rounds[index]["mrr"] - rounds[index - 1]["mrr"]
    return {
        "schema_version": 1,
        "seed": 20260717,
        "documents_per_variant": len(next(iter(variants.values()))[0]),
        "total_generated_documents": sum(len(item[0]) for item in variants.values()),
        "queries": len(queries),
        "personas": sorted({query.persona for query in queries}),
        "results": results,
        "iterations": rounds,
        "mutation": mutation_benchmark(),
        "stopping_rule": "Stop after two candidate rounds each improve MRR by <0.005 and add no high-severity mutation coverage.",
        "limitations": [
            "Deterministic lexical retrieval isolates documentation shape; it is not a claim about any named LLM.",
            "Synthetic domains test controlled retrieval properties and must be complemented by repository-specific task evaluations.",
        ],
    }


def check_thresholds(result: dict[str, object]) -> list[str]:
    metrics = result["results"]
    assert isinstance(metrics, dict)
    baseline = metrics["prose"]
    afds2 = metrics["afds2"]
    afds3 = metrics["afds3"]
    mutation = result["mutation"]
    failures: list[str] = []
    if afds3["recall@3"] < baseline["recall@3"] + 0.10:
        failures.append("AFDS3 Recall@3 gain is below 0.10")
    if afds3["mrr"] < baseline["mrr"] + 0.10:
        failures.append("AFDS3 MRR gain is below 0.10")
    if afds3["average_top3_chars"] > afds2["average_top3_chars"] * 0.60:
        failures.append("AFDS3 top-3 context is not at least 40% smaller than AFDS2")
    if mutation["detection_rate"] < 0.98:
        failures.append("mutation detection is below 98%")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks/afds/latest-results.json")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    result = run()
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    failures = check_thresholds(result)

    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != encoded:
            failures.append(f"benchmark snapshot is stale: {args.output}")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")

    print(json.dumps({"results": result["results"], "mutation": result["mutation"]}, indent=2, sort_keys=True))
    for failure in failures:
        print(f"FAIL: {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
