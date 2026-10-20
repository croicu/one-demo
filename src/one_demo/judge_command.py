"""`one-demo judge`: apply one lesson to one piece of code. The model supplies the condition
checks with line citations; the verdict is derived from them by the lesson's Decision rules."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .contracts import ModelClient
from .diagnostics import Logger
from .errors import TaskError
from .judge_types import Citation, ConditionCheck, JudgeVerdict, SourceFile
from .lesson import STATE_UNKNOWN, Lesson
from .model_client import CATEGORY_MODEL
from .model_types import ChatMessage, ChatReply

DEFAULT_PROMPT_PATH = Path("prompts/judge_prompt.md")
CONTEXT_REFUSAL_FRACTION = 0.95

_STATE_PATTERN = re.compile(r"^\s*(holds|fails|unknown)\b", re.IGNORECASE)


class JudgeCommand:
    def __init__(self, client: ModelClient, model: str, prompt_template: str, temperature: float | None = None):
        self._client = client
        self._model = model
        self._prompt_template = prompt_template
        self._temperature = temperature

    @staticmethod
    def parse_source_file(argument: str) -> SourceFile:
        """'path' shows the file under its own name; 'path=name' shows it as 'name', so a file
        name can't hint at the answer."""
        path, separator, shown_name = argument.rpartition("=")
        if not separator:
            return SourceFile(path=argument, shown_name=Path(argument).name)
        if not path or not shown_name:
            raise TaskError(f"Bad file argument '{argument}': expected <path> or <path>=<shown name>.")
        return SourceFile(path=path, shown_name=shown_name)

    def run(self, lesson: Lesson, subject: str, files: list[SourceFile]) -> JudgeVerdict:
        lines_by_name = self._read_files(files)
        prompt = self.build_prompt(lesson, subject, files, lines_by_name)

        Logger.info(f"judge: {subject} against {lesson.lesson_id} with {self._model}.", CATEGORY_MODEL)
        started = time.perf_counter()
        reply = self._client.chat(self._model, [ChatMessage("user", prompt)], temperature=self._temperature, json_mode=True)
        seconds = time.perf_counter() - started

        self._refuse_if_prompt_was_cut(reply)
        payload = self._parse_reply(reply.content)
        checks, states, missing_checks = self._read_checks(payload, lesson)
        evidence, bad_citations = self._resolve_citations(payload.get("evidence"), lines_by_name)
        verdict, conditions = lesson.decide(states)

        if bad_citations:
            Logger.warning(
                f"judge: {len(bad_citations)} citation(s) don't point at a line in the files shown: {bad_citations}",
                CATEGORY_MODEL,
            )
        if missing_checks:
            Logger.warning(f"judge: the model left out checks {missing_checks}; counted as unknown.", CATEGORY_MODEL)
        Logger.info(f"judge: {verdict} ({', '.join(conditions)}) in {seconds:.1f}s.", CATEGORY_MODEL)

        return JudgeVerdict(
            lesson=lesson.lesson_id,
            subject=subject,
            verdict=verdict,
            conditions=conditions,
            checks=checks,
            evidence=evidence,
            bad_citations=bad_citations,
            reason=str(payload.get("reason", "")),
            model_verdict=str(payload.get("verdict", "")),
            model=reply.model,
            seconds=round(seconds, 1),
            prompt_tokens=reply.prompt_tokens,
            completion_tokens=reply.completion_tokens,
            missing_checks=missing_checks,
        )

    def build_prompt(self, lesson: Lesson, subject: str, files: list[SourceFile], lines_by_name: dict[str, list[str]]) -> str:
        rendered_files = []
        for source in files:
            numbered = []
            line_number = 1
            for line in lines_by_name[source.shown_name]:
                numbered.append(f"{line_number:>3} | {line}")
                line_number += 1
            body = "\n".join(numbered)
            rendered_files.append(f"## File: {source.shown_name}\n\n```csharp\n{body}\n```")

        conditions = sorted(lesson.checked_conditions())
        schema_lines = []
        for index, condition in enumerate(conditions):
            example = "holds|fails|unknown: <file name>:<line number> and why" if index == 0 else "..."
            separator = "," if index < len(conditions) - 1 else ""
            schema_lines.append(f'    "{condition}": "{example}"{separator}')

        prompt = self._prompt_template.replace("{{lesson}}", lesson.judge_text or lesson.text)
        prompt = prompt.replace("{{lesson_id}}", lesson.lesson_id)
        prompt = prompt.replace("{{subject}}", subject)
        prompt = prompt.replace("{{conditions}}", ", ".join(conditions))
        prompt = prompt.replace("{{checks_schema}}", "\n".join(schema_lines))
        prompt = prompt.replace("{{files}}", "\n\n".join(rendered_files))
        return prompt

    @staticmethod
    def _read_files(files: list[SourceFile]) -> dict[str, list[str]]:
        if not files:
            raise TaskError("No files to judge.")
        lines_by_name: dict[str, list[str]] = {}
        for source in files:
            path = Path(source.path)
            if not path.exists():
                raise TaskError(f"File not found: {source.path}")
            if source.shown_name in lines_by_name:
                raise TaskError(f"Two files are shown under the same name '{source.shown_name}'.")
            lines_by_name[source.shown_name] = path.read_text(encoding="utf-8").splitlines()
        return lines_by_name

    @staticmethod
    def _refuse_if_prompt_was_cut(reply: ChatReply) -> None:
        """A server out of context cuts the start of the prompt, which is where the lesson is, and
        still answers. Usage that reaches the context limit is the only trace of that, and a verdict
        on a lesson the model couldn't see must not be returned."""
        if reply.context_tokens is None:
            return
        used = reply.prompt_tokens + reply.completion_tokens
        if used >= reply.context_tokens * CONTEXT_REFUSAL_FRACTION:
            raise TaskError(
                f"The prompt and reply used {used} of {reply.model}'s {reply.context_tokens}-token context "
                f"({reply.prompt_tokens} prompt + {reply.completion_tokens} reply), so the start of the "
                "prompt (the lesson) was probably cut off. No verdict. Raise the provider's context size "
                "or shorten the input."
            )

    @staticmethod
    def _parse_reply(content: str) -> dict:
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as e:
            raise TaskError(f"The model's reply is not JSON: {content[:300]!r}") from e
        if not isinstance(payload, dict):
            raise TaskError(f"The model's reply is JSON but not an object: {content[:300]!r}")
        if not isinstance(payload.get("checks"), dict):
            raise TaskError(f"The model's reply has no 'checks' object: {content[:300]!r}")
        return payload

    @staticmethod
    def _read_checks(payload: dict, lesson: Lesson) -> tuple[list[ConditionCheck], dict[str, str], list[str]]:
        raw_checks = payload["checks"]
        checks = []
        states: dict[str, str] = {}
        missing = []
        for condition in lesson.checked_conditions():
            if condition not in raw_checks:
                missing.append(condition)
                states[condition] = STATE_UNKNOWN
                continue
            text = str(raw_checks[condition])
            match = _STATE_PATTERN.match(text)
            state = match.group(1).lower() if match else STATE_UNKNOWN
            states[condition] = state
            checks.append(ConditionCheck(condition=condition, state=state, text=text))
        return checks, states, missing

    @staticmethod
    def _resolve_citations(evidence: object, lines_by_name: dict[str, list[str]]) -> tuple[list[Citation], list[str]]:
        """Each citation must be '<shown name>:<line>' pointing at a real line; the others are
        returned as bad citations instead of being trusted."""
        resolved = []
        bad = []
        if not isinstance(evidence, list):
            return resolved, bad
        for item in evidence:
            reference = str(item)
            name, _, line_range = reference.rpartition(":")
            name = JudgeCommand._shown_name_for(name, lines_by_name)
            reference = f"{name}:{line_range}"
            lines = lines_by_name.get(name)
            first, last = JudgeCommand._parse_line_range(line_range)
            if lines is None or first is None or last is None or not 1 <= first <= last <= len(lines):
                bad.append(reference)
                continue
            texts = []
            for line in lines[first - 1 : last]:
                texts.append(line.strip())
            resolved.append(Citation(reference=reference, first_line=first, last_line=last, line_text="\n".join(texts)))
        return resolved, bad

    @staticmethod
    def _shown_name_for(name: str, lines_by_name: dict[str, list[str]]) -> str:
        """Models sometimes cite 'Job.cs' for a file shown as 'src/Jobs/Job.cs'. A base name that matches
        exactly one shown file is read as that file; anything else is returned unchanged."""
        if name in lines_by_name:
            return name
        matches = []
        for shown_name in lines_by_name:
            if shown_name.endswith("/" + name):
                matches.append(shown_name)
        if len(matches) == 1:
            return matches[0]
        return name

    @staticmethod
    def _parse_line_range(text: str) -> tuple[int | None, int | None]:
        """'12' is line 12; '12-14' is lines 12 to 14. Anything else is not a line reference."""
        start, separator, end = text.partition("-")
        if not separator:
            end = start
        if not start.strip().isdigit() or not end.strip().isdigit():
            return None, None
        return int(start), int(end)
