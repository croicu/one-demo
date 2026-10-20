import json

import pytest

from one_demo.diagnostics import DiagnosticsLogSink, Logger, TelemetryLevel
from one_demo.errors import TaskError
from one_demo.judge_command import JudgeCommand
from one_demo.lesson import Lesson
from one_demo.model_client import OpenAICompatibleClient
from one_demo.model_types import ChatMessage, ChatReply


class RecordingSink(DiagnosticsLogSink):
    def __init__(self):
        self.records = []

    def log(self, level, message, category="general"):
        self.records.append((level, message))
        return super().log(level, message, category)

    def warnings(self):
        found = []
        for level, message in self.records:
            if level == TelemetryLevel.WARNING:
                found.append(message)
        return found


class FakeTransport:
    def __init__(self, prompt_tokens, completion_tokens):
        self.reply = {
            "model": "m",
            "choices": [{"message": {"content": "{}"}}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
        }

    def get_json(self, url, headers, timeout_seconds):
        return {}

    def post_json(self, url, headers, body, timeout_seconds):
        return self.reply


@pytest.fixture
def sink():
    recording = RecordingSink()
    Logger.set_logger(recording)
    yield recording
    Logger.set_logger(None)


def test_reply_carries_context_size_from_settings(tmp_path, monkeypatch):
    (tmp_path / "settings.json").write_text('{"settings": {"ollama": {"baseUrl": "http://x/v1", "contextTokens": 4096}}}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    client = OpenAICompatibleClient.from_settings("ollama", transport=FakeTransport(100, 10))

    reply = client.chat("m", [ChatMessage("user", "hi")])

    assert reply.context_tokens == 4096


def test_bad_context_size_in_settings_raises(tmp_path, monkeypatch):
    (tmp_path / "settings.json").write_text('{"settings": {"ollama": {"baseUrl": "http://x/v1", "contextTokens": "big"}}}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(TaskError):
        OpenAICompatibleClient.from_settings("ollama")


def test_no_warning_well_inside_context(sink):
    client = OpenAICompatibleClient("http://x/v1", transport=FakeTransport(2500, 300), context_tokens=4096)

    client.chat("m", [ChatMessage("user", "x" * 7500)])

    assert sink.warnings() == []


def test_warns_before_sending_a_prompt_estimated_near_the_limit(sink):
    client = OpenAICompatibleClient("http://x/v1", transport=FakeTransport(100, 10), context_tokens=4096)

    client.chat("m", [ChatMessage("user", "x" * 12000)])

    assert len(sink.warnings()) == 1
    assert "4000 tokens" in sink.warnings()[0]


def test_warns_when_reply_usage_is_near_the_limit(sink):
    client = OpenAICompatibleClient("http://x/v1", transport=FakeTransport(3800, 200), context_tokens=4096)

    client.chat("m", [ChatMessage("user", "short")])

    assert len(sink.warnings()) == 1
    assert "used 4000 of its 4096-token context" in sink.warnings()[0]


def test_no_guard_without_a_context_size(sink):
    client = OpenAICompatibleClient("http://x/v1", transport=FakeTransport(399000, 900))

    reply = client.chat("m", [ChatMessage("user", "x" * 100000)])

    assert reply.context_tokens is None
    assert sink.warnings() == []


class FixedClient:
    def __init__(self, reply):
        self.reply = reply

    def list_models(self):
        return []

    def chat(self, model, messages, temperature=None, json_mode=False):
        return self.reply


def _judge_inputs(tmp_path):
    lesson_path = tmp_path / "lesson.md"
    lesson_path.write_text("## Decision\n\n1. D1 fails → clear (H1)\n2. otherwise → flag (D1)\n", encoding="utf-8")
    code = tmp_path / "A.cs"
    code.write_text("Retry();\n", encoding="utf-8")
    return Lesson.load(lesson_path), [JudgeCommand.parse_source_file(str(code))]


def _reply_content():
    return json.dumps({"evidence": ["A.cs:1"], "checks": {"D1": "holds: A.cs:1"}, "reason": "r", "verdict": "flag"})


def test_judge_refuses_when_the_context_was_filled(tmp_path):
    lesson, files = _judge_inputs(tmp_path)
    full = ChatReply(content=_reply_content(), model="m", prompt_tokens=3900, completion_tokens=150, context_tokens=4096)

    with pytest.raises(TaskError, match="probably cut off"):
        JudgeCommand(FixedClient(full), "m", "{{lesson}}{{files}}").run(lesson, "A.Run", files)


def test_judge_accepts_usage_below_the_refusal_line(tmp_path):
    lesson, files = _judge_inputs(tmp_path)
    fine = ChatReply(content=_reply_content(), model="m", prompt_tokens=3500, completion_tokens=300, context_tokens=4096)

    verdict = JudgeCommand(FixedClient(fine), "m", "{{lesson}}{{files}}").run(lesson, "A.Run", files)

    assert verdict.verdict == "flag"
