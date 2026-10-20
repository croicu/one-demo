# Injectable `LoggingSink` Protocol; `Logger.perf()`; "Explicit DI First" Coding Style rule

**Source**: [croicu/quant-data](https://github.com/croicu/quant-data) — see
[croicu/quant-data#20](https://github.com/croicu/quant-data/issues/20) (and
[#19](https://github.com/croicu/quant-data/issues/19), which prompted it) for the full history.

## What changed

- `diagnostics.py`: new `CATEGORY_PERF = "perf"` constant, plus `Logger.perf(description,
  elapsed_seconds)` / `DiagnosticsLogSink.perf(...)` — a duration-marker log method, always at
  `INFO` under the fixed `perf` category, message shape `"duration: {elapsed:.3f}s - {description}"`.
- `protocols.py`: new `LoggingSink(Protocol)` — mirrors `DiagnosticsLogSink`'s method surface
  exactly (`diagnostic`/`info`/`warning`/`error`/`fatal(message, category="general")` plus
  `perf(description, elapsed_seconds)`). `category` defaults to the literal string `"general"`
  (not imported from `diagnostics.CATEGORY_GENERAL`), so `protocols.py` stays free of an outgoing
  dependency on `diagnostics.py` — see Architecture convention 9 (acyclic dependency graph).
- `CLAUDE.md`:
  - Architecture conventions 2/3 reworded: `protocols.py` now holds public contracts generally
    (persisted/shared data *or* behavioral `Protocol`s meant for a consumer to implement/inject),
    not "dataclasses only" — the distinction from `contracts.py` moves from data-vs-behavior to
    "does an external consumer implement this" vs. "internal wiring only."
  - Logging section's level guide gained a `Logger.perf` entry.
  - New Coding Style rule, **"Explicit DI First"**: when choosing between bridging into an
    ambient/shared mechanism (stdlib `logging`, a service locator, a singleton registry) and
    explicit constructor/parameter injection of a `Protocol`-typed object, default to explicit
    injection — especially when the injected object preserves capability (filtering, structured
    behavior) that the ambient mechanism would force you to reconstruct on the consuming side.

## Why

quant-data's own internal `Logger` was entirely private — a consumer embedding it as a library
(`quant-scratch`) had no way to see quant-data's internal logging (e.g. connection/query timing
markers added to diagnose #19's ~130s SSH-tunnel stall) regardless of the consumer's own
`settings.json`, since quant-data's `Logger` class was never exposed and the two `Logger` stacks
never talked to each other.

The design choice that mattered: **not** bridging quant-data's `Logger` onto Python's stdlib
`logging` module (the more commonly-cited "idiomatic library pattern" — `logging.getLogger(name)`,
let the host attach a `Handler`). The repo owner rejected that in favor of injecting a
`Protocol`-typed logger directly, reasoning explicitly: a host's own `Logger` (any project
generated from this template already has a structurally-identical one) already does real category
filtering, `excludedCategories`, and level-threshold work — injecting it directly preserves all of
that with zero glue code, whereas a stdlib bridge would force re-deriving that filtering logic from
`extra` fields and a logger-name convention on the consumer's side. This generalizes past logging:
whenever an ambient/framework-level integration point exists but would lose capability compared to
handing the object through directly, prefer the explicit-DI option — hence naming it as its own
Coding Style rule rather than leaving it implicit in one call site's history.

## What an instance should do

- Straight drop-in for `diagnostics.py`'s `Logger.perf`/`CATEGORY_PERF` addition — purely additive,
  no behavior change to existing log calls.
- `protocols.py`'s `LoggingSink` is immediately available even for a project that isn't (yet)
  consumed as a library by anything else — it costs nothing to have scaffolded, and becomes useful
  the moment a public constructor/factory needs to accept an injected logger.
- If your project *does* become a library another project imports, follow quant-data's pattern
  when a concrete class starts doing its own private-`Logger` calls: accept an optional
  `logger: LoggingSink = Logger` parameter (the private `Logger` class itself as the default value,
  not an instance — its methods are all `@staticmethod`s, so this behaves identically to direct
  static calls), store it, and call through `self._logger.info(...)` etc. instead of the static
  facade directly. See `quant_data._internal.shared.postgres.PostgresDatabase.__init__` for the
  concrete example if you want to see it end-to-end.
- Apply "Explicit DI First" going forward as a tiebreaker whenever a design choice comes up between
  an ambient integration mechanism and explicit `Protocol`-typed injection — not just for logging.
