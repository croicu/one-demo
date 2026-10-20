import json

import pytest

from one_demo.errors import TaskError
from one_demo.judge_command import JudgeCommand
from one_demo.lesson import Lesson
from one_demo.model_types import ChatReply

LESSON_TEXT = """# Lesson

## Decision

1. H3 holds → clear (H3)
2. D1 fails → clear (H1)
3. H2 holds → clear (H2)
4. D2 holds → flag (D1, D2)
5. otherwise → flag (D1, missing-fact)
"""

TEMPLATE = "LESSON:{{lesson}}\nID:{{lesson_id}}\nSUBJECT:{{subject}}\nFILES:\n{{files}}\n"


class FakeClient:
    def __init__(self, content):
        self.content = content
        self.calls = []

    def list_models(self):
        return []

    def chat(self, model, messages, temperature=None, json_mode=False):
        self.calls.append({"model": model, "messages": messages, "temperature": temperature, "json_mode": json_mode})
        return ChatReply(content=self.content, model=model, prompt_tokens=100, completion_tokens=20)


def _setup(tmp_path, reply_payload):
    lesson_path = tmp_path / "retry-lesson.md"
    lesson_path.write_text(LESSON_TEXT, encoding="utf-8")
    job = tmp_path / "Job.cs"
    job.write_text("class Job : Base\n{\n    Retry();\n}\n", encoding="utf-8")
    base = tmp_path / "Base.documented.cs"
    base.write_text("/// Runs as one replica.\nabstract class Base {}\n", encoding="utf-8")
    content = reply_payload if isinstance(reply_payload, str) else json.dumps(reply_payload)
    client = FakeClient(content)
    files = [
        JudgeCommand.parse_source_file(str(job)),
        JudgeCommand.parse_source_file(f"{base}=Base.cs"),
    ]
    return client, Lesson.load(lesson_path), files


def _reply(**overrides):
    payload = {
        "evidence": ["Job.cs:3", "Base.cs:1"],
        "checks": {
            "D1": "holds: Job.cs:3 calls a remote service",
            "D2": "unknown: nothing shows the instance count",
            "H2": "holds: Base.cs:1 says one replica",
            "H3": "fails: fixed delay",
        },
        "reason": "Documented as single instance.",
        "verdict": "flag",
        "citation": "retry-lesson",
    }
    payload.update(overrides)
    return payload


def test_parse_source_file_with_and_without_shown_name():
    plain = JudgeCommand.parse_source_file("targets/Job.cs")
    renamed = JudgeCommand.parse_source_file("targets/Base.documented.cs=Base.cs")

    assert (plain.path, plain.shown_name) == ("targets/Job.cs", "Job.cs")
    assert (renamed.path, renamed.shown_name) == ("targets/Base.documented.cs", "Base.cs")


def test_parse_source_file_rejects_empty_name():
    with pytest.raises(TaskError):
        JudgeCommand.parse_source_file("targets/Base.cs=")


def test_prompt_shows_numbered_lines_under_shown_names(tmp_path):
    client, lesson, files = _setup(tmp_path, _reply())

    JudgeCommand(client, "m", TEMPLATE).run(lesson, "Job.Run", files)

    call = client.calls[0]
    prompt = call["messages"][0].content
    assert "## File: Base.cs" in prompt
    assert "documented" not in prompt
    assert "  3 |     Retry();" in prompt
    assert "SUBJECT:Job.Run" in prompt
    assert "ID:retry-lesson" in prompt
    assert call["json_mode"] is True
    assert call["temperature"] is None


def test_temperature_is_passed_through_when_set(tmp_path):
    client, lesson, files = _setup(tmp_path, _reply())

    JudgeCommand(client, "m", TEMPLATE, temperature=0.0).run(lesson, "Job.Run", files)

    assert client.calls[0]["temperature"] == 0.0


def test_verdict_is_derived_from_checks_not_taken_from_model(tmp_path):
    client, lesson, files = _setup(tmp_path, _reply(verdict="flag"))

    verdict = JudgeCommand(client, "m", TEMPLATE).run(lesson, "Job.Run", files)

    assert verdict.verdict == "clear"
    assert verdict.conditions == ["H2"]
    assert verdict.model_verdict == "flag"


def test_citations_resolve_to_line_text_and_bad_ones_are_listed(tmp_path):
    client, lesson, files = _setup(tmp_path, _reply(evidence=["Job.cs:3", "Base.cs:1", "Job.cs:99", "Other.cs:1"]))

    verdict = JudgeCommand(client, "m", TEMPLATE).run(lesson, "Job.Run", files)

    assert verdict.evidence[0].line_text == "Retry();"
    assert verdict.evidence[1].line_text == "/// Runs as one replica."
    assert verdict.bad_citations == ["Job.cs:99", "Other.cs:1"]


def test_line_range_citations_resolve_and_bad_ranges_are_listed(tmp_path):
    client, lesson, files = _setup(tmp_path, _reply(evidence=["Job.cs:2-3", "Job.cs:3-9", "Job.cs:3-2", "Job.cs:a-b"]))

    verdict = JudgeCommand(client, "m", TEMPLATE).run(lesson, "Job.Run", files)

    assert len(verdict.evidence) == 1
    assert (verdict.evidence[0].first_line, verdict.evidence[0].last_line) == (2, 3)
    assert verdict.evidence[0].line_text == "{\nRetry();"
    assert verdict.bad_citations == ["Job.cs:3-9", "Job.cs:3-2", "Job.cs:a-b"]


def test_missing_check_counts_as_unknown(tmp_path):
    reply = _reply()
    del reply["checks"]["H2"]
    client, lesson, files = _setup(tmp_path, reply)

    verdict = JudgeCommand(client, "m", TEMPLATE).run(lesson, "Job.Run", files)

    assert verdict.missing_checks == ["H2"]
    assert verdict.verdict == "flag"
    assert verdict.conditions == ["D1", "missing-fact"]


def test_check_without_state_word_counts_as_unknown(tmp_path):
    reply = _reply()
    reply["checks"]["H2"] = "maybe: the comment is vague"
    client, lesson, files = _setup(tmp_path, reply)

    verdict = JudgeCommand(client, "m", TEMPLATE).run(lesson, "Job.Run", files)

    h2 = None
    for check in verdict.checks:
        if check.condition == "H2":
            h2 = check
    assert h2.state == "unknown"
    assert verdict.verdict == "flag"


def test_reply_that_is_not_json_raises(tmp_path):
    client, lesson, files = _setup(tmp_path, "not json at all")

    with pytest.raises(TaskError):
        JudgeCommand(client, "m", TEMPLATE).run(lesson, "Job.Run", files)


def test_reply_without_checks_raises(tmp_path):
    reply = _reply()
    del reply["checks"]
    client, lesson, files = _setup(tmp_path, reply)

    with pytest.raises(TaskError):
        JudgeCommand(client, "m", TEMPLATE).run(lesson, "Job.Run", files)


def test_missing_source_file_raises(tmp_path):
    client, lesson, _ = _setup(tmp_path, _reply())

    with pytest.raises(TaskError):
        JudgeCommand(client, "m", TEMPLATE).run(lesson, "Job.Run", [JudgeCommand.parse_source_file("nowhere.cs")])


def test_two_files_with_same_shown_name_raise(tmp_path):
    client, lesson, files = _setup(tmp_path, _reply())
    clash = JudgeCommand.parse_source_file(f"{files[0].path}=Base.cs")

    with pytest.raises(TaskError):
        JudgeCommand(client, "m", TEMPLATE).run(lesson, "Job.Run", [files[1], clash])


def test_citation_by_base_name_resolves_to_the_one_shown_file(tmp_path):
    client, lesson, files = _setup(tmp_path, _reply(evidence=["Job.cs:3"]))
    renamed = [
        JudgeCommand.parse_source_file(f"{files[0].path}=src/Jobs/Job.cs"),
        JudgeCommand.parse_source_file(f"{files[1].path}=src/Jobs/Base.cs"),
    ]

    verdict = JudgeCommand(client, "m", TEMPLATE).run(lesson, "Job.Run", renamed)

    assert verdict.bad_citations == []
    assert verdict.evidence[0].reference == "src/Jobs/Job.cs:3"
    assert verdict.evidence[0].line_text == "Retry();"
