from pathlib import Path

import pytest

from one_demo.candidates import CandidateFinder

RETRY_PATTERNS = [r"\b(?:for|foreach|while|do)\b", r"\bcatch\b", r"\b(?:Delay|Sleep)\s*\("]

RETRY_CLIENT = """using System.Net.Http.Json;

namespace Shop.Orders;

public sealed class OrderClient
{
    public async Task<string?> GetAsync(string id, CancellationToken ct)
    {
        for (var attempt = 1; attempt <= 5; attempt++)
        {
            try
            {
                return await _http.GetStringAsync($"orders/{id}", ct);
            }
            catch (HttpRequestException) when (attempt < 5)
            {
                await Task.Delay(TimeSpan.FromSeconds(2), ct);
            }
        }
        throw new InvalidOperationException("}");
    }

    public string Describe() => "no retry here";

    private void Log(string message)
    {
        // a loop, a catch and a Delay( in a comment are not code: while catch Delay(
        Console.WriteLine("while { catch Delay(");
    }
}
"""

POLL_WITHOUT_CATCH = """namespace Shop.Telemetry;

public sealed class Poller
{
    protected async Task RunAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            await Task.Delay(1000, ct);
        }
    }
}
"""

JOB = """namespace Shop.Jobs;

public sealed class CleanupJob : JobBase
{
    private async Task CleanAsync()
    {
        while (true)
        {
            try { await _store.DeleteAsync(); return; }
            catch (IOException) { Thread.Sleep(500); }
        }
    }
}
"""

JOB_BASE = """namespace Shop.Jobs;

public abstract class JobBase
{
}
"""

OTHER_JOB_BASE = """namespace Unrelated.Things;

public abstract class JobBase
{
}
"""


def _repo(tmp_path, files):
    for relative, text in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def _subjects(candidates):
    subjects = []
    for candidate in candidates:
        subjects.append(candidate.subject)
    return subjects


def test_finds_retry_method_with_loop_catch_and_wait(tmp_path):
    root = _repo(tmp_path, {"src/OrderClient.cs": RETRY_CLIENT})

    candidates = CandidateFinder().find(root, RETRY_PATTERNS)

    assert _subjects(candidates) == ["OrderClient.GetAsync"]
    assert candidates[0].path == "src/OrderClient.cs"
    assert candidates[0].line == 7
    assert candidates[0].files[0].shown_name == "src/OrderClient.cs"


def test_loop_and_wait_without_catch_is_not_a_candidate(tmp_path):
    root = _repo(tmp_path, {"Poller.cs": POLL_WITHOUT_CATCH})

    assert CandidateFinder().find(root, RETRY_PATTERNS) == []


def test_base_class_file_comes_along(tmp_path):
    root = _repo(tmp_path, {"Jobs/CleanupJob.cs": JOB, "Jobs/JobBase.cs": JOB_BASE})

    candidates = CandidateFinder().find(root, RETRY_PATTERNS)

    shown = []
    for source in candidates[0].files:
        shown.append(source.shown_name)
    assert _subjects(candidates) == ["CleanupJob.CleanAsync"]
    assert shown == ["Jobs/CleanupJob.cs", "Jobs/JobBase.cs"]


def test_base_class_in_a_visible_namespace_wins_over_a_namesake(tmp_path):
    root = _repo(
        tmp_path,
        {"Jobs/CleanupJob.cs": JOB, "Other/JobBase.cs": OTHER_JOB_BASE, "Shared/JobBase.cs": JOB_BASE},
    )

    candidates = CandidateFinder().find(root, RETRY_PATTERNS)

    assert candidates[0].files[1].shown_name == "Shared/JobBase.cs"


def test_build_output_folders_are_skipped(tmp_path):
    root = _repo(tmp_path, {"src/obj/Generated.cs": RETRY_CLIENT, "src/bin/Copy.cs": RETRY_CLIENT})

    assert CandidateFinder().find(root, RETRY_PATTERNS) == []


def test_missing_folder_finds_nothing(tmp_path):
    assert CandidateFinder().find(tmp_path / "nowhere", RETRY_PATTERNS) == []


def test_strings_and_comments_are_blanked():
    code = 'var a = "while { }"; // catch Delay(\nvar b = @"x""y"; /* Sleep( */ var c = \'{\';'

    stripped = CandidateFinder.strip_strings_and_comments(code)

    assert "while" not in stripped
    assert "catch" not in stripped
    assert "Sleep" not in stripped
    assert "{" not in stripped
    assert "var c" in stripped


def test_repo_lesson_targets_have_three_retries():
    targets = Path(__file__).parent.parent.parent / "experiments" / "model_check" / "targets"
    if not targets.exists():
        pytest.skip("workshop-only model check targets")

    candidates = CandidateFinder().find(targets, RETRY_PATTERNS)

    assert sorted(_subjects(candidates)) == [
        "InventoryClient.GetStockAsync",
        "ReconciliationJob.GetOpenBatchAsync",
        "StatusMonitor.GetStatusAsync",
    ]


def test_no_patterns_finds_nothing(tmp_path):
    root = _repo(tmp_path, {"src/OrderClient.cs": RETRY_CLIENT})

    assert CandidateFinder().find(root, []) == []


def test_patterns_and_file_glob_come_from_the_caller(tmp_path):
    root = _repo(tmp_path, {"src/OrderClient.cs": RETRY_CLIENT, "src/OrderClient.txt": RETRY_CLIENT})

    only_loops = CandidateFinder().find(root, [r"\bfor\b"])
    nothing = CandidateFinder().find(root, RETRY_PATTERNS, file_glob="*.vb")

    assert _subjects(only_loops) == ["OrderClient.GetAsync"]
    assert nothing == []
