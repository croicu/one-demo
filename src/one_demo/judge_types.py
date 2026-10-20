"""Data produced by judging one piece of code against one lesson."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SourceFile:
    path: str
    shown_name: str


@dataclass
class ConditionCheck:
    condition: str
    state: str
    text: str


@dataclass
class Citation:
    reference: str
    first_line: int
    last_line: int
    line_text: str


@dataclass
class JudgeVerdict:
    lesson: str
    subject: str
    verdict: str
    conditions: list[str]
    checks: list[ConditionCheck]
    evidence: list[Citation]
    bad_citations: list[str]
    reason: str
    model_verdict: str
    model: str
    seconds: float
    prompt_tokens: int
    completion_tokens: int
    missing_checks: list[str] = field(default_factory=list)
