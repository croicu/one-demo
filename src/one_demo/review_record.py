"""What the last review scan looked at: the folder, and the GitHub repo and commit it belongs to. Approval
re-scans that folder with the approved lesson and files issues against that repo, so the target is
never named twice."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

REVIEW_FILE = "last-review.json"


@dataclass
class ReviewRecord:
    folder: str
    repo: str | None
    commit: str | None

    @staticmethod
    def path_in(drafts_dir: Path) -> Path:
        return drafts_dir / REVIEW_FILE

    def save(self, drafts_dir: Path) -> None:
        drafts_dir.mkdir(parents=True, exist_ok=True)
        payload = {"folder": self.folder, "repo": self.repo, "commit": self.commit}
        ReviewRecord.path_in(drafts_dir).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def load(drafts_dir: Path) -> ReviewRecord | None:
        path = ReviewRecord.path_in(drafts_dir)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ReviewRecord(folder=payload["folder"], repo=payload.get("repo"), commit=payload.get("commit"))
