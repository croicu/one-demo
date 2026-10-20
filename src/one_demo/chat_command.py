"""`one-demo chat "<prompt>"`: send one prompt to a model and return its reply."""

from __future__ import annotations

from .contracts import ModelClient
from .diagnostics import Logger
from .errors import TaskError
from .model_client import CATEGORY_MODEL
from .model_types import ChatMessage, ChatReply


class ChatCommand:
    def __init__(self, client: ModelClient, model: str):
        self._client = client
        self._model = model

    def run(self, prompt: str) -> ChatReply:
        if not prompt.strip():
            raise TaskError("The prompt is empty.")

        Logger.info(f"chat: asking {self._model}.", CATEGORY_MODEL)
        reply = self._client.chat(self._model, [ChatMessage("user", prompt)])
        Logger.info(
            f"chat: {reply.model} replied ({reply.prompt_tokens} prompt + {reply.completion_tokens} completion tokens).",
            CATEGORY_MODEL,
        )
        return reply
