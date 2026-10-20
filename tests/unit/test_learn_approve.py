import json
from pathlib import Path

from one_demo.cli import main

CODE = """namespace Shop;

public sealed class Client
{
    public async Task KeepAliveAsync()
    {
        while (true)
        {
            try { await _http.GetAsync("ping"); }
            catch (HttpRequestException) { }
            await Task.Delay(30000);
        }
    }

    public async Task PollAsync()
    {
        while (true)
        {
            try { await _http.GetAsync("poll"); return; }
            catch (HttpRequestException) { await Task.Delay(Random.Shared.Next(15000, 30000)); }
        }
    }
}
"""

DRAFT = r"""# Lesson: retries that never back off

- **Id:** `never-backs-off`
- **Status:** draft

## Mechanism

Clients retry a remote call on a fixed beat.

## Candidates

- Files: `*.cs`
- `\bwhile\b` (a loop)
- `\bDelay\b` (that waits)

## Decision

1. D1 fails → clear (D1)
2. otherwise → flag (D1)

## Source

The keep-alive retried every 30 seconds.
"""

PATTERNLESS_DRAFT = DRAFT.replace("- `\\bwhile\\b` (a loop)\n- `\\bDelay\\b` (that waits)\n", "- `\\bNeverMatches\\b`\n")


class FixedClient:
    """A teacher that always answers with the same text."""

    def __init__(self, content):
        self.content = content
        self.prompts = []

    def list_models(self):
        return []

    def chat(self, model, messages, temperature=None, json_mode=False):
        from one_demo.model_types import ChatReply

        self.prompts.append(messages[0].content)
        return ChatReply(content=self.content, model=model, prompt_tokens=10, completion_tokens=5)


class VerdictClient:
    """A judge whose D1 check holds or fails per subject."""

    def __init__(self, holds_by_subject):
        self.holds_by_subject = holds_by_subject
        self.subjects = []

    def list_models(self):
        return []

    def chat(self, model, messages, temperature=None, json_mode=False):
        from one_demo.model_types import ChatReply

        prompt = messages[0].content
        for subject, holds in self.holds_by_subject.items():
            if f"`{subject}`" in prompt:
                self.subjects.append(subject)
                state = "holds" if holds else "fails"
                reply = {
                    "evidence": ["Client.cs:11"],
                    "checks": {"D1": f"{state}: Client.cs:11"},
                    "reason": "Because.",
                    "verdict": "flag" if holds else "clear",
                }
                return ChatReply(content=json.dumps(reply), model=model, prompt_tokens=10, completion_tokens=5)
        raise AssertionError("unexpected subject")


class Factory:
    def __init__(self, client):
        self.client = client

    def __call__(self, provider, settings_path):
        return self.client


def _workspace(tmp_path):
    packet = tmp_path / "incidents" / "pr-1"
    (packet / "before").mkdir(parents=True)
    (packet / "before" / "Client.cs").write_text(CODE, encoding="utf-8")
    (packet / "incident.json").write_text(
        json.dumps({"title": "Back off the keep-alive", "url": "https://example.test/pr/1", "diff_url": "https://example.test/pr/1/files"}),
        encoding="utf-8",
    )
    (packet / "incident.md").write_text("# Back off the keep-alive\n\nIt retried every 30 s.\n", encoding="utf-8")
    (packet / "fix.diff").write_text("-await Task.Delay(30000);\n+await Task.Delay(next);\n", encoding="utf-8")
    labels = {
        "tests": [
            {
                "name": "keep-alive",
                "source": "incident",
                "subject": "Client.KeepAliveAsync",
                "expected": "flag",
                "files": [{"path": "before/Client.cs", "showAs": "Client.cs"}],
            },
            {
                "name": "polling",
                "source": "incident",
                "subject": "Client.PollAsync",
                "expected": "clear",
                "files": [{"path": "before/Client.cs", "showAs": "Client.cs"}],
            },
        ]
    }
    (packet / "labels.json").write_text(json.dumps(labels), encoding="utf-8")
    lessons = tmp_path / "lessons"
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "settings": {
                    "logLevel": "error",
                    "learn": {"provider": "fake"},
                    "scan": {"provider": "fake"},
                    "fake": {"baseUrl": "http://fake/v1", "model": "m"},
                }
            }
        ),
        encoding="utf-8",
    )
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "learn.md").write_text("LEARN {{incident}} {{diff}}", encoding="utf-8")
    (prompts / "revise.md").write_text("REVISE {{draft}} FAILURES {{failures}}", encoding="utf-8")
    (prompts / "judge.md").write_text("{{lesson}} SUBJECT `{{subject}}` {{conditions}} {{files}}", encoding="utf-8")
    return packet, lessons, settings, prompts


def _main(args, settings, prompts, client):
    return main(
        args,
        settings_path=settings,
        client_factory=Factory(client),
        prompt_path=prompts / "judge.md",
        learn_prompt_path=prompts / "learn.md",
        revise_prompt_path=prompts / "revise.md",
    )


def test_learn_writes_a_draft_with_its_tests_and_the_incident_link(tmp_path, capsys):
    packet, lessons, settings, prompts = _workspace(tmp_path)
    teacher = FixedClient("```markdown\n" + DRAFT + "```")

    exit_code = _main(["learn", str(packet), "--lessons", str(lessons)], settings, prompts, teacher)

    draft = lessons / "drafts" / "never-backs-off.md"
    tests = json.loads((lessons / "drafts" / "never-backs-off.tests.json").read_text(encoding="utf-8"))
    text = draft.read_text(encoding="utf-8")
    assert exit_code == 0
    assert "It retried every 30 s." in teacher.prompts[0]
    assert not text.startswith("```")
    assert "**Incident:** [Back off the keep-alive](https://example.test/pr/1)" in text
    assert tests["packet"] == packet.as_posix()
    assert len(tests["tests"]) == 2
    assert tests["tests"][0]["files"][0]["path"] == (packet / "before/Client.cs").as_posix()
    assert "Checks passed" in capsys.readouterr().out


def test_learn_flags_a_draft_whose_patterns_miss_the_failing_method(tmp_path, capsys):
    packet, lessons, settings, prompts = _workspace(tmp_path)

    exit_code = _main(["learn", str(packet), "--lessons", str(lessons)], settings, prompts, FixedClient(PATTERNLESS_DRAFT))

    text = (lessons / "drafts" / "never-backs-off.md").read_text(encoding="utf-8")
    assert exit_code == 1
    assert text.startswith("> **The teacher's checks failed")
    assert "don't select Client.KeepAliveAsync" in capsys.readouterr().out


def test_approve_moves_the_lesson_live_when_all_tests_pass(tmp_path, capsys):
    packet, lessons, settings, prompts = _workspace(tmp_path)
    _main(["learn", str(packet), "--lessons", str(lessons)], settings, prompts, FixedClient(DRAFT))
    judge = VerdictClient({"Client.KeepAliveAsync": True, "Client.PollAsync": False})

    exit_code = _main(["approve", str(lessons / "drafts" / "never-backs-off.md"), "--lessons", str(lessons)], settings, prompts, judge)

    assert exit_code == 0
    assert (lessons / "never-backs-off.md").exists()
    assert (lessons / "never-backs-off.tests.json").exists()
    assert not (lessons / "drafts" / "never-backs-off.md").exists()
    assert "APPROVED  never-backs-off: 2/2" in capsys.readouterr().out


def test_approve_keeps_a_failing_draft_in_review_and_saves_its_results(tmp_path, capsys):
    packet, lessons, settings, prompts = _workspace(tmp_path)
    _main(["learn", str(packet), "--lessons", str(lessons)], settings, prompts, FixedClient(DRAFT))
    judge = VerdictClient({"Client.KeepAliveAsync": True, "Client.PollAsync": True})

    exit_code = _main(["approve", str(lessons / "drafts" / "never-backs-off.md"), "--lessons", str(lessons)], settings, prompts, judge)

    results = json.loads((lessons / "drafts" / "never-backs-off.results.json").read_text(encoding="utf-8"))
    assert exit_code == 1
    assert (lessons / "drafts" / "never-backs-off.md").exists()
    assert not (lessons / "never-backs-off.md").exists()
    failed = []
    for entry in results["results"]:
        if not entry["passed"]:
            failed.append(entry["subject"])
    assert failed == ["Client.PollAsync"]
    assert "NOT APPROVED  never-backs-off: 1/2" in capsys.readouterr().out


def test_an_unselected_method_counts_as_cleared_without_a_judgment(tmp_path):
    packet, lessons, settings, prompts = _workspace(tmp_path)
    narrow = DRAFT.replace("- `\\bDelay\\b` (that waits)\n", "- `\\bping\\b`\n")
    (packet / "before" / "Client.cs").write_text(CODE.replace('"ping"', "ping"), encoding="utf-8")
    _main(["learn", str(packet), "--lessons", str(lessons)], settings, prompts, FixedClient(narrow))
    judge = VerdictClient({"Client.KeepAliveAsync": True})

    exit_code = _main(["approve", str(lessons / "drafts" / "never-backs-off.md"), "--lessons", str(lessons)], settings, prompts, judge)

    assert exit_code == 0
    assert judge.subjects == ["Client.KeepAliveAsync"]


def test_revise_rewrites_from_the_failures_and_keeps_the_previous_version(tmp_path, capsys):
    packet, lessons, settings, prompts = _workspace(tmp_path)
    draft = lessons / "drafts" / "never-backs-off.md"
    _main(["learn", str(packet), "--lessons", str(lessons)], settings, prompts, FixedClient(DRAFT))
    _main(["approve", str(draft), "--lessons", str(lessons)], settings, prompts, VerdictClient({"Client.KeepAliveAsync": True, "Client.PollAsync": True}))
    capsys.readouterr()
    revised = DRAFT.replace("Clients retry a remote call on a fixed beat.", "Clients retry on a fixed beat; random growing waits are fine.")
    teacher = FixedClient(revised)

    exit_code = _main(["learn", "--revise", str(draft), "--lessons", str(lessons)], settings, prompts, teacher)

    assert exit_code == 0
    assert "**polling**: expected `clear`, the lesson gave `flag`" in teacher.prompts[0]
    assert "random growing waits are fine" in draft.read_text(encoding="utf-8")
    assert "fixed beat." in (lessons / "drafts" / "history" / "never-backs-off.v1.md").read_text(encoding="utf-8")
    assert not (lessons / "drafts" / "never-backs-off.results.json").exists()
    assert "Previous:" in capsys.readouterr().out


def test_revise_without_a_failed_run_is_an_error(tmp_path, capsys):
    packet, lessons, settings, prompts = _workspace(tmp_path)
    draft = lessons / "drafts" / "never-backs-off.md"
    _main(["learn", str(packet), "--lessons", str(lessons)], settings, prompts, FixedClient(DRAFT))

    exit_code = _main(["learn", "--revise", str(draft), "--lessons", str(lessons)], settings, prompts, FixedClient(DRAFT))

    assert exit_code == 1
    assert "Run approve on the draft first" in capsys.readouterr().err


def test_learn_needs_a_packet_or_revise_but_not_both(tmp_path, capsys):
    _, lessons, settings, prompts = _workspace(tmp_path)

    exit_code = _main(["learn", "--lessons", str(lessons)], settings, prompts, FixedClient(DRAFT))

    assert exit_code == 1
    assert "either an incident packet" in capsys.readouterr().err


def test_repo_incident_packet_is_complete():
    packet = Path(__file__).parent.parent.parent / "incidents" / "azure-pipelines-agent-5448"
    labels = json.loads((packet / "labels.json").read_text(encoding="utf-8"))

    for name in ("incident.json", "incident.md", "fix.diff"):
        assert (packet / name).exists()
    for test in labels["tests"]:
        for source in test["files"]:
            assert (packet / source["path"]).exists(), source["path"]
