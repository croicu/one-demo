"""Data passed to and returned by a model client."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ToolSpec:
    """A tool the model may call: its name, what it does, and its arguments as a JSON Schema object."""

    name: str
    description: str
    parameters: dict


@dataclass
class ToolCall:
    """One tool call the model asked for. The harness runs it; the model never does."""

    id: str
    name: str
    arguments: dict


@dataclass
class ChatMessage:
    role: str
    content: str
    # An assistant message that asked for tools carries its calls; a "tool" message answers one of them.
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None


@dataclass
class ChatReply:
    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    context_tokens: int | None = None
    # Set by chat_with_tools only: the calls the model asked for, the calls it got wrong (unparseable,
    # no name), the calls accepted although not in its template's format (e.g. a ```json fence), and
    # exactly what was sent and received, for the transcript.
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_errors: list[str] = field(default_factory=list)
    tool_call_format_misses: list[str] = field(default_factory=list)
    request: dict | None = None
    response: dict | None = None
