"""Data produced by scanning a repository: the candidates found and the findings judged."""

from __future__ import annotations

from dataclasses import dataclass, field

from .judge_types import JudgeVerdict, SourceFile


@dataclass
class Candidate:
    """A method that retries: a loop that catches an exception and waits. The judge decides whether
    a lesson applies to it."""

    subject: str
    path: str
    line: int
    files: list[SourceFile] = field(default_factory=list)


@dataclass
class Finding:
    candidate: Candidate
    lesson_id: str
    incident_title: str | None
    incident_url: str | None
    verdict: JudgeVerdict | None
    error: str = ""
