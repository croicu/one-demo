import pytest

from one_demo.errors import TaskError
from one_demo.model_client import OpenAICompatibleClient
from one_demo.model_types import ChatMessage


class FakeTransport:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def get_json(self, url, headers, timeout_seconds):
        self.calls.append(("GET", url, headers, None))
        return self.reply

    def post_json(self, url, headers, body, timeout_seconds):
        self.calls.append(("POST", url, headers, body))
        return self.reply


def _chat_reply(content="ready", model="m"):
    return {
        "model": model,
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 3},
    }


def test_chat_sends_messages_and_parses_reply():
    transport = FakeTransport(_chat_reply())
    client = OpenAICompatibleClient("http://host/v1/", transport=transport)

    reply = client.chat("m", [ChatMessage("user", "hi")])

    method, url, headers, body = transport.calls[0]
    assert method == "POST"
    assert url == "http://host/v1/chat/completions"
    assert body == {"model": "m", "messages": [{"role": "user", "content": "hi"}]}
    assert "Authorization" not in headers
    assert reply.content == "ready"
    assert reply.model == "m"
    assert reply.prompt_tokens == 12
    assert reply.completion_tokens == 3


def test_chat_json_mode_and_temperature_are_sent():
    transport = FakeTransport(_chat_reply())
    client = OpenAICompatibleClient("http://host/v1", transport=transport)

    client.chat("m", [ChatMessage("user", "hi")], temperature=0, json_mode=True)

    body = transport.calls[0][3]
    assert body["temperature"] == 0
    assert body["response_format"] == {"type": "json_object"}


def test_credentials_become_headers():
    transport = FakeTransport(_chat_reply())
    client = OpenAICompatibleClient("http://host/v1", api_key="k", organization="org-1", project="proj_1", transport=transport)

    client.chat("m", [ChatMessage("user", "hi")])

    headers = transport.calls[0][2]
    assert headers["Authorization"] == "Bearer k"
    assert headers["OpenAI-Organization"] == "org-1"
    assert headers["OpenAI-Project"] == "proj_1"


def test_reply_without_usage_counts_zero_tokens():
    reply_payload = _chat_reply()
    del reply_payload["usage"]
    client = OpenAICompatibleClient("http://host/v1", transport=FakeTransport(reply_payload))

    reply = client.chat("m", [ChatMessage("user", "hi")])

    assert reply.prompt_tokens == 0
    assert reply.completion_tokens == 0


def test_reply_without_choices_raises():
    client = OpenAICompatibleClient("http://host/v1", transport=FakeTransport({"model": "m"}))

    with pytest.raises(TaskError):
        client.chat("m", [ChatMessage("user", "hi")])


def test_reply_without_text_content_raises():
    reply_payload = {"choices": [{"message": {"role": "assistant", "content": None}}]}
    client = OpenAICompatibleClient("http://host/v1", transport=FakeTransport(reply_payload))

    with pytest.raises(TaskError):
        client.chat("m", [ChatMessage("user", "hi")])


def test_list_models_returns_ids():
    transport = FakeTransport({"data": [{"id": "a"}, {"id": "b"}, {"object": "no id"}]})
    client = OpenAICompatibleClient("http://host/v1", transport=transport)

    assert client.list_models() == ["a", "b"]
    assert transport.calls[0][1] == "http://host/v1/models"


def test_list_models_without_data_raises():
    client = OpenAICompatibleClient("http://host/v1", transport=FakeTransport({"OK": True}))

    with pytest.raises(TaskError):
        client.list_models()


def test_from_settings_reads_section(tmp_path, monkeypatch):
    (tmp_path / "settings.json").write_text('{"settings": {"ollama": {"baseUrl": "http://localhost:11434/v1"}}}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    transport = FakeTransport({"data": []})

    client = OpenAICompatibleClient.from_settings("ollama", transport=transport)
    client.list_models()

    assert transport.calls[0][1] == "http://localhost:11434/v1/models"


def test_from_settings_without_base_url_raises(tmp_path, monkeypatch):
    (tmp_path / "settings.json").write_text('{"settings": {"ollama": {}}}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(TaskError):
        OpenAICompatibleClient.from_settings("ollama")
