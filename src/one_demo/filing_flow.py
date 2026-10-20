"""Files a scan's warnings in the repository they were found in, after showing them and asking."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .issue_filing import IssueFiler
from .lesson import Lesson
from .scan_types import Finding
from .source_repo import SourceRepo


def file_findings(
    findings: list[Finding],
    folder: Path,
    lessons: list[Lesson],
    filer: IssueFiler,
    confirm: Callable[[str], bool],
) -> list[str]:
    """Report lines for the console. Nothing is filed for a folder that isn't in a GitHub repo."""
    repo = SourceRepo.describe(folder)
    if repo is None:
        return [f"No issues filed: {folder} isn't in a git repository with a GitHub origin."]
    titles = {}
    for lesson in lessons:
        titles[lesson.lesson_id] = lesson.title
    result = filer.file(findings, repo, titles, confirm)
    lines = []
    for subject in result.already_open:
        lines.append(f"Already tracked (open issue): {subject}")
    if result.declined:
        lines.append("Filing declined: no issues filed.")
    for url in result.filed:
        lines.append(f"Filed: {url}")
    if not result.filed and not result.already_open and not result.declined:
        lines.append(f"No warnings to file in {repo.slug}.")
    return lines
