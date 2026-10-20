# one-demo

Turns a past incident into a reviewed lesson, then scans code for the same gap, citing the incident
behind every finding.

This demo learns one lesson from a public Microsoft fix,
[microsoft/azure-pipelines-agent PR #5448](https://github.com/microsoft/azure-pipelines-agent/pull/5448):
the Azure Pipelines agent retried its connection to the server on a fixed 30-second beat, and every
retry added load to a server that was already struggling. The fix made the wait grow. The lesson is
then applied to different code, in [croicu/one-demo-sample-cs](https://github.com/croicu/one-demo-sample-cs),
and the real finding is filed there as an issue that links the incident.

## The demo

| # | Step | Command |
|---|---|---|
| 1 | Scan before learning: nothing to report, because the scanner only speaks when it can cite an incident | `one-demo scan ../one-demo-sample-cs` |
| 2 | Learn: a model reads the incident and drafts a lesson and its tests | `one-demo learn incidents/azure-pipelines-agent-5448` |
| 3 | Review: scan with the draft lesson | `one-demo scan ../one-demo-sample-cs --review` |
| 4 | Adjust: a reviewer adds what the incident couldn't teach (snippets in `lessons/drafts/snippets/`) | edit the draft in `lessons/drafts/` |
| 5 | Approve: the lesson's tests must pass; then the reviewed code is scanned again, the findings are listed, and after confirmation filed as issues | `one-demo approve lessons/drafts/<lesson>.md` |
| 6 | Scan in production: the finding is already tracked | `one-demo scan ../one-demo-sample-cs` |

If a draft fails its tests in step 5, `one-demo learn --revise lessons/drafts/<lesson>.md` sends the
failures back to the teacher, which rewrites the draft; the previous version is kept in
`lessons/drafts/history/`.

## How it works

- **A lesson is a Markdown file** (`lessons/<id>.md`): the failure mechanism, when it is dangerous,
  when it is harmless, the fix, and the incident it came from.
- **Each lesson carries its own cheap query** (its `## Candidates` section): the patterns a method
  must match to be looked at. The scanner itself knows no patterns, so with no lessons it finds
  nothing to check.
- **A model checks each condition** of the lesson against the code, citing file and line. The
  verdict is not the model's: it is derived from those checks by the lesson's `## Decision` rules.
- **No lesson reaches production untested.** Its labeled examples (from the incident's own code
  before the fix, plus hand-labeled cases) must all come out right before `approve` moves it live.
- **Findings go where the code lives:** one issue per lesson and method in the scanned repository,
  with the evidence linked at the scanned commit. The scanner opens issues; closing them is the
  team's call.

## Running it

Open this repository in a GitHub Codespace (Code → Codespaces → Create codespace). The container
installs the tool and clones the sample repository next to it. Then add your own OpenAI API key:

```bash
cp settings.local.example.json settings.local.json   # then put your key in it
```

`settings.local.json` is gitignored: your key stays in your codespace. A full run of the demo costs a
few cents (the model is `gpt-6.1-sol`).

Filing issues needs write access to the scanned repository's issues; the codespace asks for it on
`croicu/one-demo-sample-cs` when it is created.

## Commands

```bash
one-demo scan <folder> [--review] [--issues] [--summary report.md]
one-demo learn <incident packet> | --revise <draft>
one-demo approve <draft> [--yes]
python tools/build_incident_packet.py <owner/repo> <pr> incidents/<name>   # save another incident
pytest                                                                       # offline tests
```
