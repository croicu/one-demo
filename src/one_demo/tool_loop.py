"""The tool loop: the model asks for tools, the harness runs them and hands back the results, until the
model answers. The model never runs anything itself. Every round can be recorded to a JSONL transcript."""

from __future__ import annotations

import json
import time
from pathlib import Path

from .contracts import ModelClient, Tool
from .diagnostics import Logger
from .errors import TaskError
from .model_client import CATEGORY_MODEL
from .model_types import ChatMessage, ChatReply, ToolCall, ToolSpec

CATEGORY_TOOLS = "tools"
DEFAULT_MAX_ROUNDS = 8


class Transcript:
    """One JSON object per line, one line per round, written as each round finishes, so a run that fails
    halfway still leaves the rounds it had."""

    def __init__(self, path: Path):
        self._path = path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
        except OSError as error:
            raise TaskError(f"Could not create the transcript {path}: {error}") from error

    def write(self, entry: dict) -> None:
        try:
            with self._path.open("a", encoding="utf-8") as transcript:
                transcript.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as error:
            raise TaskError(f"Could not write to the transcript {self._path}: {error}") from error


class ToolLoop:
    def __init__(
        self,
        client: ModelClient,
        model: str,
        tools: list[Tool],
        temperature: float | None = None,
        max_rounds: int = DEFAULT_MAX_ROUNDS,
        transcript: Transcript | None = None,
    ):
        self._client = client
        self._model = model
        self._tools: dict[str, Tool] = {}
        for tool in tools:
            self._tools[tool.spec.name] = tool
        self._temperature = temperature
        self._max_rounds = max_rounds
        self._transcript = transcript
        self.calls_run: list[ToolCall] = []

    def run(self, messages: list[ChatMessage]) -> ChatReply:
        """Rounds until the model answers without asking for a tool. After max_rounds rounds that all
        asked for tools, one last round offers no tools, so the model has to answer with what it has."""
        conversation = list(messages)
        specs: list[ToolSpec] = []
        for name in self._tools:
            specs.append(self._tools[name].spec)

        for number in range(1, self._max_rounds + 2):
            last_round = number > self._max_rounds
            offered: list[ToolSpec] = [] if last_round else specs
            if last_round:
                Logger.warning(
                    f"tools: {self._model} asked for tools in all {self._max_rounds} rounds; one last round without tools.",
                    CATEGORY_TOOLS,
                )
            started = time.perf_counter()
            reply = self._client.chat_with_tools(self._model, conversation, offered, temperature=self._temperature)
            seconds = time.perf_counter() - started

            for error in reply.tool_call_errors:
                Logger.warning(f"tools: round {number}: {self._model} made a malformed tool call: {error}", CATEGORY_TOOLS)
            for miss in reply.tool_call_format_misses:
                Logger.warning(f"tools: round {number}: accepted {self._model}'s call out of format: {miss}", CATEGORY_TOOLS)
            results = []
            if reply.tool_calls and not last_round:
                conversation.append(ChatMessage("assistant", reply.content, tool_calls=list(reply.tool_calls)))
                for call in reply.tool_calls:
                    result = self._run_tool(number, call)
                    self.calls_run.append(call)
                    results.append({"id": call.id, "name": call.name, "arguments": call.arguments, "result": result})
                    conversation.append(ChatMessage("tool", result, tool_call_id=call.id))

            self._record(number, reply, results, seconds)
            if not reply.tool_calls or last_round:
                if reply.tool_call_errors and not reply.content:
                    raise TaskError(f"{self._model}'s only output in round {number} was a malformed tool call: {reply.tool_call_errors[0]}")
                Logger.info(f"tools: {self._model} answered after {number} round(s).", CATEGORY_TOOLS)
                return reply
        raise TaskError("The tool loop ended without an answer.")  # not reached: the last round always returns

    def _run_tool(self, number: int, call: ToolCall) -> str:
        tool = self._tools.get(call.name)
        if tool is None:
            known = ", ".join(sorted(self._tools))
            Logger.warning(f"tools: round {number}: {self._model} called an unknown tool '{call.name}' (known: {known}).", CATEGORY_TOOLS)
            return f"error: there is no tool named '{call.name}'. The tools are: {known}."
        Logger.diagnostic(f"tools: round {number}: running {call.name}({json.dumps(call.arguments)})", CATEGORY_TOOLS)
        try:
            return tool.run(call.arguments)
        except TaskError as error:
            Logger.warning(f"tools: round {number}: {call.name} refused its arguments: {error}", CATEGORY_TOOLS)
            return f"error: {error}"

    def _record(self, number: int, reply: ChatReply, results: list[dict], seconds: float) -> None:
        Logger.diagnostic(
            f"tools: round {number}: {len(reply.tool_calls)} tool call(s), {reply.prompt_tokens} prompt + "
            f"{reply.completion_tokens} completion tokens, {seconds:.1f}s",
            CATEGORY_MODEL,
        )
        if self._transcript is None:
            return
        self._transcript.write(
            {
                "round": number,
                "model": self._model,
                "seconds": round(seconds, 3),
                "prompt_tokens": reply.prompt_tokens,
                "completion_tokens": reply.completion_tokens,
                "request": reply.request,
                "response": reply.response,
                "tool_results": results,
                "tool_call_errors": reply.tool_call_errors,
                "tool_call_format_misses": reply.tool_call_format_misses,
            }
        )
