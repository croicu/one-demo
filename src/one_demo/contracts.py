"""Runtime behavioral interfaces.

`typing.Protocol` classes describing behavior (e.g. workers, executors) — not data. Persisted
or shared data contracts belong in protocols.py instead.
"""

from __future__ import annotations

from typing import Protocol

from .model_types import ChatMessage, ChatReply, ToolSpec


class HttpTransport(Protocol):
    """Sends JSON over HTTP and returns the decoded JSON reply. Raises TaskError on any failure."""

    def get_json(self, url: str, headers: dict[str, str], timeout_seconds: float) -> dict: ...

    def post_json(self, url: str, headers: dict[str, str], body: dict, timeout_seconds: float) -> dict: ...


class ModelClient(Protocol):
    """A chat model behind an OpenAI-compatible API."""

    def list_models(self) -> list[str]: ...

    def chat(
        self,
        model: str,
        messages: list[ChatMessage],
        temperature: float | None = None,
        json_mode: bool = False,
    ) -> ChatReply: ...

    def chat_with_tools(
        self,
        model: str,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
        temperature: float | None = None,
    ) -> ChatReply:
        """One round: the reply either answers (`content`) or asks for tools (`tool_calls`); it never
        runs a tool. Sets `request` and `response` to exactly what was sent and received."""
        ...


class Tool(Protocol):
    """A tool the harness runs for the model. `run` gets the model's arguments and returns the text the
    model sees as the result; it raises TaskError on arguments it can't use."""

    @property
    def spec(self) -> ToolSpec: ...

    def run(self, arguments: dict) -> str: ...


class IssueTracker(Protocol):
    """Where findings are filed for the team that owns the code (GitHub issues, via `gh`)."""

    def open_issue_bodies(self, repo: str, label: str) -> list[str]: ...

    def ensure_label(self, repo: str, name: str, description: str) -> None: ...

    def create(self, repo: str, title: str, body: str, labels: list[str]) -> str: ...
