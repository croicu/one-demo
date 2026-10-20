# Curate a public API surface; nest private internals, don't multiply bare top-level packages

**Source**: [croicu/quant-data](https://github.com/croicu/quant-data) — see
[croicu/quant-data#10](https://github.com/croicu/quant-data/issues/10) for the full history.

## What changed

`CLAUDE.md`'s Architecture conventions:

- Rule 7 (the existing "if a project ever grows beyond a single `src/<package_name>/` package"
  note) gained a collision-safety warning: an *additional* bare top-level package needs a name
  specific enough not to collide with another project's own top-level package once this repo is
  installed as a pip dependency elsewhere.
- New rule 8: curate a public API surface via `__init__.py` re-exports (`__all__` + root-level
  imports), and — if the internal implementation is substantial enough that "not in `__all__`"
  isn't a strong enough signal — a private subpackage, nested under the one namespaced package
  (`<package_name>/_internal/`), not a second bare top-level package.

## Why

`quant-data` needed to separate "safe for `quant-scratch` (its consumer) to import" from "internal
implementation, free to change without notice." It built this in two steps:

1. Curated `__init__.py` re-exports (`from quant_data import MarketData, OHLCV, ...`) — this part
   generalizes cleanly, no caveats.
2. Split the private implementation into its own package — but chose a **second bare top-level
   package** (`quant_data_internal`, a sibling of `quant_data`, not nested inside it). That specific
   choice — not the public/private split itself — caused a real circular-import crash: the private
   package needed a data type from the public package, while the public package's `__init__.py`
   eagerly imported something that (transitively) needed the private package back. Reproduced
   directly: `import quant_data_internal.shared.postgres` as the very first import in a process
   raised `ImportError: cannot import name 'PostgresDatabase' from partially initialized module`.
   Fixed with a module-level `__getattr__` (PEP 562) to defer the public package's re-exports from
   import-time to call-time — see the companion "acyclic dependency graph" addendum entry for why
   that specific failure mode exists.

   Had the private half been nested (`quant_data/_internal/...`) instead of sibling
   (`quant_data_internal/...`), the exact same public/private folder-level clarity would have held,
   and the circular import couldn't have happened at all — nesting keeps Python's own
   import-completion ordering on your side (importing a subpackage's submodule doesn't require
   re-running the parent's `__init__.py` from scratch once the parent is already registered in
   `sys.modules`, so a subpackage can safely reach back into a sibling submodule of its own parent
   without the "which one starts executing first" hazard a second, independent top-level package
   introduces).

Separately (extending rule 7, not the new rule 8): `quant-data` and `quant-scratch` — two instances
of *this same template* — each independently built multiple top-level packages using generic names
(`defs`, `shared`, `client`, ...). Installing both into one environment meant whichever installed
last silently shadowed the other's identically-named package entirely (reproduced both installation
orders — see [croicu/quant-data#7](https://github.com/croicu/quant-data/issues/7)). This is a real,
proven failure mode for the rare multi-package case rule 7 already documents, not a hypothetical.

## What an instance should do

- If you're curating a public surface: use `__init__.py` re-exports. If you need a private
  subpackage too, nest it (`<package_name>/_internal/`) rather than making it a second top-level
  package — you get the same clarity without the collision-safety burden or the circular-import
  risk.
- If you already built (or are building) a private half as a *second bare top-level package* the
  way `quant-data` did: it's not wrong, but budget for (a) that package's own name needing to stay
  collision-safe forever, same as your main package's name, and (b) checking your dependency graph
  for the cycle described above and in the companion addendum entry before you ship it.
- If this repo is (or becomes) installed as a pip dependency of another project, and you add *any*
  additional top-level package under `src/` (per rule 7's already-existing rare case): give it a
  name specific enough not to collide with another project's own top-level package — a bare generic
  name is exactly the shape that already broke twice for real.
