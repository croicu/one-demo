You turn one past production incident into a reusable lesson: a short Markdown document that a code
scanner will apply to code that hasn't failed yet. The lesson must describe the failure mechanism
in general terms, so it catches the same gap in other teams' code, not only in the code that failed.

# The incident

{{incident}}

# The fix (diff of the source files it changed)

```diff
{{diff}}
```

# What to write

Write the lesson in exactly this format. Replace everything in angle brackets; keep every heading.

```markdown
# Lesson: <one line naming the gap>

- **Id:** `<short-kebab-case-id>`
- **Status:** draft

## Mechanism

<How the failure happens, in general terms: what the code does, under which circumstances it turns
into an incident, and why. A few sentences.>

## Shape

<What the risky code looks like. The shape alone is never a finding; the conditions decide.>

## Candidates

<One sentence: which methods the scanner should hand to the judge.>

- Files: `<file glob, e.g. *.cs>`
- `<regular expression>` (<what it finds>)
- `<regular expression>` (<what it finds>)

## Dangerous when

- **<ID>. <condition>.** <What it means and how to tell from the code.>

## Harmless when

- **<ID>. <condition>.** <What it means and how to tell from the code.>

## When the deciding fact is missing

<What to conclude when the code doesn't show whether a condition holds.>

## Decision

<One sentence: the checked conditions are ..., each holds, fails or unknown; the first matching rule
decides.>

1. <ID> holds → flag (<IDs this verdict names>)
2. <ID> fails → clear (<IDs>)
3. otherwise → flag (<IDs>)

## Fix

<What the code should do instead, with a short before/after code example.>

## Source

<Two or three sentences: what happened in the incident and how the fix shows the mechanism.>
```

Rules:

- **Candidates:** every pattern must match a method body, which the scanner reads with strings and
  comments removed. A method is a candidate when its body matches all the patterns. Keep them loose:
  a false candidate costs one judgment, a missed one is a missed incident. Write each pattern as a
  Python regular expression inside single backticks.
- **Conditions:** give each a short ID (for example D1, D2 for dangerous, H1, H2 for harmless) and
  make each one checkable from code a reviewer can see. A harmless condition that is simply a
  dangerous one failing doesn't need its own check: name it in the Decision rule that clears.
- **Decision:** numbered rules, each exactly `<ID> holds → flag|clear (<IDs>)` or
  `<ID> fails → flag|clear (<IDs>)`, with the arrow `→`, applied in order. The last rule must be
  `otherwise → flag|clear (<IDs>)`. Every ID a rule tests must be defined above. Decide what an
  `unknown` check means by the order of the rules: an unknown matches neither holds nor fails.
- **Keep the mechanism, drop the circumstances.** Derive the conditions from what the fix changed.
  A property of the failing code that the fix left alone is incidental to this incident and must not
  become a condition: if the fix changed one aspect of a behavior and kept another as it was, the one
  it kept is not what made the code dangerous. State each condition at the
  level where the same failure would recur in different code; if a narrower wording would miss the
  same mechanism elsewhere, it is too narrow.
- **No team-specific facts.** The lesson applies to everyone; a fact true for one team belongs in
  that team's code (for example a doc comment), never in the lesson.
- Reply with the lesson only: no preamble, no closing remarks.
