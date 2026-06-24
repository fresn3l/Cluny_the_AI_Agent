"""Golden-question evaluation harness for regression testing RAG quality."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from cluny.config import Settings, find_repo_root
from cluny.query import rag_answer, retrieve


@dataclass
class EvalCase:
    question: str
    expect_sources: list[str] | None = None
    expect_refusal: bool = False
    k: int = 5
    skip_when_empty: bool = False


@dataclass
class EvalCaseResult:
    question: str
    answer: str
    retrieved_labels: list[str]
    retrieved_paths: list[str]
    sources_hit: bool
    refusal_ok: bool | None
    empty_index: bool
    passed: bool
    latency_ms: float


@dataclass
class EvalReport:
    run_at: str
    cases: list[EvalCaseResult]
    passed: int
    total: int
    retrieval_hit_rate: float
    refusal_rate: float | None
    avg_latency_ms: float

    def to_dict(self) -> dict:
        return {
            "run_at": self.run_at,
            "passed": self.passed,
            "total": self.total,
            "retrieval_hit_rate": self.retrieval_hit_rate,
            "refusal_rate": self.refusal_rate,
            "avg_latency_ms": self.avg_latency_ms,
            "cases": [asdict(c) for c in self.cases],
        }


def default_golden_path() -> Path:
    root = find_repo_root()
    if root is not None:
        p = root / "eval" / "golden.yaml"
        if p.is_file():
            return p
    return Path("eval/golden.yaml")


def default_report_path() -> Path:
    root = find_repo_root() or Path.cwd()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return root / "eval" / "reports" / f"{stamp}.json"


def load_cases(path: Path) -> list[EvalCase]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"Expected a list in {path}")
    cases: list[EvalCase] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        cases.append(
            EvalCase(
                question=str(item["question"]),
                expect_sources=item.get("expect_sources"),
                expect_refusal=bool(item.get("expect_refusal", False)),
                k=int(item.get("k", 5)),
                skip_when_empty=bool(item.get("skip_when_empty", False)),
            )
        )
    return cases


def _source_hit(retrieved_paths: list[str], expect_sources: list[str]) -> bool:
    lowered = [p.lower() for p in retrieved_paths]
    for expected in expect_sources:
        e = expected.lower()
        if any(e in p for p in lowered):
            return True
    return False


def _refusal_ok(answer: str) -> bool:
    lower = answer.lower()
    phrases = (
        "do not have",
        "don't have",
        "not in the",
        "no information",
        "cannot find",
        "not indexed",
        "don't know",
    )
    return any(p in lower for p in phrases)


def run_eval(
    cases: list[EvalCase],
    *,
    settings: Settings | None = None,
    skip_llm: bool = False,
    fts_only: bool = False,
) -> EvalReport:
    settings = settings or Settings.from_env()
    results: list[EvalCaseResult] = []
    passed = 0
    retrieval_checks = 0
    retrieval_hits = 0
    refusal_cases = 0
    refusal_ok_count = 0
    latencies: list[float] = []

    for case in cases:
        t0 = time.perf_counter()
        chunks = retrieve(case.question, k=case.k, settings=settings, fts_only=fts_only)
        labels = [c.label for c in chunks]
        paths = [c.doc_path or "" for c in chunks]
        index_empty = not chunks

        sources_hit = True
        if case.expect_sources is not None:
            retrieval_checks += 1
            if case.expect_sources:
                sources_hit = _source_hit(paths, case.expect_sources)
            else:
                sources_hit = bool(chunks)
            if sources_hit:
                retrieval_hits += 1

        if case.skip_when_empty and index_empty:
            ok = True
            answer = "(skipped: empty index)"
            empty_index = True
            refusal_ok = None
        elif skip_llm:
            answer = "(skipped)"
            empty_index = not chunks
            refusal_ok = None
            ok = sources_hit if case.expect_sources is not None else True
        else:
            result = rag_answer(case.question, k=case.k, settings=settings)
            answer = result.answer
            empty_index = result.empty_index
            if case.expect_refusal:
                refusal_cases += 1
                refusal_ok = _refusal_ok(answer)
                if refusal_ok:
                    refusal_ok_count += 1
                ok = refusal_ok
            else:
                refusal_ok = None
                ok = sources_hit and not empty_index

        latency_ms = (time.perf_counter() - t0) * 1000
        latencies.append(latency_ms)

        if ok:
            passed += 1

        results.append(
            EvalCaseResult(
                question=case.question,
                answer=answer,
                retrieved_labels=labels,
                retrieved_paths=paths,
                sources_hit=sources_hit,
                refusal_ok=refusal_ok,
                empty_index=empty_index,
                passed=ok,
                latency_ms=round(latency_ms, 2),
            )
        )

    hit_rate = retrieval_hits / retrieval_checks if retrieval_checks else 1.0
    refusal_rate = refusal_ok_count / refusal_cases if refusal_cases else None
    avg_lat = sum(latencies) / len(latencies) if latencies else 0.0

    return EvalReport(
        run_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        cases=results,
        passed=passed,
        total=len(cases),
        retrieval_hit_rate=round(hit_rate, 4),
        refusal_rate=round(refusal_rate, 4) if refusal_rate is not None else None,
        avg_latency_ms=round(avg_lat, 2),
    )


def write_report(report: EvalReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
