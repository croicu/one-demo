"""A lesson file (lessons/<id>.md) and the Decision rules that turn condition checks into a verdict."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .errors import TaskError

STATE_HOLDS = "holds"
STATE_FAILS = "fails"
STATE_UNKNOWN = "unknown"

_DECISION_HEADING = "## Decision"
_SOURCE_HEADING = "## Source"
_CANDIDATES_HEADING = "## Candidates"
_FILES_PATTERN = re.compile(r"^\s*-\s*Files:\s*`(?P<glob>[^`]+)`")
_CANDIDATE_PATTERN = re.compile(r"^\s*-\s*`(?P<pattern>[^`]+)`")
DEFAULT_FILE_GLOB = "*.cs"
_INCIDENT_PATTERN = re.compile(r"\*\*Incident:\*\*\s*\[(?P<title>[^\]]+)\]\((?P<url>[^)\s]+)\)")
_RULE_PATTERN = re.compile(
    r"^\s*\d+\.\s+(?:(?P<condition>\S+)\s+(?P<state>holds|fails)|otherwise)"
    r"\s+→\s+(?P<verdict>flag|clear)\s+\((?P<names>[^)]*)\)"
)


@dataclass
class DecisionRule:
    condition: str | None
    state: str | None
    verdict: str
    conditions: list[str]


@dataclass
class Lesson:
    lesson_id: str
    text: str
    rules: list[DecisionRule]
    incident_title: str | None = None
    incident_url: str | None = None
    candidate_patterns: list[str] = field(default_factory=list)
    file_glob: str = DEFAULT_FILE_GLOB
    judge_text: str = ""
    title: str = ""

    @classmethod
    def load(cls, path: Path) -> Lesson:
        if not path.exists():
            raise TaskError(f"Lesson file not found: {path}")
        text = path.read_text(encoding="utf-8")
        rules = cls._parse_rules(text)
        if not rules:
            raise TaskError(f"Lesson {path} has no '{_DECISION_HEADING}' section with numbered rules.")
        incident_title, incident_url = cls._parse_incident(text)
        patterns, file_glob = cls._parse_candidates(text, path)
        return cls(
            lesson_id=path.stem,
            text=text,
            rules=rules,
            incident_title=incident_title,
            incident_url=incident_url,
            candidate_patterns=patterns,
            file_glob=file_glob,
            judge_text=cls._without_section(text, _CANDIDATES_HEADING),
            title=cls._title(text, path.stem),
        )

    @staticmethod
    def _title(text: str, fallback: str) -> str:
        """The first '# ' heading, without a leading 'Lesson:'."""
        for line in text.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                if title.lower().startswith("lesson:"):
                    title = title[len("lesson:") :].strip()
                return title or fallback
        return fallback

    @staticmethod
    def _parse_candidates(text: str, path: Path) -> tuple[list[str], str]:
        """The '## Candidates' section: which files to read (`- Files: `*.cs``) and the patterns a method's
        body must all match to be judged. This is the lesson's own cheap query; the scanner itself knows
        no patterns."""
        patterns = []
        file_glob = DEFAULT_FILE_GLOB
        in_section = False
        for line in text.splitlines():
            if line.startswith("## "):
                in_section = line.strip() == _CANDIDATES_HEADING
                continue
            if not in_section:
                continue
            files = _FILES_PATTERN.match(line)
            if files is not None:
                file_glob = files.group("glob")
                continue
            candidate = _CANDIDATE_PATTERN.match(line)
            if candidate is None:
                continue
            try:
                re.compile(candidate.group("pattern"))
            except re.error as error:
                raise TaskError(f"Lesson {path}: candidate pattern {candidate.group('pattern')!r} is invalid: {error}")
            patterns.append(candidate.group("pattern"))
        return patterns, file_glob

    @staticmethod
    def _without_section(text: str, heading: str) -> str:
        """The lesson as the judge sees it: everything but the machinery section named by heading."""
        kept = []
        in_section = False
        for line in text.splitlines(keepends=True):
            if line.startswith("## "):
                in_section = line.strip() == heading
            if not in_section:
                kept.append(line)
        return "".join(kept)

    @staticmethod
    def _parse_incident(text: str) -> tuple[str | None, str | None]:
        """The first '**Incident:** [title](url)' in the '## Source' section: what every finding from
        this lesson cites."""
        in_section = False
        for line in text.splitlines():
            if line.startswith("## "):
                in_section = line.strip() == _SOURCE_HEADING
                continue
            if not in_section:
                continue
            match = _INCIDENT_PATTERN.search(line)
            if match is not None:
                return match.group("title"), match.group("url")
        return None, None

    @staticmethod
    def _parse_rules(text: str) -> list[DecisionRule]:
        rules = []
        in_section = False
        for line in text.splitlines():
            if line.startswith("## "):
                in_section = line.strip() == _DECISION_HEADING
                continue
            if not in_section:
                continue
            match = _RULE_PATTERN.match(line)
            if match is None:
                continue
            conditions = []
            for name in match.group("names").split(","):
                conditions.append(name.strip())
            rules.append(
                DecisionRule(
                    condition=match.group("condition"),
                    state=match.group("state"),
                    verdict=match.group("verdict"),
                    conditions=conditions,
                )
            )
        return rules

    def checked_conditions(self) -> list[str]:
        """The conditions the model must check, in the order the rules first name them."""
        names = []
        for rule in self.rules:
            if rule.condition is not None and rule.condition not in names:
                names.append(rule.condition)
        return names

    def decide(self, states: dict[str, str]) -> tuple[str, list[str]]:
        """Applies the rules in order; the first match decides. A missing or 'unknown' state never
        matches 'holds' or 'fails', so it falls through to later rules."""
        for rule in self.rules:
            if rule.condition is None:
                return rule.verdict, list(rule.conditions)
            if states.get(rule.condition, STATE_UNKNOWN) == rule.state:
                return rule.verdict, list(rule.conditions)
        raise TaskError(f"Lesson {self.lesson_id}: no Decision rule matched and there is no 'otherwise' rule.")
