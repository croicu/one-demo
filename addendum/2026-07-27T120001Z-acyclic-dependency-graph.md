# Keep the internal dependency graph acyclic — break cycles with a Protocol, verify mechanically

**Source**: [croicu/quant-data](https://github.com/croicu/quant-data) — see
[croicu/quant-data#10](https://github.com/croicu/quant-data/issues/10) for the full history.

## What changed

`CLAUDE.md`'s Architecture conventions gained a new rule 9: the internal dependency graph must
stay acyclic. If two concrete modules would otherwise need each other, introduce a `Protocol`
(per rule 3's `contracts.py` convention) that one side depends on instead of the other's concrete
type. Verify this mechanically — list every module's static top-level imports and confirm no
module is reachable from itself — rather than trusting a passing test suite.

## Why

`quant-data`'s `MarketData` (its public read client) originally imported and instantiated
`PostgresDatabase` (a concrete implementation) directly, even though the abstraction it needed
(`MarketDataProvider`, a `Protocol`) already existed in the codebase. This meant `MarketData`'s
constructor signature was inherently shaped by Postgres connection details, so swapping backends
later (a cloud store, anything non-Postgres) would have forced another breaking change to the
public constructor. Fixed by making `MarketData.__init__` depend only on `MarketDataProvider`,
with a separate factory (`create_postgres_provider`) doing the concrete construction — this is rule
6's existing constructor-injection convention, just framed as a graph property: depending on an
abstraction instead of a concretion is specifically what keeps the graph from looping back on
itself.

Separately, a real circular import (see the companion "curate a public API surface" addendum
entry) survived `quant-data`'s own `pytest` suite and its console-script entry point for a while,
undetected — not because it didn't exist, but because both happened to touch the modules involved
in an import order that avoided triggering it. It only surfaced when directly testing
`import quant_data_internal.shared.postgres` as the very first import in a fresh process. A
passing test suite is not proof the import graph is acyclic; luck of import ordering can mask a
real cycle for a long time.

The fix used there — deferring the public package's re-exports into a module-level `__getattr__`
(PEP 562) so importing the package doesn't eagerly trigger the rest of the chain — is a legitimate
technique, but it's a fallback for cases a `Protocol` genuinely can't reach (e.g. a package needing
to re-export a name without owning the dependency direction between two packages), not the default
fix for a cycle. Reach for the `Protocol` first; it removes the cycle instead of just deferring it
past Python's own import-time checks.

## What an instance should do

- When adding a new dependency between two of your own modules, ask whether the other module
  might ever need something back from this one. If so, that's a `Protocol` (in `contracts.py`),
  not a concrete import — even if only one direction is a real dependency today.
- Before considering a refactor "done," especially one that splits a package or introduces a new
  public/private boundary, actually trace the import graph: `grep -E "^(from|import) " -r src/`
  across every module, and check nothing is reachable from itself. Don't rely on `pytest` passing
  as proof — the specific failure mode above (masked by import order) won't show up in a normal
  test run unless the test happens to enter the modules in the unlucky order.
- If you do need a lazy/deferred import to bridge two packages, treat it as documentation that a
  `Protocol` couldn't fully remove the relationship (and say so in a comment, like
  `quant-data`'s `__init__.py` does) — not as the default way to "fix" a circular import.
