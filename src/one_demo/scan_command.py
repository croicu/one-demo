"""`one-demo scan <root>`: find retry candidates in a repository and judge each one against every
approved lesson. Silent when there are no lessons: the scanner only speaks when it can cite an
incident."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .candidates import CATEGORY_SCAN, CandidateFinder
from .diagnostics import Logger
from .errors import AppError, TaskError
from .judge_command import JudgeCommand
from .lesson import Lesson
from .scan_types import Candidate, Finding

DEFAULT_PARALLEL = 4


class ScanCommand:
    def __init__(self, judge: JudgeCommand, finder: CandidateFinder | None = None, parallel: int = DEFAULT_PARALLEL):
        """Judgments are independent model calls, so up to `parallel` run at once: the scan takes about as
        long as its slowest judgment, not the sum of them. Findings keep the candidates' order."""
        self._judge = judge
        self._finder = finder if finder is not None else CandidateFinder()
        self._parallel = max(1, parallel)

    @staticmethod
    def load_lessons(lessons_dir: Path) -> list[Lesson]:
        """Every approved lesson: the .md files directly in lessons_dir. Drafts live in a subfolder and
        are not read."""
        if not lessons_dir.is_dir():
            return []
        lessons = []
        for path in sorted(lessons_dir.glob("*.md")):
            lessons.append(Lesson.load(path))
        return lessons

    def run(self, root: Path, lessons: list[Lesson]) -> list[Finding]:
        if not root.is_dir():
            raise TaskError(f"Nothing to scan: {root} is not a folder.")
        if not lessons:
            Logger.info("scan: no approved lessons, nothing to check.", CATEGORY_SCAN)
            return []
        pairs = []
        for lesson in lessons:
            if not lesson.candidate_patterns:
                Logger.warning(
                    f"scan: lesson {lesson.lesson_id} has no '## Candidates' patterns, so it can't select any code; skipped.",
                    CATEGORY_SCAN,
                )
                continue
            for candidate in self._finder.find(root, lesson.candidate_patterns, lesson.file_glob):
                pairs.append((lesson, candidate))
        Logger.info(f"scan: {len(pairs)} judgment(s), up to {self._parallel} at a time.", CATEGORY_SCAN)

        findings: list[Finding | None] = [None] * len(pairs)
        with ThreadPoolExecutor(max_workers=self._parallel) as pool:
            futures = {}
            for index, (lesson, candidate) in enumerate(pairs):
                futures[pool.submit(self._judge_one, lesson, candidate)] = index
            for future in as_completed(futures):
                findings[futures[future]] = future.result()

        ordered = []
        for finding in findings:
            if finding is not None:
                ordered.append(finding)
        return ordered

    def _judge_one(self, lesson: Lesson, candidate: Candidate) -> Finding:
        Logger.diagnostic(f"scan: judging {candidate.subject} against {lesson.lesson_id}", CATEGORY_SCAN)
        try:
            verdict = self._judge.run(lesson, candidate.subject, candidate.files)
        except AppError as error:
            Logger.warning(f"scan: could not judge {candidate.subject} against {lesson.lesson_id}: {error}", CATEGORY_SCAN)
            return Finding(
                candidate=candidate,
                lesson_id=lesson.lesson_id,
                incident_title=lesson.incident_title,
                incident_url=lesson.incident_url,
                verdict=None,
                error=str(error),
            )
        return Finding(
            candidate=candidate,
            lesson_id=lesson.lesson_id,
            incident_title=lesson.incident_title,
            incident_url=lesson.incident_url,
            verdict=verdict,
        )
