"""A lesson's tests: labeled examples (code with a known right verdict) that a lesson must get right
before it is approved. Stored next to the lesson as <id>.tests.json; paths are relative to the folder
the commands run from (the repository root)."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from .candidates import CATEGORY_SCAN, CandidateFinder
from .diagnostics import Logger
from .errors import AppError, TaskError
from .judge_command import JudgeCommand
from .judge_types import SourceFile
from .lesson import Lesson

TESTS_SUFFIX = ".tests.json"
RESULTS_SUFFIX = ".results.json"
EXPECT_FLAG = "flag"
EXPECT_CLEAR = "clear"


@dataclass
class LessonTest:
    name: str
    source: str
    subject: str
    expected: str
    files: list[SourceFile] = field(default_factory=list)


@dataclass
class TestResult:
    test: LessonTest
    passed: bool
    actual: str
    detail: str


class LessonTests:
    @staticmethod
    def path_for(lesson_path: Path) -> Path:
        return lesson_path.with_name(lesson_path.stem + TESTS_SUFFIX)

    @staticmethod
    def load(path: Path) -> list[LessonTest]:
        if not path.exists():
            raise TaskError(f"No tests for this lesson: {path} is missing.")
        payload = json.loads(path.read_text(encoding="utf-8"))
        tests = []
        for entry in payload.get("tests", []):
            files = []
            for source in entry["files"]:
                files.append(SourceFile(path=source["path"], shown_name=source["showAs"]))
            tests.append(
                LessonTest(
                    name=entry["name"],
                    source=entry.get("source", ""),
                    subject=entry["subject"],
                    expected=entry["expected"],
                    files=files,
                )
            )
        if not tests:
            raise TaskError(f"{path} lists no tests.")
        return tests

    @staticmethod
    def save(path: Path, tests: list[LessonTest], packet: str | None = None) -> None:
        """packet: the incident packet the lesson was learned from, so a revision can re-read it."""
        entries = []
        for test in tests:
            files = []
            for source in test.files:
                files.append({"path": source.path, "showAs": source.shown_name})
            entries.append({"name": test.name, "source": test.source, "subject": test.subject, "files": files, "expected": test.expected})
        payload: dict = {}
        if packet is not None:
            payload["packet"] = packet
        payload["tests"] = entries
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def packet_for(path: Path) -> str | None:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8")).get("packet")

    @staticmethod
    def results_path_for(lesson_path: Path) -> Path:
        return lesson_path.with_name(lesson_path.stem + RESULTS_SUFFIX)

    @staticmethod
    def save_results(path: Path, results: list[TestResult]) -> None:
        """The last test run, kept next to a draft that failed, so a revision knows what to fix."""
        entries = []
        for result in results:
            entries.append(
                {
                    "name": result.test.name,
                    "subject": result.test.subject,
                    "expected": result.test.expected,
                    "actual": result.actual,
                    "passed": result.passed,
                    "detail": result.detail,
                }
            )
        path.write_text(json.dumps({"results": entries}, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def load_failures(path: Path) -> list[dict]:
        if not path.exists():
            raise TaskError(f"No test results to revise from: {path} is missing. Run approve on the draft first.")
        failures = []
        for entry in json.loads(path.read_text(encoding="utf-8")).get("results", []):
            if not entry["passed"]:
                failures.append(entry)
        return failures

    @staticmethod
    def is_selected(lesson: Lesson, test: LessonTest, finder: CandidateFinder) -> bool:
        """Whether the lesson's own Candidates patterns pick the test's method out of its first file."""
        first = Path(test.files[0].path)
        candidates = finder.find(first.parent, lesson.candidate_patterns, first.name)
        for candidate in candidates:
            if candidate.subject == test.subject:
                return True
        return False

    @staticmethod
    def run(lesson: Lesson, tests: list[LessonTest], judge: JudgeCommand, finder: CandidateFinder, parallel: int = 4) -> list[TestResult]:
        """A test passes when the lesson reaches the expected verdict the way a scan would: its patterns
        must select the method, then the judge decides. An unselected method counts as cleared."""
        results: list[TestResult | None] = [None] * len(tests)
        with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
            futures = {}
            for index, test in enumerate(tests):
                futures[pool.submit(LessonTests._run_one, lesson, test, judge, finder)] = index
            for future in as_completed(futures):
                results[futures[future]] = future.result()
        ordered = []
        for result in results:
            if result is not None:
                ordered.append(result)
        return ordered

    @staticmethod
    def _run_one(lesson: Lesson, test: LessonTest, judge: JudgeCommand, finder: CandidateFinder) -> TestResult:
        Logger.diagnostic(f"test: {test.name}", CATEGORY_SCAN)
        if not LessonTests.is_selected(lesson, test, finder):
            passed = test.expected == EXPECT_CLEAR
            return TestResult(test, passed, EXPECT_CLEAR, "not selected by the lesson's Candidates patterns")
        try:
            verdict = judge.run(lesson, test.subject, test.files)
        except AppError as error:
            return TestResult(test, False, "error", str(error))
        conditions = ", ".join(verdict.conditions)
        return TestResult(test, verdict.verdict == test.expected, verdict.verdict, f"[{conditions}] {verdict.reason}")
