"""`one-demo tool-chat "<message>"`: the smallest tool loop. The prompt never contains the message;
the model has to fetch it with the get_message tool, then answer it."""

from __future__ import annotations

from .contracts import ModelClient
from .diagnostics import Logger
from .errors import TaskError
from .model_types import ChatMessage, ChatReply, ToolSpec
from .tool_loop import CATEGORY_TOOLS, ToolLoop, Transcript

SYSTEM_PROMPT = "You answer the user's message, but you can't see it directly: fetch it with the get_message tool first, then reply to what it says."
USER_PROMPT = "Please read my message with the get_message tool and answer it."


class GetMessageTool:
    """Returns the message given on the command line. Takes no arguments."""

    def __init__(self, message: str):
        self._message = message

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="get_message",
            description="Returns the user's message.",
            parameters={"type": "object", "properties": {}, "required": []},
        )

    def run(self, arguments: dict) -> str:
        return self._message


class ToolChatCommand:
    def __init__(self, client: ModelClient, model: str, transcript: Transcript | None = None):
        self._client = client
        self._model = model
        self._transcript = transcript

    def run(self, message: str) -> ChatReply:
        if not message.strip():
            raise TaskError("The message is empty.")
        Logger.info(f"tool-chat: asking {self._model} to fetch the message with a tool.", CATEGORY_TOOLS)
        loop = ToolLoop(self._client, self._model, [GetMessageTool(message)], transcript=self._transcript)
        reply = loop.run([ChatMessage("system", SYSTEM_PROMPT), ChatMessage("user", USER_PROMPT)])
        fetched = False
        for call in loop.calls_run:
            if call.name == "get_message":
                fetched = True
        if not fetched:
            raise TaskError(f"{self._model} answered without calling get_message, so it never saw the message. Its reply: {reply.content[:300]!r}")
        return reply
