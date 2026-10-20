"""Which GitHub repository and commit a scanned folder belongs to, read from git, so findings can be
filed against the repository they were found in, with links to the exact lines."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

_GITHUB_REMOTE = re.compile(r"github\.com[:/](?P<owner>[\w.-]+)/(?P<name>[\w.-]+?)(?:\.git)?/?$")


@dataclass
class SourceRepo:
    slug: str
    commit: str
    prefix: str

    @staticmethod
    def describe(folder: Path) -> SourceRepo | None:
        """The folder's GitHub repo ('owner/name'), its current commit, and the folder's path inside the
        repo ('' at the root). None when the folder isn't in a git repo with a GitHub origin."""
        top = SourceRepo._git(folder, ["rev-parse", "--show-toplevel"])
        remote = SourceRepo._git(folder, ["remote", "get-url", "origin"])
        commit = SourceRepo._git(folder, ["rev-parse", "HEAD"])
        if top is None or remote is None or commit is None:
            return None
        match = _GITHUB_REMOTE.search(remote)
        if match is None:
            return None
        prefix = Path(folder).resolve().relative_to(Path(top).resolve()).as_posix()
        if prefix == ".":
            prefix = ""
        return SourceRepo(slug=f"{match.group('owner')}/{match.group('name')}", commit=commit, prefix=prefix)

    def line_url(self, path: str, first: int, last: int) -> str:
        repo_path = f"{self.prefix}/{path}" if self.prefix else path
        anchor = f"#L{first}" if first == last else f"#L{first}-L{last}"
        return f"https://github.com/{self.slug}/blob/{self.commit}/{repo_path}{anchor}"

    @staticmethod
    def _git(folder: Path, arguments: list[str]) -> str | None:
        try:
            completed = subprocess.run(["git", "-C", str(folder), *arguments], capture_output=True, text=True, encoding="utf-8", check=False)
        except OSError:
            return None
        if completed.returncode != 0:
            return None
        return completed.stdout.strip()
