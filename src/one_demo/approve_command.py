"""`one-demo approve <draft>`: the gate to production. Runs the draft lesson's tests and moves the
lesson (and its tests) into the approved folder only if every test passes; otherwise the draft stays
in review and the command fails."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .candidates import CandidateFinder
from .diagnostics import Logger
from .errors import TaskError
from .judge_command import JudgeCommand
from .lesson import Lesson
from .lesson_tests import LessonTests, TestResult

CATEGORY_APPROVE = "approve"


@dataclass
class ApproveResult:
    lesson_id: str
    approved: bool
    results: list[TestResult] = field(default_factory=list)
    approved_path: Path | None = None


class ApproveCommand:
    def __init__(self, judge: JudgeCommand, finder: CandidateFinder | None = None):
        self._judge = judge
        self._finder = finder if finder is not None else CandidateFinder()

    def run(self, draft: Path, approved_dir: Path) -> ApproveResult:
        lesson = Lesson.load(draft)
        tests_path = LessonTests.path_for(draft)
        tests = LessonTests.load(tests_path)
        Logger.info(f"approve: running {len(tests)} test(s) for {lesson.lesson_id}.", CATEGORY_APPROVE)
        results = LessonTests.run(lesson, tests, self._judge, self._finder)

        failed = 0
        for result in results:
            if not result.passed:
                failed += 1
        results_path = LessonTests.results_path_for(draft)
        if failed:
            LessonTests.save_results(results_path, results)
            Logger.warning(
                f"approve: {lesson.lesson_id} failed {failed} of {len(results)} test(s); it stays in review.",
                CATEGORY_APPROVE,
            )
            return ApproveResult(lesson_id=lesson.lesson_id, approved=False, results=results)

        target = approved_dir / draft.name
        if target.exists():
            raise TaskError(f"An approved lesson with this name already exists: {target}")
        shutil.move(str(draft), str(target))
        shutil.move(str(tests_path), str(LessonTests.path_for(target)))
        if results_path.exists():
            results_path.unlink()
        Logger.info(f"approve: {lesson.lesson_id} passed all {len(results)} test(s) and is live.", CATEGORY_APPROVE)
        return ApproveResult(lesson_id=lesson.lesson_id, approved=True, results=results, approved_path=target)

    @staticmethod
    def report(result: ApproveResult) -> str:
        lines = []
        for test_result in result.results:
            mark = "pass" if test_result.passed else "FAIL"
            lines.append(f"{mark}  {test_result.test.name}: expected {test_result.test.expected}, got {test_result.actual}")
            if not test_result.passed:
                lines.append(f"      {test_result.detail}")
        passed = 0
        for test_result in result.results:
            if test_result.passed:
                passed += 1
        lines.append("")
        if result.approved:
            lines.append(f"APPROVED  {result.lesson_id}: {passed}/{len(result.results)} tests passed; now live in {result.approved_path}.")
        else:
            lines.append(f"NOT APPROVED  {result.lesson_id}: {passed}/{len(result.results)} tests passed. Fix the lesson (or the labels), then approve again.")
        return "\n".join(lines)
