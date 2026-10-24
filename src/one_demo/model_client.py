"""OpenAI-compatible chat client (OpenAI, a llama-server, or any provider exposing the same API)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from .contracts import HttpTransport
from .diagnostics import Logger
from .errors import TaskError
from .model_types import ChatMessage, ChatReply, ToolCall, ToolSpec
from .settings import Settings

CATEGORY_MODEL = "model"

# Code and markdown run at roughly 3-4 characters per token; 3 overestimates, so warnings come early.
CHARS_PER_TOKEN_ESTIMATE = 3
CONTEXT_WARNING_FRACTION = 0.85


class UrllibTransport:
    """HttpTransport over the standard library, so the client needs no third-party package."""

    def get_json(self, url: str, headers: dict[str, str], timeout_seconds: float) -> dict:
        request = urllib.request.Request(url, headers=headers, method="GET")
        return self._send(request, timeout_seconds)

    def post_json(self, url: str, headers: dict[str, str], body: dict, timeout_seconds: float) -> dict:
        data = json.dumps(body).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers=headers, method="POST")
        return self._send(request, timeout_seconds)

    @staticmethod
    def _send(request: urllib.request.Request, timeout_seconds: float) -> dict:
        url = request.full_url
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                payload = response.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            body_excerpt = e.read().decode("utf-8", errors="replace")[:500]
            message = f"HTTP {e.code} from {request.get_method()} {url}: {body_excerpt}"
            Logger.error(message, CATEGORY_MODEL)
            raise TaskError(message) from e
        except (urllib.error.URLError, TimeoutError) as e:
            message = f"Could not reach {request.get_method()} {url} (timeout {timeout_seconds}s): {e}"
            Logger.error(message, CATEGORY_MODEL)
            raise TaskError(message) from e

        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as e:
            # A retired endpoint can still answer 200 with a plain-text body (GitHub Models did).
            message = f"Reply from {url} is not JSON: {payload[:200]!r}"
            Logger.error(message, CATEGORY_MODEL)
            raise TaskError(message) from e
        if not isinstance(decoded, dict):
            message = f"Reply from {url} is JSON but not an object: {payload[:200]!r}"
            Logger.error(message, CATEGORY_MODEL)
            raise TaskError(message)
        return decoded


class OpenAICompatibleClient:
    """ModelClient for any provider with an OpenAI-compatible API. Which provider is decided by the
    settings section it is built from (see docs/PROTOCOL.md)."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        organization: str | None = None,
        project: str | None = None,
        transport: HttpTransport | None = None,
        timeout_seconds: float = 300.0,
        context_tokens: int | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._organization = organization
        self._project = project
        self._transport = transport if transport is not None else UrllibTransport()
        self._timeout_seconds = timeout_seconds
        self._context_tokens = context_tokens

    @classmethod
    def from_settings(
        cls,
        section_name: str,
        transport: HttpTransport | None = None,
        path: Path | None = None,
    ) -> OpenAICompatibleClient:
        if path is None:
            section = Settings.section(section_name)
        else:
            section = Settings.section(section_name, path=path)
        if not section:
            raise TaskError(f"Unknown provider '{section_name}': there is no 'settings.{section_name}' section.")
        base_url = section.get("baseUrl")
        if not base_url:
            raise TaskError(f"'settings.{section_name}.baseUrl' is missing from settings.json.")
        if section.get("apiKeyRequired") and not section.get("apiKey"):
            raise TaskError(
                f"No API key: add settings.{section_name}.apiKey to settings.local.json "
                "(see settings.local.example.json). It is gitignored, so the key stays on this machine."
            )
        context_tokens = section.get("contextTokens")
        if context_tokens is not None and (not isinstance(context_tokens, int) or context_tokens <= 0):
            raise TaskError(f"'settings.{section_name}.contextTokens' must be a positive whole number.")
        return cls(
            base_url=base_url,
            api_key=section.get("apiKey"),
            organization=section.get("organization"),
            project=section.get("project"),
            transport=transport,
            context_tokens=context_tokens,
        )

    def list_models(self) -> list[str]:
        reply = self._transport.get_json(self._base_url + "/models", self._headers(), self._timeout_seconds)
        entries = reply.get("data")
        if not isinstance(entries, list):
            raise TaskError(f"Model list from {self._base_url} has no 'data' array.")
        model_ids = []
        for entry in entries:
            if isinstance(entry, dict) and "id" in entry:
                model_ids.append(str(entry["id"]))
        return model_ids

    def chat(
        self,
        model: str,
        messages: list[ChatMessage],
        temperature: float | None = None,
        json_mode: bool = False,
    ) -> ChatReply:
        message_payload = []
        for message in messages:
            message_payload.append({"role": message.role, "content": message.content})
        body: dict = {"model": model, "messages": message_payload}
        if temperature is not None:
            body["temperature"] = temperature
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        Logger.diagnostic(f"chat: {model} at {self._base_url}, {len(messages)} message(s)", CATEGORY_MODEL)
        self._warn_if_prompt_too_long(model, messages)
        started = time.perf_counter()
        reply = self._transport.post_json(self._base_url + "/chat/completions", self._headers(), body, self._timeout_seconds)
        Logger.perf(f"chat {model}", time.perf_counter() - started)

        parsed = self._parse_chat_reply(reply, model)
        parsed.context_tokens = self._context_tokens
        self._warn_if_context_nearly_full(parsed)
        return parsed

    def chat_with_tools(
        self,
        model: str,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
        temperature: float | None = None,
    ) -> ChatReply:
        """One round of native tool calling (Chat Completions `tools` / `tool_calls`)."""
        message_payload = []
        for message in messages:
            message_payload.append(self.tool_message_payload(message, arguments_as_text=True))
        body: dict = {"model": model, "messages": message_payload}
        if tools:
            tool_payload = []
            for tool in tools:
                tool_payload.append(self.tool_spec_payload(tool))
            body["tools"] = tool_payload
        if temperature is not None:
            body["temperature"] = temperature

        Logger.diagnostic(f"chat: {model} at {self._base_url} with {len(tools)} tool(s), {len(messages)} message(s)", CATEGORY_MODEL)
        self._warn_if_prompt_too_long(model, messages)
        started = time.perf_counter()
        reply = self._transport.post_json(self._base_url + "/chat/completions", self._headers(), body, self._timeout_seconds)
        Logger.perf(f"chat {model} (tools)", time.perf_counter() - started)

        parsed = self._parse_tool_reply(reply, model)
        parsed.context_tokens = self._context_tokens
        parsed.request = body
        parsed.response = reply
        self._warn_if_context_nearly_full(parsed)
        return parsed

    @staticmethod
    def tool_spec_payload(tool: ToolSpec) -> dict:
        """A tool in the OpenAI shape, which the local chat templates take too."""
        return {"type": "function", "function": {"name": tool.name, "description": tool.description, "parameters": tool.parameters}}

    @staticmethod
    def tool_message_payload(message: ChatMessage, arguments_as_text: bool) -> dict:
        """A message in the OpenAI shape. OpenAI wants a call's arguments as JSON text; the local chat
        templates serialize them themselves, so they get the object."""
        payload: dict = {"role": message.role, "content": message.content}
        if message.tool_calls:
            calls = []
            for call in message.tool_calls:
                arguments: object = call.arguments
                if arguments_as_text:
                    arguments = json.dumps(call.arguments)
                calls.append({"id": call.id, "type": "function", "function": {"name": call.name, "arguments": arguments}})
            payload["tool_calls"] = calls
        if message.tool_call_id is not None:
            payload["tool_call_id"] = message.tool_call_id
        return payload

    @staticmethod
    def _parse_tool_reply(reply: dict, requested_model: str) -> ChatReply:
        """Like _parse_chat_reply, but a reply that asks for tools may have no text at all."""
        choices = reply.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise TaskError(f"Chat reply for {requested_model} has no choices: {str(reply)[:300]}")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise TaskError(f"Chat reply for {requested_model} has no message: {str(reply)[:300]}")

        calls = []
        errors = []
        raw_calls = message.get("tool_calls") or []
        for raw in raw_calls:
            function = raw.get("function") if isinstance(raw, dict) else None
            if not isinstance(function, dict) or not function.get("name"):
                errors.append(f"a tool call without a function name: {str(raw)[:200]}")
                continue
            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except json.JSONDecodeError:
                errors.append(f"{function['name']}: arguments are not JSON: {str(function.get('arguments'))[:200]}")
                continue
            if not isinstance(arguments, dict):
                errors.append(f"{function['name']}: arguments are not a JSON object: {str(arguments)[:200]}")
                continue
            calls.append(ToolCall(id=str(raw.get("id", f"call_{len(calls) + 1}")), name=str(function["name"]), arguments=arguments))

        content = message.get("content")
        if not isinstance(content, str):
            content = ""
        if not content and not calls and not errors:
            raise TaskError(f"Chat reply for {requested_model} has neither text nor tool calls: {str(reply)[:300]}")

        usage = reply.get("usage")
        if not isinstance(usage, dict):
            usage = {}
        return ChatReply(
            content=content,
            model=str(reply.get("model", requested_model)),
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            tool_calls=calls,
            tool_call_errors=errors,
        )

    def _warn_if_prompt_too_long(self, model: str, messages: list[ChatMessage]) -> None:
        """Estimates the prompt's size before sending. A server that runs out of context may cut the
        start of the prompt silently instead of failing, so this is the only early warning."""
        if self._context_tokens is None:
            return
        characters = 0
        for message in messages:
            characters += len(message.content)
        estimated_tokens = characters // CHARS_PER_TOKEN_ESTIMATE
        if estimated_tokens >= self._context_tokens * CONTEXT_WARNING_FRACTION:
            Logger.warning(
                f"chat: the prompt to {model} is about {estimated_tokens} tokens (estimated from "
                f"{characters} characters), near or over the {self._context_tokens}-token context at "
                f"{self._base_url}. The server may cut the start of the prompt without saying so.",
                CATEGORY_MODEL,
            )

    def _warn_if_context_nearly_full(self, reply: ChatReply) -> None:
        if reply.context_tokens is None:
            return
        used = reply.prompt_tokens + reply.completion_tokens
        if used >= reply.context_tokens * CONTEXT_WARNING_FRACTION:
            Logger.warning(
                f"chat: {reply.model} used {used} of its {reply.context_tokens}-token context "
                f"({reply.prompt_tokens} prompt + {reply.completion_tokens} reply). If the prompt was "
                "longer than that, its start was cut off.",
                CATEGORY_MODEL,
            )

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = "Bearer " + self._api_key
        if self._organization:
            headers["OpenAI-Organization"] = self._organization
        if self._project:
            headers["OpenAI-Project"] = self._project
        return headers

    @staticmethod
    def _parse_chat_reply(reply: dict, requested_model: str) -> ChatReply:
        choices = reply.get("choices")
        if not isinstance(choices, list) or not choices:
            raise TaskError(f"Chat reply for {requested_model} has no choices: {str(reply)[:300]}")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise TaskError(f"Chat reply for {requested_model} has no text content: {str(reply)[:300]}")

        usage = reply.get("usage")
        if not isinstance(usage, dict):
            usage = {}
        return ChatReply(
            content=content,
            model=str(reply.get("model", requested_model)),
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
        )
