---
marp: true
paginate: true
---

# Learning from a past incident

A lesson learned from a past production fix, tested, and applied to code that hasn't failed yet.
Every finding cites the incident behind it.

`one-demo` · step by step

---

## The incident

**[microsoft/azure-pipelines-agent PR #5448](https://github.com/microsoft/azure-pipelines-agent/pull/5448)**: the
agent that runs on every self-hosted build machine.

> "When the server is unavailable … the agent continuously retries the request indefinitely. Each
> retry invokes the OAuth token provisioning mechanism on the server … This behavior significantly
> increases load on an already unavailable server."

```diff
-            await HostContext.Delay(TimeSpan.FromSeconds(30), token);
+            await HostContext.Delay(_keepAliveRetryInterval, token);
```

Before: every agent retried on the same 30-second beat. After: the wait grows while failures last.

---

## The loop

```
incident  →  learn  →  review  →  adjust  →  approve  →  scan
 (a fix)    (draft     (scan      (a person   (tests,     (findings
            lesson)    with the   adds what   then file   filed where
                       draft)     it missed)  issues)     the code is)
```

- A **lesson** is a Markdown file: the mechanism, when it is dangerous, when it is harmless, the fix,
  and the incident it came from.
- The code it is applied to: [croicu/one-demo-sample-cs](https://github.com/croicu/one-demo-sample-cs),
  a few ordinary service components that call other services and retry on failure.

---

## Step 1: scan before learning

```
$ one-demo scan ../one-demo-sample-cs
No approved lessons: nothing to check, so nothing to report.
```

The scanner knows no patterns of its own. Each lesson carries the query that selects the code it
applies to; with no lessons, nothing is even looked at.

**It only speaks when it can cite an incident.**

---

## Step 2: learn

```
$ one-demo learn incidents/azure-pipelines-agent-5448
Draft lesson: lessons/drafts/nonprogressive-failure-retries.md
Its tests:    lessons/drafts/nonprogressive-failure-retries.tests.json
Checks passed.
```

A model reads the saved incident (the description and the fix, never fetched live) and drafts:

- the **mechanism**: failed remote work retried without the delay growing
- **candidates**: the patterns that select methods to look at
- **conditions** and **decision rules**: when the lesson flags, when it clears

Deterministic checks before anyone reads it: it parses, it cites its incident, and its patterns
find the method the incident shows failing. (~40 s)

---

## Step 3: review

```
$ one-demo scan ../one-demo-sample-cs --review
REVIEW: judging with draft lessons, not yet approved.
WARNING  InventoryClient.GetStockAsync
WARNING  ReconciliationJob.GetOpenBatchAsync
WARNING  StatusMonitor.GetStatusAsync
cleared  UserSettings.MoveIntoPlace
3 warning(s), 1 cleared
```

| Warning | Right? |
|---|---|
| The inventory client: every request retries a shared service on a fixed 2 s beat | ✅ real |
| A scheduled job documented to run as a single instance | ❌ the draft ignores the documentation |
| A monitor polling an agent on its own host (`127.0.0.1`) | ❌ a local target can't be stormed by a fleet |

---

## Step 4: adjust

The incident was about one shared server. It never mentions documented single instances or local
targets, so the model couldn't learn them. A reviewer adds them, in the lesson:

```markdown
- **H-DOC. The code documents that it runs as a single instance.** A `///` doc comment
  on the method, its class, or a base class states that this code runs once fleet-wide …
- **H-LOCAL. The retried target is local to the host.** A loopback address, a local
  file or device, or an in-process resource …

1. H-DOC holds → clear (H-DOC)
1. H-LOCAL holds → clear (H-LOCAL)
```

The code isn't touched: the team's fact (the doc comment) was already there. **Two ways to fix a
finding: fix the code, or fix the lesson.**

---

## Step 5: approve

```
$ one-demo approve lessons/drafts/nonprogressive-failure-retries.md
pass  The incident: keep-alive retried every 30 s
pass  The incident: session creation retried every 30 s
pass  Same file: message polling, which can fall into the fixed 30 s session recovery
pass  Fleet client: per-request retry of a shared remote API
pass  Local poll loop: retries a loopback agent
pass  Scheduled job, instance count undocumented
pass  Scheduled job, documented as one replica fleet-wide
APPROVED  7/7 tests passed

Re-scanning ../one-demo-sample-cs with the approved lesson...
1 warning(s), 3 cleared
1 new issue(s) to file in croicu/one-demo-sample-cs:
  - Retry delays that do not grow during sustained failures: InventoryClient.GetStockAsync
File them? [y/N] y
Filed: https://github.com/croicu/one-demo-sample-cs/issues/2
```

**No lesson reaches production untested:** labeled examples from the incident's own code before the
fix, plus hand-labeled cases. Any failure keeps the lesson in review. (~50 s)

---

## What the team receives

**Retry delays that do not grow during sustained failures: `InventoryClient.GetStockAsync`**

> Failed inventory requests are retried at a fixed two-second cadence; limiting each call to five
> attempts does not provide progressive backoff. Track consecutive failures and increase the
> cancellable delay toward a bounded maximum, resetting the streak after success.

- **Evidence**, linked at the scanned commit: `RetryDelay = TimeSpan.FromSeconds(2)`, the retry
  loop, the remote call, the catch.
- **Why this matters:** the same gap caused the Azure Pipelines agent incident (PR #5448).
- **To resolve:** fix the code, or document the fact that makes it safe, so the next scan clears it.

The scanner opens issues; closing them is the team's call.

---

## Step 6: scan in production

```
$ one-demo scan ../one-demo-sample-cs --issues
WARNING  InventoryClient.GetStockAsync
cleared  UserSettings.MoveIntoPlace
cleared  ReconciliationJob.GetOpenBatchAsync   [H-DOC]
cleared  StatusMonitor.GetStatusAsync          [H-LOCAL]
1 warning(s), 3 cleared
Already tracked (open issue): InventoryClient.GetStockAsync
```

A single incident's lesson, applied to different code in another repository: the real gap is found
and tracked, the harmless lookalikes are cleared with the reason stated.

---

## How it stays honest

- **The scanner knows no patterns.** Each lesson brings its own query, drafted by the model and
  reviewed by a person.
- **The verdict isn't the model's.** The model checks each condition and cites file and line; the
  lesson's decision rules turn those checks into the verdict.
- **Every citation is verified** against the code, and every finding links its incident.
- **No lesson ships untested,** and a failed test is fixed in the lesson or, when the label was
  wrong, in the label. In rehearsal a learned lesson caught a path our own label had missed.
- **The model learns what the incident says, not what we know.** What an incident can't teach is
  added by a reviewer, visibly.

---

## What this doesn't prove

- **Precision.** A single incident and a single sample repository show the mechanism, not how often a lesson
  is right. That needs many labeled incidents and held-out examples: a backtest with a precision bar
  before any lesson ships.
- **Unfamiliar lessons.** Retries without backoff are well-known practice; a model knows them
  already. The value grows with lessons a model can't know: failures specific to a system, a team,
  or an internal API.

---

## Try it

1. Open [croicu/one-demo](https://github.com/croicu/one-demo) in a GitHub Codespace. The container
   installs the tool and clones the sample repository next to it.
2. `cp settings.local.example.json settings.local.json` and add your own OpenAI API key (gitignored;
   it stays in your codespace).
3. Run the steps above. A full run takes a few minutes and costs a few cents.

```
one-demo scan <folder> [--review] [--issues]
one-demo learn <incident packet> | --revise <draft>
one-demo approve <draft>
```
