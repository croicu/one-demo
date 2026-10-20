import json

import pytest

from one_demo.cli import main
from one_demo.errors import TaskError
from one_demo.judge_command import JudgeCommand
from one_demo.model_types import ChatReply
from one_demo.scan_command import ScanCommand
from one_demo.scan_report import ScanReport

LESSON = r"""# Lesson

## Decision

1. H3 holds → clear (H3)
2. D1 fails → clear (H1)
3. H2 holds → clear (H2)
4. D2 holds → flag (D1, D2)
5. otherwise → flag (D1, missing-fact)

## Candidates

- Files: `*.cs`
- `\bwhile\b`
- `\bcatch\b`
- `\bDelay\s*\(`

## Source

**Incident:** [Example PR #1](https://example.test/pr/1)
"""

REMOTE = """namespace Shop;

public sealed class Remote
{
    public async Task CallAsync()
    {
        while (true)
        {
            try { await _http.GetAsync("x"); return; }
            catch (HttpRequestException) { await Task.Delay(1000); }
        }
    }
}
"""

LOCAL = REMOTE.replace("Remote", "Local").replace("CallAsync", "PollAsync")


class SubjectClient:
    """Answers each judge call according to the subject named in the prompt."""

    def __init__(self, replies):
        self.replies = replies
        self.prompts = []

    def list_models(self):
        return []

    def chat(self, model, messages, temperature=None, json_mode=False):
        prompt = messages[0].content
        self.prompts.append(prompt)
        for subject, reply in self.replies.items():
            if f"`{subject}`" in prompt:
                if isinstance(reply, Exception):
                    raise reply
                return ChatReply(content=json.dumps(reply), model=model, prompt_tokens=10, completion_tokens=5)
        raise AssertionError("unexpected subject")


def _flag_reply():
    return {
        "evidence": ["Remote.cs:9", "Remote.cs:10"],
        "checks": {
            "H3": "fails: Remote.cs:10 waits a fixed second",
            "D1": "holds: Remote.cs:9 calls a remote service",
            "H2": "unknown: no comment",
            "D2": "holds: Remote.cs:9 runs per request",
        },
        "reason": "Every caller retries the shared service on the same beat.",
        "verdict": "flag",
    }


def _clear_reply():
    return {
        "evidence": ["Local.cs:9"],
        "checks": {
            "H3": "fails: fixed wait",
            "D1": "fails: Local.cs:9 is a loopback address",
            "H2": "unknown",
            "D2": "unknown",
        },
        "reason": "The target is local to each host.",
        "verdict": "clear",
    }


def _workspace(tmp_path, with_lesson=True):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "Remote.cs").write_text(REMOTE, encoding="utf-8")
    (repo / "Local.cs").write_text(LOCAL, encoding="utf-8")
    lessons = tmp_path / "lessons"
    lessons.mkdir()
    (lessons / "drafts").mkdir()
    (lessons / "drafts" / "unapproved.md").write_text(LESSON, encoding="utf-8")
    if with_lesson:
        (lessons / "retry.md").write_text(LESSON, encoding="utf-8")
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps(
            {
                "settings": {
                    "logLevel": "error",
                    "judge": {"provider": "fake"},
                    "scan": {"provider": "fake"},
                    "fake": {"baseUrl": "http://fake/v1", "model": "m"},
                }
            }
        ),
        encoding="utf-8",
    )
    prompt = tmp_path / "judge_prompt.md"
    prompt.write_text("{{lesson}}\nSUBJECT `{{subject}}`\n{{files}}", encoding="utf-8")
    return repo, lessons, settings, prompt


class Factory:
    def __init__(self, client):
        self.client = client
        self.calls = 0

    def __call__(self, provider, settings_path):
        self.calls += 1
        return self.client


def test_no_lessons_means_no_model_calls_and_a_clean_report(tmp_path, capsys):
    repo, lessons, settings, prompt = _workspace(tmp_path, with_lesson=False)
    factory = Factory(SubjectClient({}))

    exit_code = main(["scan", str(repo), "--lessons", str(lessons)], settings_path=settings, client_factory=factory, prompt_path=prompt)

    assert exit_code == 0
    assert factory.calls == 0
    assert "No approved lessons" in capsys.readouterr().out


def test_scan_flags_and_clears_with_incident_and_writes_summary(tmp_path, capsys):
    repo, lessons, settings, prompt = _workspace(tmp_path)
    client = SubjectClient({"Remote.CallAsync": _flag_reply(), "Local.PollAsync": _clear_reply()})
    summary = tmp_path / "summary.md"

    exit_code = main(
        ["scan", str(repo), "--lessons", str(lessons), "--summary", str(summary)],
        settings_path=settings,
        client_factory=Factory(client),
        prompt_path=prompt,
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert len(client.prompts) == 2
    assert "WARNING  Remote.CallAsync  (Remote.cs:5)" in output
    assert "incident: Example PR #1 <https://example.test/pr/1>" in output
    assert "cleared  Local.PollAsync  [H1]" in output
    assert "1 warning(s), 1 cleared (1 approved lesson(s), 2 judgment(s))." in output
    markdown = summary.read_text(encoding="utf-8")
    assert "### ⚠️ `Remote.CallAsync`" in markdown
    assert "[Example PR #1](https://example.test/pr/1)" in markdown


def test_a_failed_judgment_is_reported_not_fatal(tmp_path, capsys):
    repo, lessons, settings, prompt = _workspace(tmp_path)
    client = SubjectClient({"Remote.CallAsync": TaskError("model unreachable"), "Local.PollAsync": _clear_reply()})

    exit_code = main(["scan", str(repo), "--lessons", str(lessons)], settings_path=settings, client_factory=Factory(client), prompt_path=prompt)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "ERROR    Remote.CallAsync  model unreachable" in output
    assert "0 warning(s), 1 cleared, 1 not judged" in output


def test_findings_keep_candidate_order_when_run_in_parallel(tmp_path):
    repo, lessons, _, _ = _workspace(tmp_path)
    client = SubjectClient({"Remote.CallAsync": _flag_reply(), "Local.PollAsync": _clear_reply()})
    judge = JudgeCommand(client, "m", "{{lesson}}\nSUBJECT `{{subject}}`\n{{files}}")

    findings = ScanCommand(judge, parallel=4).run(repo, ScanCommand.load_lessons(lessons))

    subjects = []
    for finding in findings:
        subjects.append(finding.candidate.subject)
    assert subjects == ["Local.PollAsync", "Remote.CallAsync"]


def test_scan_of_a_missing_folder_raises(tmp_path):
    repo, lessons, _, _ = _workspace(tmp_path)
    judge = JudgeCommand(SubjectClient({}), "m", "{{lesson}}{{subject}}{{files}}")

    with pytest.raises(TaskError):
        ScanCommand(judge).run(tmp_path / "nowhere", ScanCommand.load_lessons(lessons))


def test_key_evidence_keeps_lines_the_deciding_checks_cite(tmp_path):
    repo, lessons, _, _ = _workspace(tmp_path)
    reply = _flag_reply()
    reply["evidence"] = ["Remote.cs:3", "Remote.cs:5", "Remote.cs:9", "Remote.cs:10", "Remote.cs:12"]
    client = SubjectClient({"Remote.CallAsync": reply, "Local.PollAsync": _clear_reply()})
    judge = JudgeCommand(client, "m", "{{lesson}}\nSUBJECT `{{subject}}`\n{{files}}")
    findings = ScanCommand(judge).run(repo, ScanCommand.load_lessons(lessons))

    flagged = None
    for finding in findings:
        if finding.verdict.verdict == "flag":
            flagged = finding
    references = []
    for citation in ScanReport.key_evidence(flagged):
        references.append(citation.reference)
    assert references == ["Remote.cs:9", "Remote.cs:10"]


def test_a_lesson_without_candidate_patterns_selects_nothing(tmp_path, capsys):
    repo, lessons, settings, prompt = _workspace(tmp_path)
    text = (lessons / "retry.md").read_text(encoding="utf-8")
    start = text.index("## Candidates")
    end = text.index("## Source")
    (lessons / "retry.md").write_text(text[:start] + text[end:], encoding="utf-8")
    client = SubjectClient({})

    exit_code = main(["scan", str(repo), "--lessons", str(lessons)], settings_path=settings, client_factory=Factory(client), prompt_path=prompt)

    assert exit_code == 0
    assert client.prompts == []
    assert "0 warning(s), 0 cleared" in capsys.readouterr().out


def test_review_flag_judges_the_draft_lessons(tmp_path, capsys):
    repo, lessons, settings, prompt = _workspace(tmp_path, with_lesson=False)
    client = SubjectClient({"Remote.CallAsync": _flag_reply(), "Local.PollAsync": _clear_reply()})

    approved = main(["scan", str(repo), "--lessons", str(lessons)], settings_path=settings, client_factory=Factory(client), prompt_path=prompt)
    approved_output = capsys.readouterr().out
    review = main(["scan", str(repo), "--lessons", str(lessons), "--review"], settings_path=settings, client_factory=Factory(client), prompt_path=prompt)
    review_output = capsys.readouterr().out

    assert approved == 0 and review == 0
    assert "No approved lessons" in approved_output
    assert "REVIEW: judging with draft lessons" in review_output
    assert "1 warning(s), 1 cleared (1 draft lesson(s), 2 judgment(s))." in review_output
