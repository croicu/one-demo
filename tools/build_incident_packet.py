"""Builds an incident packet from a merged GitHub pull request, so the teacher never fetches live.

    python tools/build_incident_packet.py microsoft/azure-pipelines-agent 5448 incidents/azure-pipelines-agent-5448

Writes into the folder:
- incident.json   title, link, merge date, merge commit, the commit before the fix, files changed
- incident.md     the pull request's title and description, verbatim
- fix.diff        the diff of the non-test source files
- before/<file>   each of those files as it was in the commit before the fix

labels.json (which methods should be flagged or cleared, and why) is curated by a person, not
generated here. Needs the GitHub CLI (`gh`), signed in.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def gh(arguments: list[str]) -> str:
    completed = subprocess.run(["gh", *arguments], capture_output=True, text=True, encoding="utf-8", check=False)
    if completed.returncode != 0:
        raise SystemExit(f"gh {' '.join(arguments)} failed: {completed.stderr.strip()}")
    return completed.stdout


def is_test_file(path: str) -> bool:
    lowered = path.lower()
    return "/test/" in lowered or "/tests/" in lowered or lowered.endswith("tests.cs") or lowered.endswith("l0.cs")


def source_diff(full_diff: str, keep: list[str]) -> str:
    """Only the per-file sections of the diff for the files in keep."""
    sections = []
    current: list[str] = []
    current_path = None
    for line in full_diff.splitlines(keepends=True):
        if line.startswith("diff --git "):
            if current_path in keep:
                sections.append("".join(current))
            current = []
            current_path = line.split(" b/", 1)[1].strip() if " b/" in line else None
        current.append(line)
    if current_path in keep:
        sections.append("".join(current))
    return "".join(sections)


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    repo, number, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])

    pr = json.loads(gh(["pr", "view", number, "--repo", repo, "--json", "title,url,body,mergedAt,mergeCommit,files"]))
    merge_commit = pr["mergeCommit"]["oid"]
    parents = json.loads(gh(["api", f"repos/{repo}/commits/{merge_commit}"]))["parents"]
    before_commit = parents[0]["sha"]

    source_files = []
    for changed in pr["files"]:
        if not is_test_file(changed["path"]):
            source_files.append(changed["path"])

    out.mkdir(parents=True, exist_ok=True)
    (out / "before").mkdir(exist_ok=True)
    metadata = {
        "repo": repo,
        "number": int(number),
        "title": pr["title"],
        "url": pr["url"],
        "diff_url": pr["url"] + "/files",
        "merged_at": pr["mergedAt"],
        "merge_commit": merge_commit,
        "before_commit": before_commit,
        "source_files": source_files,
    }
    (out / "incident.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    (out / "incident.md").write_text(f"# {pr['title']}\n\n{pr['url']} (merged {pr['mergedAt'][:10]})\n\n{pr['body'].strip()}\n", encoding="utf-8")
    (out / "fix.diff").write_text(source_diff(gh(["pr", "diff", number, "--repo", repo]), source_files), encoding="utf-8")

    for path in source_files:
        content = gh(["api", f"repos/{repo}/contents/{path}?ref={before_commit}", "-H", "Accept: application/vnd.github.raw"])
        (out / "before" / Path(path).name).write_text(content, encoding="utf-8")

    print(f"incident packet written to {out}: {len(source_files)} source file(s), before {before_commit[:8]}")


main()
