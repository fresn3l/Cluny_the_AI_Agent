"""Golden-question evaluation harness for regression testing RAG quality."""

from __future__ import annotations

import json
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


@dataclass
class EvalReport:
    run_at: str
    cases: list[EvalCaseResult]
    passed: int
    total: int

    def to_dict(self) -> dict:
        return {
            "run_at": self.run_at,
            "passed": self.passed,
            "total": self.total,
            "cases": [asdict(c) for c in self.cases],
        }


def default_golden_path() -> Path:
    root = find_repo_root()
    if root is not None:
        p = root / "eval" / "golden.yaml"
        if p.is_file():
            return p
    return Path("eval/golden.yaml")


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
) -> EvalReport:
    settings = settings or Settings.from_env()
    results: list[EvalCaseResult] = []
    passed = 0

    for case in cases:
        chunks = retrieve(case.question, k=case.k, settings=settings)
        labels = [c.label for c in chunks]
        paths = [c.doc_path or "" for c in chunks]

        sources_hit = True
        if case.expect_sources:
            sources_hit = _source_hit(paths, case.expect_sources)

        if skip_llm:
            answer = "(skipped)"
            empty_index = not chunks
            refusal_ok = None
            ok = sources_hit
        else:
            result = rag_answer(case.question, k=case.k, settings=settings)
            answer = result.answer
            empty_index = result.empty_index
            if case.expect_refusal:
                refusal_ok = _refusal_ok(answer)
                ok = refusal_ok
            else:
                refusal_ok = None
                ok = sources_hit and not empty_index

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
            )
        )

    return EvalReport(
        run_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        cases=results,
        passed=passed,
        total=len(cases),
    )


def write_report(report: EvalReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
