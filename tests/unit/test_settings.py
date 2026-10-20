import json

from one_demo.settings import Settings


def _write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_section_merges_local_fields_into_base_section(tmp_path):
    base = tmp_path / "settings.json"
    local = tmp_path / "settings.local.json"
    _write(base, {"settings": {"openai": {"baseUrl": "https://api.openai.com/v1"}}})
    _write(local, {"settings": {"openai": {"apiKey": "sk-test"}}})

    section = Settings.section("openai", path=base, local_path=local)

    assert section == {"baseUrl": "https://api.openai.com/v1", "apiKey": "sk-test"}


def test_section_local_value_overrides_base_value(tmp_path):
    base = tmp_path / "settings.json"
    local = tmp_path / "settings.local.json"
    _write(base, {"settings": {"openai": {"baseUrl": "https://api.openai.com/v1"}}})
    _write(local, {"settings": {"openai": {"baseUrl": "https://proxy.example/v1"}}})

    section = Settings.section("openai", path=base, local_path=local)

    assert section == {"baseUrl": "https://proxy.example/v1"}


def test_section_without_local_file_returns_base_section(tmp_path):
    base = tmp_path / "settings.json"
    _write(base, {"settings": {"ollama": {"baseUrl": "http://localhost:11434/v1"}}})

    section = Settings.section("ollama", path=base, local_path=tmp_path / "missing.json")

    assert section == {"baseUrl": "http://localhost:11434/v1"}


def test_section_missing_returns_empty(tmp_path):
    base = tmp_path / "settings.json"
    _write(base, {"settings": {}})

    section = Settings.section("openai", path=base, local_path=tmp_path / "missing.json")

    assert section == {}


def test_local_scalar_overrides_base_scalar(tmp_path):
    base = tmp_path / "settings.json"
    local = tmp_path / "settings.local.json"
    _write(base, {"settings": {"logLevel": "error"}})
    _write(local, {"settings": {"logLevel": "verbose"}})

    settings = Settings.load(path=base, local_path=local)

    assert settings.logging.value == "verbose"
