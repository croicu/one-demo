# Specific settings override generic ones on scope overlap; new Coding Style rule

**Source**: [croicu/quant-data](https://github.com/croicu/quant-data) — see
[croicu/quant-data#16](https://github.com/croicu/quant-data/issues/16) for the full history.

## What changed

`CLAUDE.md`'s Coding Style section gained a new rule: when two configuration knobs can both
influence the same outcome, the more specific/targeted one wins wherever they'd otherwise
disagree, not the more generic/blanket one — the generic one only falls back into play when the
specific one was left at its implicit default.

The origin case is fixed directly in `settings.py`/`diagnostics.py`: `Settings.load`'s
log-category default used to be governed entirely by `debug` (`debug: false` -> `["general"]`
only, `debug: true` -> unfiltered), completely independent of `logLevel`. `diagnostics.py`'s
`_LEVEL_RANK` is renamed to `LEVEL_RANK` (made public) so `settings.py` can compare levels. Also:
the Logging section's level guide was missing `Logger.diagnostic` (`VERBOSE`) entirely — added,
described as one message per chunk of work so a run's progress is distinguishable from a hang.

## Why

Setting `settings.json`'s `logLevel: "verbose"` alone did nothing — the category filter still
defaulted to `["general"]` unless `debug` was *also* separately flipped to `true`, since the two
settings' effects on the category default were only ever wired through `debug`. This was
surprising enough in practice (adding a new `VERBOSE`-level log line, then setting `logLevel:
"verbose"` to see it, and seeing nothing) to be worth fixing at the root rather than patching the
one instance: `logLevel` is a targeted, purpose-built verbosity control; `debug` is a coarse,
general-purpose toggle. A user who explicitly sets the specific control has already answered the
question the generic one was being consulted for — letting the generic one silently override that
explicit, narrower intent is the actual bug, and the same shape of bug can recur anywhere a new
settings key's effect overlaps an existing broader flag's, not just here.

## What an instance should do

- If you've generated a project from this template and haven't touched `settings.py`/
  `diagnostics.py`'s logging internals, this addendum's changes are a straight drop-in — no
  local adaptation needed.
- If you've added your own settings keys since generating, check whether any of them overlaps in
  effect with an existing broader flag (the same shape as `logLevel`/`debug` here). If so, apply
  the same precedence: the more specific key should win outright when explicitly set, with the
  generic one only as a fallback for when the specific one was left at its default — not the
  other way around.
- If your project's `settings.py` has diverged further from this template's version (e.g.
  `quant-data`'s own copy has extra fields like `tickers`/`startDate`/`catchUpLookbackDays`), port
  just the `expand_categories` logic and the `LEVEL_RANK` rename — the rest of your local
  divergence doesn't need to change.
