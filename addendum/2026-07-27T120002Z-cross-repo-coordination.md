# Cross-repo coordination workflow (new, opt-in section)

**Source**: [croicu/quant-data](https://github.com/croicu/quant-data) — see its `CLAUDE.md`'s
`Cross-Repo Coordination` section for the fully-worked example this generalizes from.

## What changed

A new, opt-in `Cross-Repo Coordination` section added to `CLAUDE.md`, for once an instance has a
real data/API contract with another repo (a producer/consumer relationship — not just "both repos
exist"). Covers: a placement rule for where a cross-repo issue lives, a cheap heuristic for
deciding whether a given change needs one at all (reusing the public-surface boundary from the
"curate a public API surface" addendum entry instead of re-deriving it each time), labeling/linking
conventions, and an explicit note not to build multi-consumer fan-out process ahead of a second
real consumer.

## Why

`quant-data` (producer) and `quant-scratch` (consumer) are two instances of this template with a
real, ongoing contract between them — schema/API changes on one side need the other side to react.
Coordinating this via ad-hoc conversation or a shared doc doesn't scale past the first change;
`quant-data` settled on GitHub issues, cross-linked, labeled `cross-repo`, with a placement rule
(the issue lives wherever the *actionable follow-up* happens, not where the need originated) and a
cheap "does this even need one" check tied directly to its public/private package boundary — code
that isn't part of the curated public surface can't have broken a consumer's import, so it doesn't
need an announcement unless it changed observable behavior some other way (e.g. a bug fix that
changes what a public function returns).

This is genuinely conditional, unlike most of `CLAUDE.md`'s other sections: a single-repo instance,
or one with no real contract to another repo, doesn't need this at all, and shouldn't have it
sitting in `CLAUDE.md` unused. Same judgment call as rule 7's multi-package case, or the
"don't build a DI factory prematurely" note under Coding Style — build the process when the need is
real, not ahead of it.

## What an instance should do

- If this repo has (or is gaining) a real producer/consumer relationship with another repo: add a
  `Cross-Repo Coordination` section to `CLAUDE.md`, adapted from `quant-data`'s version — the
  placement rule, the "does this need an issue" heuristic tied to your own public-surface
  boundary, the `cross-repo` label convention (create the label if it doesn't exist yet), and the
  cross-linking requirement.
- Don't add this section speculatively if there's no such relationship yet — it's opt-in scaffolding
  for a specific situation, not default process.
- If a second real consumer repo arrives later: that's the trigger to extend the section with a
  consumer registry, fan-out-on-breaking-changes, and a rollout-tracking issue — not before. See
  `quant-data`'s own `CLAUDE.md` for a worked-out version of that extension, written but
  deliberately not built out until/unless it's needed.
