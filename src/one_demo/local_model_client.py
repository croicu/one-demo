"""ModelClient that runs a GGUF model in this process through llama.cpp (the llama-cpp-python
bindings): no server, nothing running in the background. The model is loaded on the first call of a
command and freed when the command ends."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from pathlib import Path

from .diagnostics import Logger
from .errors import TaskError
from .model_client import CATEGORY_MODEL, CONTEXT_WARNING_FRACTION, OpenAICompatibleClient
from .model_types import ChatMessage, ChatReply, ToolCall, ToolSpec
from .settings import Settings

KIND_LLAMACPP = "llamacpp"

# Qwen's tool-call markup and end-of-turn tokens (the chat templates of the local models).
TOOL_CALL_OPEN = "<tool_call>"
TOOL_CALL_CLOSE = "</tool_call>"
FENCE = "```"
STOP_SEQUENCES = ("<|im_end|>", "<|endoftext|>")


def _to_json(value: object, indent: int | None = None) -> str:
    """The `tojson` filter as Hugging Face templates expect it: plain JSON, non-ASCII kept."""
    return json.dumps(value, ensure_ascii=False, indent=indent)


def _raise_template_error(message: str) -> None:
    from jinja2 import TemplateError

    raise TemplateError(message)


def load_llama(model_path: str, context_tokens: int) -> object:
    """The real loader. llama-cpp-python is imported here, not at the top, because it is optional:
    only machines that run local models need it, compiled with CUDA."""
    try:
        from llama_cpp import Llama
    except ImportError as error:
        raise TaskError("Local models need llama-cpp-python built with CUDA: pip install llama-cpp-python with CMAKE_ARGS=-DGGML_CUDA=on set.") from error
    return Llama(model_path=model_path, n_ctx=context_tokens, n_gpu_layers=-1, verbose=False)


class LocalModelClient:
    def __init__(
        self,
        models: dict[str, str],
        context_tokens: int = 8192,
        loader: Callable[[str, int], object] = load_llama,
    ):
        self._models = models
        self._context_tokens = context_tokens
        self._loader = loader
        self._loaded: dict[str, object] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_section(cls, section_name: str, section: dict) -> LocalModelClient:
        models = section.get("models")
        if not isinstance(models, dict) or not models:
            raise TaskError(f"'settings.{section_name}.models' must map model names to GGUF files.")
        return cls(models=dict(models), context_tokens=int(section.get("contextTokens", 8192)))

    def list_models(self) -> list[str]:
        names = []
        for name in self._models:
            names.append(name)
        return names

    def chat(
        self,
        model: str,
        messages: list[ChatMessage],
        temperature: float | None = None,
        json_mode: bool = False,
    ) -> ChatReply:
        payload = []
        for message in messages:
            payload.append({"role": message.role, "content": message.content})
        arguments: dict = {"messages": payload}
        if temperature is not None:
            arguments["temperature"] = temperature

        with self._lock:
            llama = self._model(model)
            # JSON mode: llama-cpp-python enforces JSON with a sampling grammar, which made a 4B model
            # about 9x slower (93 -> 11 tokens/s). So try without it first and keep the reply if it is
            # a JSON object; only a reply that isn't is generated again under the grammar.
            parsed = self._complete(llama, model, arguments, "plain" if json_mode else "")
            if json_mode:
                content = self._json_object_text(parsed.content)
                if content is not None:
                    parsed.content = content
                else:
                    Logger.warning(
                        f"chat: {model}'s reply was not a JSON object without the JSON grammar; generating it "
                        f"again with the grammar. Reply started: {parsed.content[:120]!r}",
                        CATEGORY_MODEL,
                    )
                    arguments["response_format"] = {"type": "json_object"}
                    parsed = self._complete(llama, model, arguments, "JSON grammar")

        parsed.model = model
        parsed.context_tokens = self._context_tokens
        used = parsed.prompt_tokens + parsed.completion_tokens
        if used >= self._context_tokens * CONTEXT_WARNING_FRACTION:
            Logger.warning(f"chat: {model} used {used} of its {self._context_tokens}-token context.", CATEGORY_MODEL)
        return parsed

    def chat_with_tools(
        self,
        model: str,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
        temperature: float | None = None,
    ) -> ChatReply:
        """One round of tool calling, done by the harness: the prompt is rendered with the model's own
        chat template (Qwen's has a tools block), completed as plain text, and the model's
        `<tool_call>{json}</tool_call>` blocks are parsed here. The request records the rendered prompt:
        exactly what the model saw."""
        message_payload = []
        for message in messages:
            message_payload.append(OpenAICompatibleClient.tool_message_payload(message, arguments_as_text=False))
        tool_payload = []
        for tool in tools:
            tool_payload.append(OpenAICompatibleClient.tool_spec_payload(tool))

        with self._lock:
            llama = self._model(model)
            template = llama.metadata.get("tokenizer.chat_template")
            if not template:
                raise TaskError(f"{model}'s GGUF file has no chat template, so its prompt can't be rendered for tools.")
            prompt = self._render(template, message_payload, tool_payload)
            arguments: dict = {"prompt": prompt, "max_tokens": None, "stop": list(STOP_SEQUENCES)}
            if temperature is not None:
                arguments["temperature"] = temperature
            description = f"chat {model} (in process, {len(tools)} tool(s))"
            Logger.diagnostic(description, CATEGORY_MODEL)
            started = time.perf_counter()
            try:
                completion = llama.create_completion(**arguments)
            except ValueError as error:
                raise TaskError(f"{model} could not answer in process: {error}") from error
            Logger.perf(description, time.perf_counter() - started)

        text = self._completion_text(completion, model)
        content, calls, errors = self._parse_tool_calls(text)
        misses: list[str] = []
        if not calls and not errors:
            tool_names = []
            for tool in tools:
                tool_names.append(tool.name)
            content, calls, misses = self._parse_untagged_tool_calls(content, tool_names, errors)
        usage = completion.get("usage") if isinstance(completion.get("usage"), dict) else {}
        reply = ChatReply(
            content=content,
            model=model,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            context_tokens=self._context_tokens,
            tool_calls=calls,
            tool_call_errors=errors,
            tool_call_format_misses=misses,
            request={"model": model, "messages": message_payload, "tools": tool_payload, "prompt": prompt},
            response=completion,
        )
        used = reply.prompt_tokens + reply.completion_tokens
        if used >= self._context_tokens * CONTEXT_WARNING_FRACTION:
            Logger.warning(f"chat: {model} used {used} of its {self._context_tokens}-token context.", CATEGORY_MODEL)
        return reply

    @staticmethod
    def _render(template: str, messages: list[dict], tools: list[dict]) -> str:
        """Renders a Hugging Face-style chat template the way transformers does (sandboxed jinja2,
        trimmed blocks). jinja2 comes with llama-cpp-python, so it is imported only here."""
        from jinja2 import TemplateError
        from jinja2.sandbox import ImmutableSandboxedEnvironment

        environment = ImmutableSandboxedEnvironment(trim_blocks=True, lstrip_blocks=True)
        environment.filters["tojson"] = _to_json
        environment.globals["raise_exception"] = _raise_template_error
        try:
            return environment.from_string(template).render(messages=messages, tools=tools or None, add_generation_prompt=True)
        except TemplateError as error:
            raise TaskError(f"The model's chat template could not be rendered: {error}") from error

    @staticmethod
    def _completion_text(completion: dict, model: str) -> str:
        choices = completion.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise TaskError(f"Completion from {model} has no choices: {str(completion)[:300]}")
        text = choices[0].get("text")
        if not isinstance(text, str):
            raise TaskError(f"Completion from {model} has no text: {str(completion)[:300]}")
        return text

    @staticmethod
    def _parse_tool_calls(text: str) -> tuple[str, list[ToolCall], list[str]]:
        """Splits a completion into its text and its `<tool_call>` blocks. A block that isn't a JSON
        object with a name, or that never closes, is a tool-call error, not a silent drop."""
        calls: list[ToolCall] = []
        errors: list[str] = []
        content_parts = []
        position = 0
        while True:
            start = text.find(TOOL_CALL_OPEN, position)
            if start == -1:
                content_parts.append(text[position:])
                break
            content_parts.append(text[position:start])
            end = text.find(TOOL_CALL_CLOSE, start)
            if end == -1:
                errors.append(f"a tool call that never closes: {text[start : start + 200]!r}")
                break
            body = text[start + len(TOOL_CALL_OPEN) : end].strip()
            position = end + len(TOOL_CALL_CLOSE)
            call = LocalModelClient._tool_call_from_json(body, len(calls) + 1, errors)
            if call is not None:
                calls.append(call)
        return "".join(content_parts).strip(), calls, errors

    @staticmethod
    def _parse_untagged_tool_calls(text: str, tool_names: list[str], errors: list[str]) -> tuple[str, list[ToolCall], list[str]]:
        """The near miss: no `<tool_call>` tags, but a ```json fence (or the whole reply) holding a JSON
        object whose `name` is an offered tool. Taken as the call, and returned as a format miss so the
        transcript still shows the model didn't follow its template. JSON that names no offered tool
        stays text: it may be the answer."""
        calls: list[ToolCall] = []
        misses: list[str] = []
        content_parts = []
        position = 0
        while True:
            start = text.find(FENCE, position)
            if start == -1:
                content_parts.append(text[position:])
                break
            line_end = text.find("\n", start)
            end = text.find(FENCE, line_end + 1) if line_end != -1 else -1
            if end == -1:
                content_parts.append(text[position:])
                break
            body = text[line_end + 1 : end].strip()
            call = LocalModelClient._offered_tool_call(body, tool_names, len(calls) + 1, errors)
            if call is None:
                content_parts.append(text[position : end + len(FENCE)])
            else:
                content_parts.append(text[position:start])
                calls.append(call)
                misses.append(f"{call.name}: called in a ``` fence instead of <tool_call> tags")
            position = end + len(FENCE)

        if not calls:
            call = LocalModelClient._offered_tool_call(text.strip(), tool_names, 1, errors)
            if call is not None:
                return "", [call], [f"{call.name}: called as bare JSON instead of <tool_call> tags"]
        return "".join(content_parts).strip(), calls, misses

    @staticmethod
    def _offered_tool_call(body: str, tool_names: list[str], number: int, errors: list[str]) -> ToolCall | None:
        try:
            decoded = json.loads(body)
        except json.JSONDecodeError:
            return None
        if not isinstance(decoded, dict) or decoded.get("name") not in tool_names:
            return None
        return LocalModelClient._tool_call_from_json(body, number, errors)

    @staticmethod
    def _tool_call_from_json(body: str, number: int, errors: list[str]) -> ToolCall | None:
        try:
            decoded = json.loads(body)
        except json.JSONDecodeError:
            errors.append(f"a tool call that is not JSON: {body[:200]!r}")
            return None
        if not isinstance(decoded, dict) or not isinstance(decoded.get("name"), str) or not decoded["name"]:
            errors.append(f"a tool call without a name: {body[:200]!r}")
            return None
        arguments = decoded.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments or "{}")
            except json.JSONDecodeError:
                errors.append(f"{decoded['name']}: arguments are not JSON: {arguments[:200]!r}")
                return None
        if not isinstance(arguments, dict):
            errors.append(f"{decoded['name']}: arguments are not a JSON object: {str(arguments)[:200]!r}")
            return None
        return ToolCall(id=f"call_{number}", name=decoded["name"], arguments=arguments)

    @staticmethod
    def _complete(llama: object, model: str, arguments: dict, how: str) -> ChatReply:
        description = f"chat {model} (in process)"
        if how:
            description = f"chat {model} (in process, {how})"
        Logger.diagnostic(description, CATEGORY_MODEL)
        started = time.perf_counter()
        try:
            reply = llama.create_chat_completion(**arguments)
        except ValueError as error:
            raise TaskError(f"{model} could not answer in process: {error}") from error
        Logger.perf(description, time.perf_counter() - started)
        return OpenAICompatibleClient._parse_chat_reply(reply, model)

    @staticmethod
    def _json_object_text(content: str) -> str | None:
        """The reply as JSON object text, unwrapped from a ```json fence if the model added one; None if
        it is not a JSON object."""
        text = content.strip()
        if text.startswith("```"):
            first_newline = text.find("\n")
            if first_newline == -1 or not text.endswith("```"):
                return None
            text = text[first_newline + 1 : -3].strip()
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(decoded, dict):
            return None
        return text

    def _model(self, name: str) -> object:
        if name in self._loaded:
            return self._loaded[name]
        path = self._models.get(name)
        if path is None:
            raise TaskError(f"Unknown local model '{name}'. Known: {', '.join(sorted(self._models))}.")
        if not Path(path).exists():
            raise TaskError(f"Model file not found: {path}")
        # One model at a time: the 14B alone nearly fills the 8 GB GPU.
        self._unload_all()
        Logger.info(f"chat: loading {name} from {path}.", CATEGORY_MODEL)
        started = time.perf_counter()
        llama = self._loader(path, self._context_tokens)
        Logger.perf(f"load {name}", time.perf_counter() - started)
        self._loaded[name] = llama
        return llama

    def _unload_all(self) -> None:
        for name in self._loaded:
            Logger.diagnostic(f"chat: unloading {name}", CATEGORY_MODEL)
            close = getattr(self._loaded[name], "close", None)
            if close is not None:
                close()
        self._loaded = {}


def client_for(provider: str, settings_path: Path | None = None) -> object:
    """The ModelClient a provider section describes: in-process llama.cpp for `"kind": "llamacpp"`,
    otherwise an OpenAI-compatible HTTP client."""
    if settings_path is None:
        section = Settings.section(provider)
    else:
        section = Settings.section(provider, path=settings_path)
    if section.get("kind") == KIND_LLAMACPP:
        return LocalModelClient.from_section(provider, section)
    if settings_path is None:
        return OpenAICompatibleClient.from_settings(provider)
    return OpenAICompatibleClient.from_settings(provider, path=settings_path)
