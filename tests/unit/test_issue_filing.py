import json
import subprocess

from one_demo.cli import main
from one_demo.issue_filing import ISSUE_LABEL, IssueFiler
from one_demo.judge_types import Citation, ConditionCheck, JudgeVerdict
from one_demo.scan_types import Candidate, Finding
from one_demo.source_repo import SourceRepo

REPO = SourceRepo(slug="acme/shop", commit="abc123", prefix="")


class FakeTracker:
    def __init__(self, open_bodies=None):
        self.open_bodies = list(open_bodies or [])
        self.labels = []
        self.created = []

    def open_issue_bodies(self, repo, label):
        return list(self.open_bodies)

    def ensure_label(self, repo, name, description):
        self.labels.append(name)

    def create(self, repo, title, body, labels):
        self.created.append({"repo": repo, "title": title, "body": body, "labels": labels})
        self.open_bodies.append(body)
        return f"https://github.com/{repo}/issues/{len(self.created)}"


def _finding(subject="Client.CallAsync", verdict="flag"):
    judged = JudgeVerdict(
        lesson="retry-pacing",
        subject=subject,
        verdict=verdict,
        conditions=["D1"],
        checks=[ConditionCheck(condition="D1", state="holds", text="holds: src/Client.cs:9 calls a shared service")],
        evidence=[Citation(reference="src/Client.cs:9", first_line=9, last_line=9, line_text="await _http.GetAsync(url);")],
        bad_citations=[],
        reason="Every caller retries the shared service on the same beat.",
        model_verdict=verdict,
        model="m",
        seconds=1.0,
        prompt_tokens=1,
        completion_tokens=1,
    )
    return Finding(
        candidate=Candidate(subject=subject, path="src/Client.cs", line=5),
        lesson_id="retry-pacing",
        incident_title="Back off the keep-alive",
        incident_url="https://example.test/pr/1",
        verdict=judged,
    )


def _yes(question):
    return True


def _no(question):
    return False


def test_body_links_lines_at_the_scanned_commit_and_cites_the_incident():
    body = IssueFiler.body(_finding(), REPO)

    assert "https://github.com/acme/shop/blob/abc123/src/Client.cs#L9" in body
    assert "[Back off the keep-alive](https://example.test/pr/1)" in body
    assert "Every caller retries" in body
    assert IssueFiler.marker(_finding()) in body


def test_line_links_include_the_scanned_folders_path_in_the_repo():
    nested = SourceRepo(slug="acme/shop", commit="abc123", prefix="services/api")

    assert nested.line_url("src/Client.cs", 9, 12) == "https://github.com/acme/shop/blob/abc123/services/api/src/Client.cs#L9-L12"


def test_files_only_warnings_after_confirmation_with_labels():
    tracker = FakeTracker()
    questions = []

    def confirm(question):
        questions.append(question)
        return True

    result = IssueFiler(tracker).file([_finding(), _finding("Local.PollAsync", "clear")], REPO, {"retry-pacing": "Retry pacing"}, confirm)

    assert len(result.filed) == 1
    assert tracker.created[0]["title"] == "Retry pacing: Client.CallAsync"
    assert tracker.created[0]["labels"] == [ISSUE_LABEL, "retry-pacing"]
    assert "1 new issue(s) to file in acme/shop" in questions[0]
    assert ISSUE_LABEL in tracker.labels


def test_an_open_issue_is_never_duplicated():
    tracker = FakeTracker()
    filer = IssueFiler(tracker)
    filer.file([_finding()], REPO, {}, _yes)

    again = filer.file([_finding()], REPO, {}, _yes)

    assert len(tracker.created) == 1
    assert again.filed == []
    assert again.already_open == ["Client.CallAsync"]


def test_declining_files_nothing():
    tracker = FakeTracker()

    result = IssueFiler(tracker).file([_finding()], REPO, {}, _no)

    assert result.declined
    assert tracker.created == []


def _git(folder, *arguments):
    subprocess.run(["git", "-C", str(folder), *arguments], check=True, capture_output=True)


def _git_repo(folder, remote="https://github.com/acme/shop.git"):
    folder.mkdir(parents=True, exist_ok=True)
    _git(folder, "init", "-q")
    _git(folder, "config", "user.email", "test@example.test")
    _git(folder, "config", "user.name", "Test")
    _git(folder, "remote", "add", "origin", remote)
    (folder / "README.md").write_text("x\n", encoding="utf-8")
    _git(folder, "add", "README.md")
    _git(folder, "commit", "-q", "-m", "init")


def test_describe_reads_slug_commit_and_prefix(tmp_path):
    _git_repo(tmp_path / "shop", "git@github.com:acme/shop.git")
    (tmp_path / "shop" / "services").mkdir()

    root = SourceRepo.describe(tmp_path / "shop")
    nested = SourceRepo.describe(tmp_path / "shop" / "services")

    assert root.slug == "acme/shop"
    assert len(root.commit) == 40
    assert root.prefix == ""
    assert nested.prefix == "services"


def test_describe_is_none_for_a_repo_not_on_github(tmp_path):
    _git_repo(tmp_path / "elsewhere", "ssh://git.example.test/storage/elsewhere.git")

    assert SourceRepo.describe(tmp_path / "elsewhere") is None


CODE = """namespace Shop;

public sealed class Client
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

LESSON = r"""# Lesson: Retry pacing

- **Id:** `retry-pacing`

## Candidates

- `\bwhile\b`
- `\bDelay\b`

## Decision

1. D1 fails → clear (D1)
2. otherwise → flag (D1)

## Source

**Incident:** [Back off the keep-alive](https://example.test/pr/1)
"""


class FlagClient:
    def list_models(self):
        return []

    def chat(self, model, messages, temperature=None, json_mode=False):
        from one_demo.model_types import ChatReply

        reply = {
            "evidence": ["src/Client.cs:9"],
            "checks": {"D1": "holds: src/Client.cs:9"},
            "reason": "Every caller retries on the same beat.",
            "verdict": "flag",
        }
        return ChatReply(content=json.dumps(reply), model=model, prompt_tokens=1, completion_tokens=1)


def test_review_scan_records_the_target_and_approve_files_against_it(tmp_path, capsys):
    shop = tmp_path / "shop"
    _git_repo(shop)
    (shop / "src").mkdir()
    (shop / "src" / "Client.cs").write_text(CODE, encoding="utf-8")
    lessons = tmp_path / "lessons"
    drafts = lessons / "drafts"
    drafts.mkdir(parents=True)
    (drafts / "retry-pacing.md").write_text(LESSON, encoding="utf-8")
    (drafts / "retry-pacing.tests.json").write_text(
        json.dumps(
            {
                "tests": [
                    {
                        "name": "t",
                        "source": "incident",
                        "subject": "Client.CallAsync",
                        "expected": "flag",
                        "files": [{"path": (shop / "src" / "Client.cs").as_posix(), "showAs": "Client.cs"}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    settings = tmp_path / "settings.json"
    settings.write_text(
        json.dumps({"settings": {"logLevel": "error", "scan": {"provider": "fake"}, "fake": {"baseUrl": "http://f/v1", "model": "m"}}}),
        encoding="utf-8",
    )
    prompt = tmp_path / "judge.md"
    prompt.write_text("{{lesson}} `{{subject}}` {{conditions}} {{files}}", encoding="utf-8")
    tracker = FakeTracker()
    common = {"settings_path": settings, "client_factory": lambda_free_factory(FlagClient()), "prompt_path": prompt, "issue_tracker": tracker, "confirm": _yes}

    main(["scan", str(shop), "--lessons", str(lessons), "--review"], **common)
    record = json.loads((drafts / "last-review.json").read_text(encoding="utf-8"))
    exit_code = main(["approve", str(drafts / "retry-pacing.md"), "--lessons", str(lessons)], **common)

    output = capsys.readouterr().out
    assert record["repo"] == "acme/shop"
    assert exit_code == 0
    assert (lessons / "retry-pacing.md").exists()
    assert "Re-scanning" in output
    assert "Filed: https://github.com/acme/shop/issues/1" in output
    assert tracker.created[0]["title"] == "Retry pacing: Client.CallAsync"


def lambda_free_factory(client):
    def factory(provider, settings_path):
        return client

    return factory
