You wrote the draft lesson below from a past production incident. Before a lesson goes to production,
it must reach the right verdict on labeled examples: code whose right answer is known. Your draft
failed some of them. Revise the lesson so it gets them right.

# The incident

{{incident}}

# The fix (diff of the source files it changed)

```diff
{{diff}}
```

# Your draft

{{draft}}

# The examples it got wrong

{{failures}}

# How to revise

- Find the **general** reason behind each failure: a missing condition, a condition that is too
  strict or too loose, a rule in the wrong order, candidate patterns that miss the code. Fix the
  lesson for that reason. Never mention the examples, their class or method names, or special-case
  them: the lesson must work on code nobody has labeled.
- Keep everything that already works: the examples that passed must still pass.
- Keep the exact format: every heading, `- **Id:**` unchanged, the `## Candidates` list
  (`- Files: ...` and one backticked regular expression per line), and the `## Decision` rules, each
  `<ID> holds → flag|clear (<IDs>)` or `<ID> fails → flag|clear (<IDs>)`, ending with
  `otherwise → flag|clear (<IDs>)`. Every ID a rule tests must be defined above it.
- Leave the `## Source` section as it is.
- Reply with the revised lesson only: no preamble, no list of changes.
