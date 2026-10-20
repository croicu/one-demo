# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Mission

A demo project.

## Template Sync

- **Source**: [croicu/tpl-py](https://github.com/croicu/tpl-py)
- **Synced to**: 2026-08-30T19:00:00Z

This repo is either `tpl-py` itself or was generated from it. `tpl-py`'s `ADDENDUM.md` is a
curated, timestamped log of changes meant for downstream instances (new/changed rules,
base-module fixes, obsoleted patterns) — routine housekeeping doesn't get an entry. Which
protocol below applies depends on which repo you're in.

### Reading the addendum (applies in an instance)

1. Fetch `tpl-py`'s `ADDENDUM.md` over plain HTTPS (e.g. `WebFetch` against the raw content
   URL) — no `gh` CLI, no `git clone`, no persistent git remote required.
2. Compare each row's timestamp against this repo's `Synced to` value above.
3. For rows newer than that, fetch only that entry's individual file under `addendum/` (not the
   whole history) and decide whether/how to apply it here.
4. After applying (or deliberately skipping) everything newer, bump `Synced to` above to the
   latest entry's timestamp.

### Writing an addendum entry (applies only in `tpl-py` itself)

1. When making a change meant for downstream instances, add a new file under `addendum/`
   (filename prefixed with an ISO timestamp) describing what changed, why, and what an instance
   should do about it.
2. Append a row to `ADDENDUM.md`'s table (timestamp, title, filename).

### Porting an instance's improvement back to `tpl-py` (applies in an instance)

The addendum protocol above is one-directional — `tpl-py` pushing a change out to instances. This
is the reverse channel: when a change made *in an instance* touches a **template-inherited
artifact** (a class this repo started with from `tpl-py`'s scaffolding, e.g. `settings.py`'s
`Settings` or `diagnostics.py`'s `Logger`; or a markdown file `tpl-py` itself authors, e.g. this
file or `ADDENDUM.md`'s structure) and the change is generalizable rather than specific to this
repo's own domain, open an issue in `croicu/tpl-py` (`gh issue create --repo croicu/tpl-py`)
describing the change and cross-linking back to the commit/PR here, so `tpl-py` can decide whether
to adopt it and, if so, write its own addendum entry per "Writing an addendum entry" above. Not
every edit to a template-inherited file qualifies — a one-off tweak that only makes sense in this
repo's own context doesn't need a backport issue, only a fix, convention, or reusable pattern that
would generalize to other instances too. See the "Completed Tasks" section below (issues #3–#6)
for worked examples of this same pattern sourced from other instances (`quant-scratch`,
`quant-data`).

## Cross-Repo Coordination

Not every instance needs this section — add it (or an adapted version of it) once this repo has a
real data/API contract with another repo in your ecosystem (a producer/consumer relationship, not
just "both repos happen to exist"). Same judgment call as the multi-package case in Architecture
convention 7: build this when the need is real, don't pre-build it. Retrofit is cheap — this is
process guidance, not code.

**Placement rule**: a cross-repo issue lives in whichever repo owns the actionable follow-up, not
necessarily where the need originated:
- **This repo ships a breaking or notable change** (a changed contract, a deprecated symbol, a
  schema migration) → open an issue in the consumer repo(s) announcing it, since that's where the
  reacting work happens.
- **A consumer needs something from this repo** (a new capability, a bug in what it returns) →
  open an issue here requesting it, since that's where the building work happens.

**Does a given change need one at all?** If this repo curates a public surface (Architecture
convention 8), use that boundary to decide cheaply instead of re-deriving it each time: touched
only internal implementation (not re-exported, not a documented CLI flag/file format)? No
cross-repo issue needed, *unless* the change alters externally observable behavior anyway (a bug
fix that changes what a public function returns still counts). Touched the actual public surface
(an `__init__.py` re-export, a public class's constructor/method signature, a CLI flag, a persisted
file/schema format)? Default to assuming a cross-repo issue is needed, then confirm.

**Conventions**:
- Label every cross-repo issue `cross-repo` (alongside the normal `status:*` label) so these
  threads are filterable apart from this repo's own internal work — create the label
  (`gh label create`) if it doesn't exist yet.
- Always cross-link: the issue body must reference the originating repo/issue/commit, so either
  side is navigable from the other.
- Use `gh issue create --repo <owner>/<repo>` to open a cross-repo issue directly from wherever
  you're working — no need to switch working directories first.

**Multiple consumers**: don't build a consumer registry, fan-out-on-breaking-changes, or a
rollout-tracking process ahead of a second real consumer — that's speculative process-building, the
same judgment call as the "don't build a DI factory/composition-root prematurely" note under Coding
Style. When a second consumer repo actually arrives, that's the trigger to design that extension,
not before.

## Collaboration rules

- Before implementing any feature or non-trivial change, ask clarifying questions until the intent is unambiguous.
- If anything is unclear or could be interpreted multiple ways, ask — do not assume and implement.

### Task workflow

Tasks are tracked as GitHub issues in this repo, status via labels: `status:brainstorm`,
`status:implementation`, `status:testing`, `status:ready-to-submit`, `status:ready-for-integration`
(only needed once this repo has a `cross-repo` relationship with another — see "Ready for
Integration" below). There is no `status:done` label — reaching Done means closing the issue.
(These labels don't exist on a freshly-created repo — create them with `gh label create` before
the first task needs one.)

Tasks come in two flavors, which affects whether step 1 below applies:

- **Planned tasks** — a `tasks/<task-name>.md` already exists (or is being freshly authored as a
  deliverable in its own right) before implementation discussion starts, e.g. dropped in by the
  user ahead of time. Follow all stages below, starting with Brainstorm.
- **Ad-hoc tasks** — the task emerges organically from conversation (no pre-existing or
  deliberately-authored task file). Skip straight to Implementation: no `tasks/<task-name>.md` gets
  created at all, just open the GitHub issue directly once the discussion has converged. Don't
  create a task file first just to immediately trim/delete it — that's churn, not documentation.

For any non-trivial feature or change, follow these stages:

1. **Brainstorm** (planned tasks only) — copy `tasks/new_task.md` to `tasks/<task-name>.md` with the problem statement; update it with conclusions as the design discussion progresses. This is scratch space for live back-and-forth — an issue isn't required at this stage, but a lightweight tracking issue labeled `status:brainstorm` can be opened for backlog visibility if wanted; either way, `tasks/<task-name>.md` (not the issue) stays the working document until the design converges.
2. **Implementation** — open a GitHub issue (`gh issue create`) with the converged problem statement + conclusions as the body, labeled `status:implementation`. Write the code. For a planned task, `tasks/<task-name>.md` is no longer the source of truth once the issue exists — trim it to a one-line pointer at the issue (or delete it) rather than maintaining both. For an ad-hoc task, there's no file to trim — the issue was the first artifact.
3. **Testing** — relabel the issue `status:testing`. Verify correctness; post test results and any open issues as an issue comment. **For a `cross-repo` issue that originated from a consumer repo's own testing/diagnosis**, this repo's own verification — even a live check against a real external dependency — confirms the fix works in isolation, but isn't the same as confirming the originally reported symptom is actually resolved: that requires the consumer to pull the updated code and re-test in its own context. Say so explicitly in the comment rather than implying it's fully confirmed.
4. **Ready to Submit** — relabel `status:ready-to-submit`. Run lint + tests; confirm docs are up to date; post a summary comment. This is as far as *this* repo's own work can confirm the issue.
5. **Ready for Integration** (`cross-repo` issues that need consumer-side verification only — see
   "Who closes an issue" below for which issues that is) — once the fix is actually merged/pushed,
   relabel `status:ready-for-integration` instead of leaving it at `status:ready-to-submit`. This
   is the label that actually names the gap: this repo's own checks can confirm the fix works in
   isolation, but not that the originally reported symptom is resolved — that needs the consumer to
   pull the update and re-test in its own context. An issue with no such downstream dependency (a
   same-repo bug, nothing cross-repo) skips this stage entirely — `status:ready-to-submit` is
   already its terminal pre-close state.
6. **Done** — close the issue after merge. For a planned task, delete `tasks/<task-name>.md` once the issue is closed — the issue (body + comments) is the sole source of truth from that point on, so there's no reason to keep a stale duplicate on disk. (Only applies when a real issue holds the full history; a Done task with no issue keeps its local file.) Ad-hoc tasks have nothing to delete.

**Who closes an issue**: applies to issues opened "in the family" — by the repo owner themselves
(directly, or via a cross-repo issue from one of their own other repos) — the normal case before
this project has any external contributors. In that case, whoever opened it is the one who closes
it, not automatically whoever did the implementation work: leave it open (at
`status:ready-for-integration` once pushed, if it needed that stage; otherwise
`status:ready-to-submit`) and say so; don't close it, and don't use GitHub's auto-closing
commit-message keywords (`Closes #N`, `Fixes #N`, `Resolves #N`) for it, since those close on push
regardless of who's supposed to have that call — use a non-closing reference instead (`Ref #N`,
`Part of #N`, `Addresses #N`). This matters most for `cross-repo` issues diagnosed from a
consumer's own testing: the opener is the one positioned to actually verify the fix in that
original context, so closing is their call, not a mechanical side effect of merging. The one
exception even within the family: an issue Claude opened itself mid-task (e.g. a
`status:implementation` issue opened while executing a planned/ad-hoc task in the same session)
can be closed directly, since Claude is the opener there.

**If an issue ever comes from a genuine external contributor** (not the repo owner or one of their
own other repos), this whole rule doesn't apply — follow normal GitHub OSS etiquette instead
(auto-close via a merged PR's `Closes #N` is fine, maintainer discretion applies). Revisit this
section if/when that actually happens; it's not a case worth designing for speculatively before a
real external contributor shows up.

## Before committing

Run these before every commit:

```bash
ruff format src/ tests/
ruff check src/ tests/
pytest
```

## Documentation rule

After any change that affects the public interface, CLI, or file formats, update the relevant docs:

- `CLAUDE.md` — commands, architecture notes
- `docs/ARCHITECTURE.md` — modules, data flow, contracts
- `docs/PROTOCOL.md` — CLI signature, file format schemas

## Commands

```bash
# Install (editable, with dev deps)
pip install -e ".[dev]"

# Run
one-demo

# Lint
ruff check src/ tests/
ruff format src/ tests/

# Test
pytest
pytest tests/unit/test_foo.py::test_bar   # single test
```

## Architecture conventions

1. Internal processing uses strongly typed dataclasses.
2. `protocols.py` contains public contracts: persisted/shared data (dataclasses) *and* behavioral `Protocol`s meant for a consumer to actually implement/inject (e.g. `LoggingSink`, already scaffolded here — see the Logging section below). The distinction from `contracts.py` isn't data-vs-behavior, it's "does an external consumer implement this" vs. "does this only wire this project's own internals together": a behavioral `Protocol` belongs in `protocols.py` specifically when a host application is expected to supply its own implementation of it (most relevant once this project is consumed as a library by another project — see Architecture convention 8), not just when there's some internal data type to describe. Behavior that merely *operates on* a data contract still belongs in a dedicated entity/service layer, not on the dataclass itself. Keep any behavioral `Protocol` placed here leaf-safe (convention 9) — default parameter values like a category string should be literals, not imports from `diagnostics.py`, even where `diagnostics.py` already defines the same constant.
3. `contracts.py` contains runtime behavioral interfaces (`Protocol` classes for things like workers/executors) that wire this project's *own* internals together — never imported by external consumers, unlike `protocols.py`'s behavioral `Protocol`s above.
4. Unit tests (`tests/unit/`) must run offline. Integration tests (`tests/integration/`), if the project has them, may hit real external services — that's a deliberate scope split, not a loophole in rule 4. Note `pytest.ini`'s `testpaths = tests` runs both by default, so adding an integration suite means accepting network calls in the default `pytest` invocation unless you also gate it behind a marker.
5. Prefer explicit, readable Python over clever abstractions.
6. Prefer constructor/parameter injection over monkeypatching this project's own module internals in tests — e.g. a component that talks to the outside world (network, filesystem, clock) should take that dependency as an argument, defaulting to the real implementation, so tests can pass a fake object instead of patching a function inside the module under test. Monkeypatching is still the right tool for faking a *third-party* library's own internals (e.g. an HTTP client class you don't own) — the distinction is whether the thing being faked is your code or someone else's.
7. If a project ever grows beyond a single `src/<package_name>/` package (e.g. a shared framework package plus multiple CLI tools in one repo — an intentionally rare case, not the default shape), setuptools' src-layout automatic discovery picks up multiple packages under `src/` with no extra `[tool.setuptools]` config needed, as long as each has `__init__.py`. Don't pre-build this structure speculatively — it's here so you don't have to rediscover it if the need actually arrives. **If this repo is ever installed as a pip dependency of another project** (not just run standalone), any additional top-level package added this way needs a name specific enough not to collide with another project's own top-level package — a generic name (`shared`, `defs`, `client`, `utils`, ...) used as a *second, bare* top-level package is exactly the shape that caused a real, reproduced collision between two repos generated from this same template, each independently choosing the same generic names for their own "extra" packages (see croicu/quant-data#7: installing both into one environment made whichever installed last silently shadow the other's identically-named package entirely). Default to nesting the extra concern as a subpackage of your one namespaced package instead (`<package_name>.<subpackage>`) — only give it its own bare top-level name if it has no importable surface at all (e.g. a second console-script-only CLI in the same repo) or its own name is already specific enough to be practically collision-free.
8. **Curate a public API surface, separate from internal implementation.** Even a single-package project benefits from distinguishing "what's safe for another project to import" from "internal implementation, free to change" — don't rely on every symbol in every module being equally supported. Two mechanisms, pick based on need: **`__init__.py` re-exports** — list the actually-supported names in `__all__` and import them at the package root, so consumers write `from <package_name> import Thing` rather than reaching into a specific submodule; cheap, works even for a single-package project, and the re-export list itself documents the contract. **A private subpackage** (e.g. `<package_name>/_internal/`), if the internal implementation is substantial enough that "not in `__all__`" isn't a strong enough signal on its own — prefer this *nested* under your one namespaced package over a second bare top-level package (see rule 7's collision note); nesting also sidesteps a real circular-import failure mode documented in rule 9 below.
9. **Keep the internal dependency graph acyclic — break cycles with an abstract `Protocol`, not a runtime workaround.** If two concrete modules would otherwise need each other, introduce a `Protocol` (per rule 3's `contracts.py` convention) that one side depends on instead of the other's concrete type — this is the same seam rule 6's constructor-injection convention already creates, just framed as a graph property: depending on an abstraction instead of a concretion is what keeps the graph from looping back on itself. Verify this mechanically when it matters, not by feel: list every module's static top-level imports (`grep -E "^(from|import) " -r src/`) and confirm no module is reachable from itself by following them — a passing test suite is not proof the graph is acyclic, since import-order luck can mask a real cycle. A lazy/deferred import (e.g. a module-level `__getattr__`, PEP 562) can *mask* a cycle by moving it from import-time to call-time — that's a legitimate fallback for cases a `Protocol` genuinely can't reach (e.g. a package needing to re-export a name without owning the dependency direction), not the default fix. Reach for the `Protocol` first.

## Logging

- **Use `Logger`** (`from one_demo.diagnostics import Logger`) — not bare `print()`.
- **All features log success and errors** — no silent success, no swallowed errors.
- **Message length by severity**:
  - **Success (info)** — short: feature started, feature ended.
  - **Recoverable issues (warning)** — medium: enough context to understand what went wrong and why it was non-fatal.
  - **Errors (error/fatal)** — detailed: full context needed to reproduce and diagnose.
- **Level guide**:
  - `Logger.diagnostic` (`VERBOSE`) — one message per chunk of work, so a run's progress is visible and a hang is distinguishable from silence (e.g. a batch-processing loop logging one `VERBOSE` line per item it starts)
  - `Logger.info` — normal notable events (start, end, success, counts)
  - `Logger.warning` — recoverable problems (retries, skipped items)
  - `Logger.error` / `Logger.fatal` — unrecoverable failures
  - `Logger.perf(description, elapsed_seconds)` — duration markers for timing-sensitive spans
    (a network call, a slow query, anything worth measuring), always logged at `INFO` under a
    fixed category `perf` (`CATEGORY_PERF`, not the caller's choice — unlike every other `Logger`
    method). Message shape is `"duration: {elapsed:.3f}s - {description}"`. If this project is ever
    consumed as a library by another project, its own perf markers become visible to the host via
    the injectable `LoggingSink` `Protocol` (see `protocols.py` and the "Explicit DI First" rule
    under Coding Style) rather than a stdlib-`logging` bridge.
- **Categories** — every `Logger` method takes an optional `category: str = "general"`, filterable via `settings.json`'s `logCategories` (an open string, not a closed enum — `diagnostics.py` only defines `CATEGORY_GENERAL` as a starting constant). Console output is `[LEVEL][category] message`. **Effective default depends on whether `logLevel` is explicit** (see "Specific settings override generic ones on scope overlap" under Coding Style — this is that rule's origin case): if `settings.json`'s `logCategories` is left empty/absent, an explicit `logLevel` decides it outright — permissive (`verbose`/`info`/`warning`) resolves to `[]` (unfiltered), restrictive (`error`/`critical`) resolves to `["general"]` — regardless of `debug`. Only when `logLevel` is left at its implicit default does `debug` get consulted as the fallback (`debug: false` -> `["general"]`, `debug: true` -> `[]`). An explicit non-empty `logCategories` always overrides all of this outright. **`excludedCategories`** is a complementary deny-list, only in effect when the resolved `logCategories` is `[]` (the true unfiltered state) — inert against an explicit non-empty `logCategories` or the restrictive `["general"]` default.

## Coding Style

- **`protocols.py` holds public contracts, not implementations** — data (dataclasses, no methods) plus behavioral `Protocol`s meant for a consumer to implement/inject (e.g. `LoggingSink`). Either way, no concrete logic lives here — a dataclass has no behavior of its own (that lives in a separate entity/service layer), and a `Protocol`'s methods are signatures only (`...` bodies), never an implementation.
- **Explicit DI First** — when choosing between (a) integrating with an ambient/shared mechanism (stdlib `logging`, a service locator, a singleton registry) and (b) explicit constructor/parameter injection of an object matching a `Protocol`, default to (b), especially when the injected object can carry more capability through unmodified than the ambient mechanism would let you reconstruct on the other side. Concrete case: `LoggingSink` (see `protocols.py`) is an explicitly injected `Protocol`, not a bridge onto stdlib `logging.getLogger(...)` — a host's own `Logger` already has real behavior (category filtering, `excludedCategories`, level thresholds), and handing it through directly via DI preserves all of that with zero glue code, whereas a stdlib bridge would force reconstructing that behavior from `extra` fields and a logger-name convention on the consuming side. Don't assume "the idiomatic library pattern" (e.g. "real libraries use stdlib `logging`") automatically wins over this — capability-preserving DI is the default here even when a framework-level integration point already exists and would technically work.
- **Explicit over brief** — if two implementations are equivalent, choose the one that is easier to read and debug, even if it is longer.
- **No list/dict/set comprehensions** — use explicit `for` loops. Comprehensions obscure control flow and make multi-step logic harder to follow.
- **No lambdas** — use named functions or plain `for` loops. Lambdas hide intent and cannot be stepped through in a debugger.
- **Import count as SRP signal** — more than 5–10 imports in a file is a hint that the file may be doing too much. Not a hard rule, but worth pausing to consider whether responsibilities should be split.
- **Don't build a DI factory/composition-root prematurely** — the same wait-for-evidence judgment as the import-count signal applies to DI wiring. A function picking up its second or third injectable parameter (e.g. `main(argv, provider=None, settings_path=None)`) is not yet a smell; extracting a shared factory/helper from a single data point risks guessing at the wrong abstraction shape. Wait for real duplication — a second call site needing the same wiring, or a parameter list that's genuinely grown unwieldy — before extracting one.
- **Specific settings override generic ones on scope overlap** — when two configuration knobs can both influence the same outcome, the more specific/targeted one wins wherever they'd otherwise disagree, not the more generic/blanket one; the generic one only falls back into play when the specific one was left at its implicit default. Origin case: `settings.json`'s `logLevel` (a targeted verbosity control) vs. `debug` (a blanket flag) both used to influence the console log-category default, with `debug` winning outright — so setting `logLevel: "verbose"` alone did nothing, silently muted by `debug`'s separate default (see the Logging section above for the resulting behavior). Apply this whenever a new settings key's effect could overlap with an existing broader flag's — don't let a coarse toggle silently override an explicit, narrower setting the user actually configured.
- **Prefer a static/class method over a module-level function when it conceptually belongs to a class** — if a function's job is really about one class's own data or responsibility (parsing the file format that class owns, a helper only that class's methods call), attach it to the class as a `@staticmethod`/`@classmethod` rather than leaving it as a same-module function sitting beside the class. A dangling module-level function reads as either free-standing utility code or, worse, gets imported directly by outside callers, leaking an implementation detail the class was supposed to encapsulate. Origin case: `settings.py`'s `Settings._load_payload` (the `settings.json`/`settings.local.json` merge) started as a free function beside `Settings`, got imported directly by another module that needed one section of the merged settings, and was pulled inside the class as a private `@staticmethod` once that direct import was flagged as reaching past `Settings`'s own public surface (`Settings.section()`) into its internals.

## New Task

## Pending Tasks

## Completed Tasks
- **Backport: static-method encapsulation convention, and a channel for instances to backport
  template-inherited fixes** — [issue #7](https://github.com/croicu/tpl-py/issues/7), sourced from
  `geo-organizer` (since renamed to `desk-organizer`)'s own in-repo discovery while building an MCP
  server. `settings.py`'s `Settings` gained a private `@staticmethod` `_load_payload(path,
  local_path)` (the settings.json/settings.local.json merge logic, moved inside the class from a
  dangling module-level function) and a public `@classmethod` `section(name, path=..., local_path=
  ...) -> dict` — the general-purpose way for a caller outside `settings.py` to reach one named
  top-level section of settings.json without knowing how the file is read or merged. New Coding
  Style rule, "Prefer a static/class method over a module-level function when it conceptually
  belongs to a class," with that extraction as the origin case. New Template Sync subsection,
  "Porting an instance's improvement back to `tpl-py`" — the reverse channel of the addendum
  protocol: when a change made *in* an instance touches a template-inherited artifact and
  generalizes, open an issue here rather than waiting for the same fix to be rediscovered
  independently elsewhere; this issue was itself the first application of that new rule. Seventh
  addendum entry.
- **Backport DI-for-testability and process learnings from quant-scratch** — [issue #3](https://github.com/croicu/tpl-py/issues/3)
- **Backport public-surface, acyclic-dependency, and cross-repo learnings from quant-data** —
  [issue #4](https://github.com/croicu/tpl-py/issues/4). Architecture conventions 7-9 (namespace
  collision safety, curated public API surface, acyclic dependency graph) and a new opt-in
  `Cross-Repo Coordination` section. First real use of the addendum protocol (three entries under
  `addendum/`), since real instances (`quant-scratch`, `quant-data`) already exist and needed
  notifying rather than just having the base files changed underneath them.
- **Backport specific-overrides-generic settings precedence from quant-data** —
  [issue #5](https://github.com/croicu/tpl-py/issues/5), sourced from
  [croicu/quant-data#16](https://github.com/croicu/quant-data/issues/16). `settings.py`'s
  category-default resolution now lets an explicit `logLevel` override the blanket `debug` flag
  outright on disagreement; `diagnostics.py`'s `_LEVEL_RANK` made public (`LEVEL_RANK`); new
  Coding Style rule ("Specific settings override generic ones on scope overlap") plus a Logging
  section rewrite, including the previously-missing `Logger.diagnostic`/`VERBOSE` entry in the
  level guide. Fourth addendum entry.
- **Backport injectable `LoggingSink` + Explicit DI First rule; `ready-for-integration` issue
  workflow from quant-data** — [issue #6](https://github.com/croicu/tpl-py/issues/6), sourced from
  [croicu/quant-data#19](https://github.com/croicu/quant-data/issues/19) and
  [#20](https://github.com/croicu/quant-data/issues/20). `diagnostics.py` gained
  `Logger.perf(description, elapsed_seconds)`/`CATEGORY_PERF`; `protocols.py` gained a
  `LoggingSink(Protocol)` mirroring `DiagnosticsLogSink`'s method surface, so any instance's own
  `Logger` already satisfies it structurally, ready to inject the moment a public
  constructor/factory needs one. Architecture conventions 2/3 reworded: `protocols.py`'s scope is
  now public contracts generally (data *or* behavioral-`Protocol`s-for-injection), distinguishing
  from `contracts.py` by public-vs-private rather than data-vs-behavior. New Coding Style rule,
  "Explicit DI First" — prefer injecting a `Protocol`-typed object over bridging into an ambient
  mechanism (stdlib `logging`, a service locator) when the injected object preserves more
  capability; this was the actual reasoning behind choosing `LoggingSink` over a stdlib-`logging`
  bridge. Also: new `status:ready-for-integration` label/stage and a "Who closes an issue" rule in
  the Task workflow section — whoever opened an issue closes it (not automatically whoever
  implemented the fix), prompted by two quant-data issues that got auto-closed via `Closes #N`
  before the reporter (who'd diagnosed them from a different, consumer repo) had actually verified
  the fix end-to-end. Fifth and sixth addendum entries.
