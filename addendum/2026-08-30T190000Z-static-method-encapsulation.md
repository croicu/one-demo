# Static-method encapsulation convention; a channel for instances to backport template-inherited fixes

**Source**: [croicu/desk-organizer](https://github.com/croicu/desk-organizer) (named
`geo-organizer` at the time) — see
[croicu/tpl-py#7](https://github.com/croicu/tpl-py/issues/7) for the full history.

## What changed

`settings.py`'s `Settings` gains a private `@staticmethod` `_load_payload(path, local_path) ->
dict` — the settings.json/settings.local.json merge logic, moved inside the class from a dangling
module-level shape it would otherwise have taken — and a public `@classmethod` `section(name,
path=..., local_path=...) -> dict`, the general-purpose way for a caller outside `settings.py` to
reach one named top-level section of settings.json (merged with settings.local.json's override)
without knowing how the file is read or merged. `section()` raises `TaskError` if the named
section isn't a JSON object, matching `load()`'s existing validation style.

`CLAUDE.md` gains two things:

- A new Coding Style rule, **"Prefer a static/class method over a module-level function when it
  conceptually belongs to a class"** — if a function's job is really about one class's own data or
  responsibility, attach it to the class rather than leaving it as a same-module function beside
  it. A dangling module-level function reads as either free-standing utility code or, worse, gets
  imported directly by outside callers, leaking an implementation detail the class was supposed to
  encapsulate.
- A new Template Sync subsection, **"Porting an instance's improvement back to `tpl-py`"** — the
  reverse channel of the addendum protocol. `tpl-py` pushing a change out to instances was already
  documented; the other direction wasn't. When a change made *in* an instance touches a
  template-inherited artifact (a class the instance started with from `tpl-py`'s scaffolding, or a
  markdown file `tpl-py` itself authors) and the change is generalizable rather than specific to
  that instance's own domain, the instance should open an issue in `croicu/tpl-py` describing the
  change and cross-linking back, rather than waiting for the same fix to be rediscovered
  independently in another instance later (the pattern issues #3–#6 already followed, but starting
  from a sibling instance's report rather than the instance's own in-repo discovery).

## Why

`geo-organizer` needed a settings.json/settings.local.json merge helper reused by two call sites
(`Settings.load()` and a new `Settings.section(name)` accessor added for an MCP server's own
config section). It was first extracted as a free function sitting beside the `Settings` class,
then pulled inside the class as a private `@staticmethod` once flagged as leaking an
implementation detail past the encapsulation `Settings` was supposed to own. That reaction
generalizes to a rule worth stating explicitly rather than rediscovering per-instance.

Separately, this was the first time an instance needed to push a change back to `tpl-py` starting
from its own in-repo discovery, rather than the change being noticed first in a sibling instance
and reported from there (the shape issues #3–#6 all took). The addendum protocol only documented
the `tpl-py` → instance direction; the reverse wasn't written down anywhere, so there was no
standing expectation that an instance should proactively open a backport issue on its own — worth
fixing now so every future instance inherits the expectation rather than rediscovering it.

## What an instance should do

- If you've generated a project from this template and haven't touched `settings.py`'s merge
  logic, this addendum's `settings.py` change is a straight drop-in — no local adaptation needed.
- If your project already has its own `Settings.section()`-shaped accessor (e.g. any instance that
  built an MCP server or plugin needing its own settings.json section before this addendum
  existed), diff your version against this one — the shape should already match; if it diverged
  independently, converge on this one's method names (`_load_payload`, `section`) for consistency
  across instances.
- Going forward, apply the new "Porting an instance's improvement back to `tpl-py`" protocol
  yourself: if you touch a template-inherited class or `tpl-py`-authored markdown file in a way
  that generalizes beyond your own domain, open the backport issue from your own repo rather than
  waiting for someone else to notice.
