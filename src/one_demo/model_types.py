"""Data passed to and returned by a model client."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class ChatReply:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    context_tokens: int | None = None
