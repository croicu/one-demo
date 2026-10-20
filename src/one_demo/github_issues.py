"""IssueTracker over the GitHub CLI (`gh`), which must be installed and signed in."""

from __future__ import annotations

import json
import subprocess

from .errors import TaskError

_LABEL_COLOR = "d93f0b"


class GhIssueTracker:
    def open_issue_bodies(self, repo: str, label: str) -> list[str]:
        output = self._gh(["issue", "list", "--repo", repo, "--label", label, "--state", "open", "--limit", "500", "--json", "body"])
        bodies = []
        for issue in json.loads(output or "[]"):
            bodies.append(issue.get("body") or "")
        return bodies

    def ensure_label(self, repo: str, name: str, description: str) -> None:
        self._gh(["label", "create", name, "--repo", repo, "--color", _LABEL_COLOR, "--description", description, "--force"])

    def create(self, repo: str, title: str, body: str, labels: list[str]) -> str:
        arguments = ["issue", "create", "--repo", repo, "--title", title, "--body", body]
        for label in labels:
            arguments.extend(["--label", label])
        return self._gh(arguments).strip()

    @staticmethod
    def _gh(arguments: list[str]) -> str:
        try:
            completed = subprocess.run(["gh", *arguments], capture_output=True, text=True, encoding="utf-8", check=False)
        except OSError as error:
            raise TaskError(f"Could not run the GitHub CLI (gh): {error}") from error
        if completed.returncode != 0:
            raise TaskError(f"gh {arguments[0]} {arguments[1]} failed: {completed.stderr.strip()}")
        return completed.stdout
