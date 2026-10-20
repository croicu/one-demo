"""Files scan warnings as issues in the repository they were found in: one issue per lesson and method,
never a duplicate of one still open. The scanner only opens issues; closing them is the team's call."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .contracts import IssueTracker
from .diagnostics import Logger
from .scan_report import VERDICT_FLAG, ScanReport
from .scan_types import Finding
from .source_repo import SourceRepo

CATEGORY_ISSUES = "issues"
ISSUE_LABEL = "one-demo"
_MARKER = "<!-- one-demo-finding lesson={lesson} subject={subject} -->"


@dataclass
class FilingResult:
    filed: list[str]
    already_open: list[str]
    declined: bool = False


class IssueFiler:
    def __init__(self, tracker: IssueTracker):
        self._tracker = tracker

    @staticmethod
    def marker(finding: Finding) -> str:
        return _MARKER.format(lesson=finding.lesson_id, subject=finding.candidate.subject)

    @staticmethod
    def title(finding: Finding, lesson_title: str) -> str:
        return f"{lesson_title}: {finding.candidate.subject}"

    @staticmethod
    def body(finding: Finding, repo: SourceRepo) -> str:
        verdict = finding.verdict
        location = repo.line_url(finding.candidate.path, finding.candidate.line, finding.candidate.line)
        lines = [
            f"**`{finding.candidate.subject}`** ([{finding.candidate.path}:{finding.candidate.line}]({location}))",
            "",
            verdict.reason,
            "",
            "**Evidence** (at the scanned commit):",
            "",
        ]
        for citation in ScanReport.key_evidence(finding):
            name = citation.reference.rpartition(":")[0]
            url = repo.line_url(name, citation.first_line, citation.last_line)
            first_line = citation.line_text.splitlines()[0] if citation.line_text else ""
            lines.append(f"- [`{citation.reference}`]({url}): `{first_line}`")
        lines.append("")
        if finding.incident_url:
            lines.append(f"**Why this matters:** the same gap caused [{finding.incident_title}]({finding.incident_url}).")
            lines.append("")
        lines.append(
            "**To resolve:** fix the code, or, if it's safe for a reason the code doesn't show, document that "
            "fact where it belongs (for example a doc comment) so the next scan clears it. "
            f"Lesson `{finding.lesson_id}`, deciding conditions: {', '.join(verdict.conditions)}."
        )
        lines.append("")
        lines.append(IssueFiler.marker(finding))
        return "\n".join(lines)

    def pending(self, findings: list[Finding], repo: SourceRepo) -> tuple[list[Finding], list[Finding]]:
        """(warnings without an open issue, warnings that already have one)."""
        open_bodies = self._tracker.open_issue_bodies(repo.slug, ISSUE_LABEL)
        new = []
        existing = []
        for finding in findings:
            if finding.verdict is None or finding.verdict.verdict != VERDICT_FLAG:
                continue
            marker = IssueFiler.marker(finding)
            found = False
            for body in open_bodies:
                if marker in body:
                    found = True
            if found:
                existing.append(finding)
            else:
                new.append(finding)
        return new, existing

    def file(
        self,
        findings: list[Finding],
        repo: SourceRepo,
        lesson_titles: dict[str, str],
        confirm: Callable[[str], bool],
    ) -> FilingResult:
        new, existing = self.pending(findings, repo)
        already_open = []
        for finding in existing:
            already_open.append(finding.candidate.subject)
        if not new:
            return FilingResult(filed=[], already_open=already_open)

        lines = [f"{len(new)} new issue(s) to file in {repo.slug}:"]
        for finding in new:
            lines.append(f"  - {self.title(finding, lesson_titles.get(finding.lesson_id, finding.lesson_id))}")
        if not confirm("\n".join(lines) + "\nFile them?"):
            Logger.info("issues: filing declined; nothing filed.", CATEGORY_ISSUES)
            return FilingResult(filed=[], already_open=already_open, declined=True)

        self._tracker.ensure_label(repo.slug, ISSUE_LABEL, "Found by one-demo: a gap a past incident taught us about")
        filed = []
        for finding in new:
            self._tracker.ensure_label(repo.slug, finding.lesson_id, "one-demo lesson")
            url = self._tracker.create(
                repo.slug,
                self.title(finding, lesson_titles.get(finding.lesson_id, finding.lesson_id)),
                self.body(finding, repo),
                [ISSUE_LABEL, finding.lesson_id],
            )
            Logger.info(f"issues: filed {url}", CATEGORY_ISSUES)
            filed.append(url)
        return FilingResult(filed=filed, already_open=already_open)
