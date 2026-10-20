"""Turns scan findings into text: plain lines for a console, Markdown for a GitHub Actions job
summary. Flags come first; each cites its incident and the lines it relied on."""

from __future__ import annotations

import re

from .judge_types import Citation
from .scan_types import Finding

VERDICT_FLAG = "flag"
VERDICT_CLEAR = "clear"
KEY_EVIDENCE_LIMIT = 4

_REFERENCE_PATTERN = re.compile(r"(?P<file>[\w./\-]+\.cs):(?P<first>\d+)(?:-(?P<last>\d+))?")
# Which checks argue for a deciding condition: H1 is D1 failing, missing-fact is about D1 holding.
_CHECK_FOR_CONDITION = {"H1": "D1", "missing-fact": "D1"}


class ScanReport:
    @staticmethod
    def _ordered(findings: list[Finding]) -> tuple[list[Finding], list[Finding], list[Finding]]:
        flags = []
        clears = []
        errors = []
        for finding in findings:
            if finding.verdict is None:
                errors.append(finding)
            elif finding.verdict.verdict == VERDICT_FLAG:
                flags.append(finding)
            else:
                clears.append(finding)
        return flags, clears, errors

    @staticmethod
    def key_evidence(finding: Finding, limit: int = KEY_EVIDENCE_LIMIT) -> list[Citation]:
        """The cited lines that carry the argument: those the deciding checks point at (for a flag, also
        the check that found the fixed wait). Falls back to the first citations if the checks name no
        lines."""
        verdict = finding.verdict
        wanted = []
        for condition in verdict.conditions:
            wanted.append(_CHECK_FOR_CONDITION.get(condition, condition))
        if verdict.verdict == VERDICT_FLAG:
            wanted.append("H3")
        ranges = []
        for check in verdict.checks:
            if check.condition not in wanted:
                continue
            for match in _REFERENCE_PATTERN.finditer(check.text):
                first = int(match.group("first"))
                last = int(match.group("last") or first)
                ranges.append((match.group("file"), first, last))
        key = []
        for citation in verdict.evidence:
            name = citation.reference.rpartition(":")[0]
            for file, first, last in ranges:
                overlaps = citation.first_line <= last and first <= citation.last_line
                if (name == file or name.endswith("/" + file) or file.endswith("/" + name)) and overlaps:
                    key.append(citation)
                    break
        if not key:
            key = list(verdict.evidence)
        return key[:limit]

    @staticmethod
    def summary_line(findings: list[Finding], lesson_count: int, drafts: bool = False) -> str:
        kind = "draft" if drafts else "approved"
        if lesson_count == 0:
            return f"No {kind} lessons: nothing to check, so nothing to report."
        flags, clears, errors = ScanReport._ordered(findings)
        line = f"{len(flags)} warning(s), {len(clears)} cleared"
        if errors:
            line += f", {len(errors)} not judged"
        return line + f" ({lesson_count} {kind} lesson(s), {len(findings)} judgment(s))."

    @staticmethod
    def console(findings: list[Finding], lesson_count: int, drafts: bool = False) -> str:
        flags, clears, errors = ScanReport._ordered(findings)
        lines = []
        if drafts and lesson_count:
            lines.append("REVIEW: judging with draft lessons, not yet approved.")
            lines.append("")
        for finding in flags:
            verdict = finding.verdict
            lines.append(f"WARNING  {finding.candidate.subject}  ({finding.candidate.path}:{finding.candidate.line})")
            lines.append(f"  lesson:   {finding.lesson_id}  [{', '.join(verdict.conditions)}]")
            lines.append(f"  why:      {verdict.reason}")
            for citation in ScanReport.key_evidence(finding):
                first_line = citation.line_text.splitlines()[0] if citation.line_text else ""
                lines.append(f"  evidence: {citation.reference}  {first_line}")
            if finding.incident_url:
                lines.append(f"  incident: {finding.incident_title} <{finding.incident_url}>")
            lines.append("")
        for finding in clears:
            verdict = finding.verdict
            lines.append(f"cleared  {finding.candidate.subject}  [{', '.join(verdict.conditions)}]  {verdict.reason}")
        for finding in errors:
            lines.append(f"ERROR    {finding.candidate.subject}  {finding.error}")
        if clears or errors:
            lines.append("")
        lines.append(ScanReport.summary_line(findings, lesson_count, drafts))
        return "\n".join(lines)

    @staticmethod
    def markdown(findings: list[Finding], lesson_count: int, root_label: str, drafts: bool = False) -> str:
        flags, clears, errors = ScanReport._ordered(findings)
        title = f"## Review scan of `{root_label}` (draft lessons)" if drafts else f"## Scan of `{root_label}`"
        lines = [title, "", f"**{ScanReport.summary_line(findings, lesson_count, drafts)}**", ""]
        for finding in flags:
            verdict = finding.verdict
            lines.append(f"### ⚠️ `{finding.candidate.subject}`")
            lines.append("")
            lines.append(f"`{finding.candidate.path}:{finding.candidate.line}`")
            lines.append("")
            lines.append(f"- **Lesson:** `{finding.lesson_id}` ({', '.join(verdict.conditions)})")
            lines.append(f"- **Why:** {verdict.reason}")
            if finding.incident_url:
                lines.append(f"- **Incident:** [{finding.incident_title}]({finding.incident_url})")
            lines.append("- **Evidence:**")
            for citation in ScanReport.key_evidence(finding):
                first_line = citation.line_text.splitlines()[0] if citation.line_text else ""
                lines.append(f"  - `{citation.reference}`: `{first_line}`")
            lines.append("")
        if clears:
            lines.append("### Cleared")
            lines.append("")
            lines.append("| Code | Lesson | Because |")
            lines.append("|---|---|---|")
            for finding in clears:
                verdict = finding.verdict
                reason = verdict.reason.replace("|", "\\|")
                lines.append(f"| `{finding.candidate.subject}` | `{finding.lesson_id}` ({', '.join(verdict.conditions)}) | {reason} |")
            lines.append("")
        if errors:
            lines.append("### Not judged")
            lines.append("")
            for finding in errors:
                lines.append(f"- `{finding.candidate.subject}`: {finding.error}")
            lines.append("")
        return "\n".join(lines)
