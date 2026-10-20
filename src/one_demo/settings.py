from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from .diagnostics import CATEGORY_GENERAL, LEVEL_RANK, TelemetryLevel
from .errors import TaskError

_SETTINGS_PATH = Path("./settings.json")
_LOCAL_PATH = Path("./settings.local.json")


@dataclass
class Settings:
    debug: bool
    logging: TelemetryLevel = TelemetryLevel.ERROR
    log_categories: list[str] = field(default_factory=list)
    excluded_categories: list[str] = field(default_factory=list)

    _instance: ClassVar[Settings | None] = None

    @staticmethod
    def _merge(base: dict, override: dict) -> dict:
        """Returns base with override applied key-by-key. Where both sides hold a JSON object
        under the same key, the two are merged recursively instead of override replacing it, so
        settings.local.json can supply one field of a section (e.g. a secret) without repeating
        the rest of that section from settings.json."""
        merged = dict(base)
        for key, override_value in override.items():
            base_value = merged.get(key)
            if isinstance(base_value, dict) and isinstance(override_value, dict):
                merged[key] = Settings._merge(base_value, override_value)
            else:
                merged[key] = override_value
        return merged

    @staticmethod
    def _load_payload(path: Path, local_path: Path) -> dict:
        """Reads settings.json's 'settings' object, with settings.local.json's own 'settings'
        object merged over it (see _merge()). Private to the class — section() is the public way
        for a caller outside Settings to reach a section of the merged file."""
        settings_payload: dict = {}

        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                settings_file = json.load(f)
            if not isinstance(settings_file, dict):
                raise TaskError("settings.json must contain a JSON object.")
            base_settings = settings_file.get("settings", {})
            if not isinstance(base_settings, dict):
                raise TaskError("'settings' in settings.json must be a JSON object.")
            settings_payload = dict(base_settings)

        if local_path.exists():
            with local_path.open("r", encoding="utf-8") as f:
                local_payload = json.load(f)
            if isinstance(local_payload, dict):
                local_settings = local_payload.get("settings", {})
                if isinstance(local_settings, dict):
                    settings_payload = Settings._merge(settings_payload, local_settings)

        return settings_payload

    @classmethod
    def load(cls, path: Path = _SETTINGS_PATH, local_path: Path = _LOCAL_PATH) -> Settings:
        debug = False
        log_level = TelemetryLevel.ERROR
        log_categories: list[str] = []
        excluded_categories: list[str] = []
        expand_categories = False

        settings_payload = cls._load_payload(path, local_path)

        if settings_payload:
            debug = bool(settings_payload.get("debug", False))
            try:
                log_level = TelemetryLevel(settings_payload.get("logLevel", "error"))
            except ValueError:
                valid_levels = []
                for level in TelemetryLevel:
                    valid_levels.append(level.value)
                raise TaskError(f"'settings.logLevel' in settings.json must be one of: {', '.join(valid_levels)}")

            if "logLevel" in settings_payload:
                # An explicit logLevel is more specific than the blanket debug flag, so it wins
                # outright whenever the two would otherwise disagree about how much to show:
                # setting a permissive level (e.g. "verbose") shouldn't be silently muted by
                # debug's own separate category default, and setting a restrictive level (e.g.
                # "critical") shouldn't be forced open just because debug=true. debug only falls
                # back into play here when logLevel was left at its implicit default.
                expand_categories = LEVEL_RANK[log_level] < LEVEL_RANK[TelemetryLevel.ERROR]
            else:
                expand_categories = debug

            log_categories_payload = settings_payload.get("logCategories", [])
            if not isinstance(log_categories_payload, list):
                raise TaskError("'settings.logCategories' in settings.json must be an array of strings.")
            log_categories = []
            for category_name in log_categories_payload:
                log_categories.append(str(category_name))

            if log_categories and expand_categories and CATEGORY_GENERAL not in log_categories:
                # Expanded-logging intent (see expand_categories above) always keeps
                # CATEGORY_GENERAL alongside an explicit narrower list — its baseline info should
                # stay visible even while zoomed into one category, not be silently dropped by
                # naming a single other category.
                log_categories = [CATEGORY_GENERAL] + log_categories

            excluded_categories_payload = settings_payload.get("excludedCategories", [])
            if not isinstance(excluded_categories_payload, list):
                raise TaskError("'settings.excludedCategories' in settings.json must be an array of strings.")
            excluded_categories = []
            for category_name in excluded_categories_payload:
                excluded_categories.append(str(category_name))

        if not log_categories:
            # No explicit override: restricts console noise to CATEGORY_GENERAL unless expanded
            # logging was signaled (via an explicit permissive logLevel, or debug=true when
            # logLevel was left at its default — see expand_categories above), in which case
            # everything shows, same as an empty filter always has.
            log_categories = [] if expand_categories else [CATEGORY_GENERAL]

        cls._instance = cls(
            debug=debug,
            logging=log_level,
            log_categories=log_categories,
            excluded_categories=excluded_categories,
        )

        return cls._instance

    @classmethod
    def current(cls) -> Settings:
        if cls._instance is None:
            raise RuntimeError("Settings.load() must be called first.")
        return cls._instance

    @classmethod
    def section(cls, name: str, path: Path = _SETTINGS_PATH, local_path: Path = _LOCAL_PATH) -> dict:
        """Returns one named top-level section of settings.json (merged with
        settings.local.json's override), e.g. a plugin's or subsystem's own config section.
        settings.json's shape is uniform across consumer repos, so this is the public entry
        point for a caller outside this module to reach its own section without knowing how
        the file is read or merged — that stays encapsulated in _load_payload()."""
        settings_payload = cls._load_payload(path, local_path)
        section_payload = settings_payload.get(name, {})
        if not isinstance(section_payload, dict):
            raise TaskError(f"'settings.{name}' in settings.json must be a JSON object.")
        return section_payload
