# one-demo

A demo project

---

## Install

```bash
pip install -e ".[dev]"
```

## Lint

```bash
ruff check src/ tests/
ruff format src/ tests/
```

## Test

```bash
pytest
pytest tests/unit/test_foo.py::test_bar   # single test
```
