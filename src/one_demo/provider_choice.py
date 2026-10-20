"""Which provider and model a command uses: a command-line flag wins over settings.json."""

from __future__ import annotations

from .errors import TaskError


class ProviderChoice:
    @staticmethod
    def resolve_provider(command: str, command_section: dict, provider_flag: str | None) -> str:
        """--provider wins over settings.json's '<command>.provider', which supplies the default."""
        provider = provider_flag if provider_flag else command_section.get("provider")
        if not provider:
            raise TaskError(f"No provider: pass --provider or set 'settings.{command}.provider' in settings.json.")
        return str(provider)

    @staticmethod
    def resolve_model(provider: str, provider_section: dict, model_flag: str | None, command_section: dict | None = None) -> str:
        """--model wins; then the command's own 'model', but only while the command runs on its own
        configured provider (the more specific setting); then the provider's 'model'. So switching
        provider with --provider also switches to a model that provider actually has."""
        if not provider_section:
            raise TaskError(f"Unknown provider '{provider}': there is no 'settings.{provider}' section.")
        model = model_flag
        if not model and command_section and command_section.get("provider") == provider:
            model = command_section.get("model")
        if not model:
            model = provider_section.get("model")
        if not model:
            raise TaskError(f"No model: pass --model or set 'settings.{provider}.model' in settings.json.")
        return str(model)

    @staticmethod
    def resolve_temperature(provider_section: dict, temperature_flag: float | None) -> float | None:
        """--temperature wins over the provider's own 'temperature'. None means none is sent, so the
        model uses its default; some models (e.g. gpt-6.1-sol) accept no other value."""
        if temperature_flag is not None:
            return temperature_flag
        temperature = provider_section.get("temperature")
        if temperature is None:
            return None
        if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
            raise TaskError("A provider's 'temperature' in settings.json must be a number.")
        return float(temperature)
