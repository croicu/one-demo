"""Runtime behavioral interfaces.

`typing.Protocol` classes describing behavior (e.g. workers, executors) — not data. Persisted
or shared data contracts belong in protocols.py instead.
"""

from __future__ import annotations

from typing import Protocol

from .model_types import ChatMessage, ChatReply


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


class IssueTracker(Protocol):
    """Where findings are filed for the team that owns the code (GitHub issues, via `gh`)."""

    def open_issue_bodies(self, repo: str, label: str) -> list[str]: ...

    def ensure_label(self, repo: str, name: str, description: str) -> None: ...

    def create(self, repo: str, title: str, body: str, labels: list[str]) -> str: ...
