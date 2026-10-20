# `status:ready-for-integration` label; "Who closes an issue" rule

**Source**: [croicu/quant-data](https://github.com/croicu/quant-data) — see
[croicu/quant-data#19](https://github.com/croicu/quant-data/issues/19) and
[#20](https://github.com/croicu/quant-data/issues/20) for the incident that prompted this.

## What changed

`CLAUDE.md`'s Task workflow section:

- New label `status:ready-for-integration`, and a new stage 5 between "Ready to Submit" and
  "Done": for a `cross-repo` issue that needs consumer-side verification, relabel to
  `status:ready-for-integration` once the fix is actually merged/pushed, instead of treating
  `status:ready-to-submit` as the terminal pre-close state. An issue with no cross-repo downstream
  dependency skips this stage — `status:ready-to-submit` stays terminal for it.
- The Testing stage now says explicitly: for a `cross-repo` issue diagnosed from a consumer's own
  testing, this repo's own verification (even a live check against a real external dependency)
  confirms the fix in isolation, not that the originally reported symptom is resolved — say so in
  the comment rather than implying full confirmation.
- New **"Who closes an issue"** rule: for issues opened "in the family" (by the repo owner
  themselves, directly or via a cross-repo issue from one of their own other repos) — the normal
  case before a project has real external contributors — whoever opened the issue is the one who
  closes it, not automatically whoever did the implementation work. Concretely: leave the issue
  open once the fix is pushed (at `status:ready-for-integration` if it needed that stage,
  `status:ready-to-submit` otherwise) and say so in a comment; don't close it; don't use GitHub's
  auto-closing commit-message keywords (`Closes #N`, `Fixes #N`, `Resolves #N`) for it, since those
  close on push regardless of who's supposed to have that call — use a non-closing reference
  instead (`Ref #N`, `Part of #N`, `Addresses #N`). One exception even within the family: an issue
  Claude opened itself mid-task can be closed directly, since Claude is the opener there. If an
  issue ever comes from a genuine external contributor, this whole rule doesn't apply — normal
  GitHub OSS etiquette (auto-close via a merged PR) is fine there instead.

## Why

Two issues (#19, #20) were opened by the repo owner from testing done in a *different* repo
(`quant-scratch`) than the one being fixed (`quant-data`). The fixing work happened, was verified
locally against a real external dependency, and got pushed with a `Closes #N`-style commit
message — auto-closing both issues on merge, before the repo owner had actually synced the
consumer repo to the fix and confirmed the originally-reported symptom (a ~130s stall; invisible
internal logging) was actually gone in that original context. Local verification in the producer
repo is necessary but not sufficient proof for a bug that was only ever observed from the consumer
side — closing on push conflated "our own checks pass" with "the reporter has confirmed this is
actually fixed," which are different moments whenever the issue crossed a repo boundary.

## What an instance should do

- If this repo doesn't have any `cross-repo` relationship yet (see the opt-in "Cross-Repo
  Coordination" section), none of this is live yet — it becomes relevant the same moment that
  section does.
- Once it does apply: create the `status:ready-for-integration` label (`gh label create`) the
  first time an issue actually needs it, same as any other `status:*` label.
- Stop using `Closes #N`/`Fixes #N`/`Resolves #N` in commit messages for any issue you didn't open
  yourself — use `Ref #N` or similar instead, and let the actual opener close it once they've
  verified.
