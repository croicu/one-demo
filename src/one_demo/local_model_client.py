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
from .model_types import ChatMessage, ChatReply
from .settings import Settings

KIND_LLAMACPP = "llamacpp"


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
