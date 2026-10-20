"""`one-demo learn <incident packet>`: the teacher. Reads a saved incident (description and fix),
asks a model to draft a lesson in the lesson format, writes it with its tests to lessons/drafts/, and
runs deterministic checks on the draft. Never fetches anything live."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .candidates import CandidateFinder
from .contracts import ModelClient
from .diagnostics import Logger
from .errors import TaskError
from .judge_types import SourceFile
from .lesson import Lesson
from .lesson_tests import EXPECT_FLAG, LessonTest, LessonTests
from .model_client import CATEGORY_MODEL
from .model_types import ChatMessage

CATEGORY_LEARN = "learn"
_ID_PATTERN = re.compile(r"^\s*-\s*\*\*Id:\*\*\s*`(?P<id>[a-z0-9][a-z0-9-]*)`", re.MULTILINE)
_FENCE_PATTERN = re.compile(r"^```(?:markdown|md)?\s*\n(?P<body>.*)\n```\s*$", re.DOTALL)


@dataclass
class LearnResult:
    lesson_path: Path
    tests_path: Path
    failures: list[str] = field(default_factory=list)
    previous_path: Path | None = None


class LearnCommand:
    def __init__(
        self,
        client: ModelClient,
        model: str,
        prompt_template: str,
        temperature: float | None = None,
        revise_template: str = "",
    ):
        self._revise_template = revise_template
        self._client = client
        self._model = model
        self._prompt_template = prompt_template
        self._temperature = temperature

    def run(self, packet: Path, drafts_dir: Path) -> LearnResult:
        if not (packet / "incident.json").exists():
            raise TaskError(f"Not an incident packet: {packet} has no incident.json.")
        incident = json.loads((packet / "incident.json").read_text(encoding="utf-8"))
        prompt = self._prompt_template.replace("{{incident}}", (packet / "incident.md").read_text(encoding="utf-8"))
        prompt = prompt.replace("{{diff}}", (packet / "fix.diff").read_text(encoding="utf-8"))

        Logger.info(f"learn: drafting a lesson from {incident['title']} with {self._model}.", CATEGORY_LEARN)
        reply = self._client.chat(self._model, [ChatMessage("user", prompt)], temperature=self._temperature)
        Logger.info(
            f"learn: draft received ({reply.prompt_tokens} prompt + {reply.completion_tokens} completion tokens).",
            CATEGORY_MODEL,
        )

        text = self._clean(reply.content)
        lesson_id = self._lesson_id(text, packet)
        text = self._with_incident_line(text, incident)

        drafts_dir.mkdir(parents=True, exist_ok=True)
        lesson_path = drafts_dir / f"{lesson_id}.md"
        lesson_path.write_text(text, encoding="utf-8")
        tests_path = LessonTests.path_for(lesson_path)
        tests = self._tests_from_labels(packet)
        LessonTests.save(tests_path, tests, packet=packet.as_posix())

        failures = self.check(lesson_path, tests)
        if failures:
            lesson_path.write_text(self._with_failures(text, failures), encoding="utf-8")
            Logger.warning(f"learn: the draft fails {len(failures)} check(s); see the top of {lesson_path}.", CATEGORY_LEARN)
        else:
            Logger.info(f"learn: draft {lesson_path} passes its checks.", CATEGORY_LEARN)
        return LearnResult(lesson_path=lesson_path, tests_path=tests_path, failures=failures)

    def revise(self, draft: Path) -> LearnResult:
        """Rewrites a draft that failed its tests: the teacher gets the incident again, its own draft, and
        the examples it got wrong with the judge's reasoning. The previous version is kept in
        <drafts>/history/, which scans don't read."""
        if not draft.exists():
            raise TaskError(f"Draft not found: {draft}")
        tests_path = LessonTests.path_for(draft)
        packet_name = LessonTests.packet_for(tests_path)
        if not packet_name:
            raise TaskError(f"{tests_path} doesn't say which incident packet the draft came from; can't revise it.")
        packet = Path(packet_name)
        results_path = LessonTests.results_path_for(draft)
        failures = LessonTests.load_failures(results_path)
        if not failures:
            raise TaskError("The draft's last test run had no failures: nothing to revise. Approve it.")
        if not self._revise_template:
            raise TaskError("No revise prompt was given.")

        incident = json.loads((packet / "incident.json").read_text(encoding="utf-8"))
        current = self._without_failure_banner(draft.read_text(encoding="utf-8"))
        prompt = self._revise_template.replace("{{incident}}", (packet / "incident.md").read_text(encoding="utf-8"))
        prompt = prompt.replace("{{diff}}", (packet / "fix.diff").read_text(encoding="utf-8"))
        prompt = prompt.replace("{{draft}}", current)
        prompt = prompt.replace("{{failures}}", self._describe_failures(failures))

        Logger.info(f"learn: revising {draft.name} for {len(failures)} failed test(s) with {self._model}.", CATEGORY_LEARN)
        reply = self._client.chat(self._model, [ChatMessage("user", prompt)], temperature=self._temperature)
        text = self._with_incident_line(self._clean(reply.content), incident)

        backup = self._next_history_path(draft)
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(current, encoding="utf-8")
        draft.write_text(text, encoding="utf-8")
        results_path.unlink()

        check_failures = self.check(draft, LessonTests.load(tests_path))
        if check_failures:
            draft.write_text(self._with_failures(text, check_failures), encoding="utf-8")
        Logger.info(f"learn: revised {draft.name}; the previous version is {backup}.", CATEGORY_LEARN)
        return LearnResult(lesson_path=draft, tests_path=tests_path, failures=check_failures, previous_path=backup)

    @staticmethod
    def _describe_failures(failures: list[dict]) -> str:
        lines = []
        for failure in failures:
            lines.append(
                f"- **{failure['name']}**: expected `{failure['expected']}`, the lesson gave `{failure['actual']}`. The judge's reasoning: {failure['detail']}"
            )
        return "\n".join(lines)

    @staticmethod
    def _without_failure_banner(text: str) -> str:
        if not text.startswith("> **The teacher's checks failed"):
            return text
        lines = text.splitlines(keepends=True)
        index = 0
        while index < len(lines) and lines[index].startswith(">"):
            index += 1
        return "".join(lines[index:]).lstrip("\n")

    @staticmethod
    def _next_history_path(draft: Path) -> Path:
        history = draft.parent / "history"
        version = 1
        while (history / f"{draft.stem}.v{version}.md").exists():
            version += 1
        return history / f"{draft.stem}.v{version}.md"

    @staticmethod
    def check(lesson_path: Path, tests: list[LessonTest]) -> list[str]:
        """Deterministic checks a draft must pass before anyone reviews it: it parses, its Decision ends in
        'otherwise', it cites its incident, its Candidates patterns compile, and they select every method
        the incident itself shows failing."""
        try:
            lesson = Lesson.load(lesson_path)
        except TaskError as error:
            return [str(error)]
        failures = []
        if lesson.rules[-1].condition is not None:
            failures.append("The Decision section's last rule isn't 'otherwise → ...'.")
        if not lesson.incident_url:
            failures.append("The Source section has no '**Incident:** [title](url)' line.")
        if not lesson.candidate_patterns:
            failures.append("The Candidates section has no patterns, so the lesson can't select any code.")
        finder = CandidateFinder()
        for test in tests:
            if test.source == "incident" and test.expected == EXPECT_FLAG and lesson.candidate_patterns:
                if not LessonTests.is_selected(lesson, test, finder):
                    failures.append(f"The Candidates patterns don't select {test.subject}, which the incident shows failing.")
        return failures

    @staticmethod
    def _clean(content: str) -> str:
        text = content.strip()
        fenced = _FENCE_PATTERN.match(text)
        if fenced is not None:
            text = fenced.group("body").strip()
        return text + "\n"

    @staticmethod
    def _lesson_id(text: str, packet: Path) -> str:
        match = _ID_PATTERN.search(text)
        if match is not None:
            return match.group("id")
        return packet.name

    @staticmethod
    def _with_incident_line(text: str, incident: dict) -> str:
        """The incident link is a fact from the packet, not something to trust the model with: it is
        written into the Source section deterministically."""
        line = f"**Incident:** [{incident['title']}]({incident['url']}) ([diff]({incident['diff_url']}))"
        if "## Source" not in text:
            return text.rstrip() + f"\n\n## Source\n\n{line}\n"
        head, _, tail = text.partition("## Source")
        if "**Incident:**" in tail:
            return text
        return head + "## Source\n\n" + line + "\n\n" + tail.lstrip("\n")

    @staticmethod
    def _with_failures(text: str, failures: list[str]) -> str:
        lines = ["> **The teacher's checks failed. Fix the lesson before review:**", ">"]
        for failure in failures:
            lines.append(f"> - {failure}")
        return "\n".join(lines) + "\n\n" + text

    @staticmethod
    def _tests_from_labels(packet: Path) -> list[LessonTest]:
        """The packet's labeled examples, with paths made relative to the working folder."""
        labels_path = packet / "labels.json"
        if not labels_path.exists():
            return []
        payload = json.loads(labels_path.read_text(encoding="utf-8"))
        tests = []
        for entry in payload.get("tests", []):
            files = []
            for source in entry["files"]:
                files.append(SourceFile(path=(packet / source["path"]).as_posix(), shown_name=source["showAs"]))
            tests.append(
                LessonTest(
                    name=entry["name"],
                    source=entry.get("source", ""),
                    subject=entry["subject"],
                    expected=entry["expected"],
                    files=files,
                )
            )
        return tests
