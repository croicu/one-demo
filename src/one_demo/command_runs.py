"""One function per command: wires settings, the model client and the command classes together, and
prints the result. cli.py parses the arguments and dispatches here."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from .approve_command import ApproveCommand
from .chat_command import ChatCommand
from .cli_arguments import COMMAND_CHAT, COMMAND_JUDGE, COMMAND_LEARN, COMMAND_SCAN, DRAFTS_SUBDIR, CliArguments
from .contracts import IssueTracker, ModelClient
from .diagnostics import Logger
from .errors import TaskError
from .filing_flow import file_findings
from .issue_filing import IssueFiler
from .judge_command import JudgeCommand
from .learn_command import LearnCommand
from .lesson import Lesson
from .provider_choice import ProviderChoice
from .review_record import ReviewRecord
from .scan_command import ScanCommand
from .scan_report import ScanReport
from .settings import Settings
from .source_repo import SourceRepo
from .tool_chat_command import ToolChatCommand
from .tool_loop import Transcript


@dataclass
class RunContext:
    settings_path: Path | None
    client_factory: Callable[[str, Path | None], ModelClient]
    judge_prompt_path: Path
    learn_prompt_path: Path
    revise_prompt_path: Path
    issue_tracker: IssueTracker
    confirm: Callable[[str], bool]


@dataclass
class ModelChoice:
    provider: str
    model: str
    temperature: float | None


def _section(name: str, context: RunContext) -> dict:
    if context.settings_path is None:
        return Settings.section(name)
    return Settings.section(name, path=context.settings_path)


def _choose(command: str, arguments: CliArguments, context: RunContext) -> ModelChoice:
    command_section = _section(command, context)
    provider = ProviderChoice.resolve_provider(command, command_section, arguments.provider)
    provider_section = _section(provider, context)
    model = ProviderChoice.resolve_model(provider, provider_section, arguments.model, command_section)
    temperature = ProviderChoice.resolve_temperature(provider_section, arguments.temperature)
    return ModelChoice(provider=provider, model=model, temperature=temperature)


def _template(path: Path, what: str) -> str:
    if not path.exists():
        raise TaskError(f"{what} prompt not found: {path} (run from the repository root).")
    return path.read_text(encoding="utf-8")


def _judge(command: str, arguments: CliArguments, context: RunContext) -> JudgeCommand:
    choice = _choose(command, arguments, context)
    client = context.client_factory(choice.provider, context.settings_path)
    return JudgeCommand(client, choice.model, _template(context.judge_prompt_path, "Judge"), choice.temperature)


def run_chat(arguments: CliArguments, context: RunContext) -> int:
    choice = _choose(COMMAND_CHAT, arguments, context)
    client = context.client_factory(choice.provider, context.settings_path)
    reply = ChatCommand(client, choice.model).run(arguments.prompt or "")
    Logger.print(reply.content)
    return 0


def run_tool_chat(arguments: CliArguments, context: RunContext) -> int:
    """Provider and model resolve as for chat (settings.chat)."""
    choice = _choose(COMMAND_CHAT, arguments, context)
    client = context.client_factory(choice.provider, context.settings_path)
    transcript = Transcript(Path(arguments.transcript)) if arguments.transcript else None
    reply = ToolChatCommand(client, choice.model, transcript).run(arguments.prompt or "")
    Logger.print(reply.content)
    return 0


def run_judge(arguments: CliArguments, context: RunContext) -> int:
    lesson = Lesson.load(Path(arguments.lesson or ""))
    files = []
    for argument in arguments.files:
        files.append(JudgeCommand.parse_source_file(argument))
    verdict = _judge(COMMAND_JUDGE, arguments, context).run(lesson, arguments.subject or "", files)
    Logger.print(json.dumps(asdict(verdict), indent=2))
    return 0


def run_scan(arguments: CliArguments, context: RunContext) -> int:
    lessons_dir = Path(arguments.lessons_dir)
    if arguments.review:
        lessons_dir = lessons_dir / DRAFTS_SUBDIR
    lessons = ScanCommand.load_lessons(lessons_dir)
    root = Path(arguments.root or "")
    findings = []
    if lessons:
        findings = ScanCommand(_judge(COMMAND_SCAN, arguments, context)).run(root, lessons)
    Logger.print(ScanReport.console(findings, len(lessons), drafts=arguments.review))
    if arguments.review:
        repo = SourceRepo.describe(root)
        ReviewRecord(
            # absolute(), not resolve(): resolve() follows junctions, so C:\Projects\... would be
            # recorded as the drive it links to.
            folder=str(root.absolute()),
            repo=repo.slug if repo else None,
            commit=repo.commit if repo else None,
        ).save(lessons_dir)
    elif arguments.issues and lessons:
        Logger.print("")
        filing = file_findings(findings, root, lessons, IssueFiler(context.issue_tracker), _confirm(arguments, context))
        Logger.print("\n".join(filing))

    summary_paths = []
    if arguments.summary:
        summary_paths.append(Path(arguments.summary))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        summary_paths.append(Path(os.environ["GITHUB_STEP_SUMMARY"]))
    markdown = ScanReport.markdown(findings, len(lessons), arguments.root or "", drafts=arguments.review)
    for path in summary_paths:
        try:
            with path.open("a", encoding="utf-8") as summary:
                summary.write(markdown + "\n")
        except OSError as error:
            raise TaskError(f"Could not write the scan summary to {path}: {error}") from error
    return 0


def run_learn(arguments: CliArguments, context: RunContext) -> int:
    choice = _choose(COMMAND_LEARN, arguments, context)
    client = context.client_factory(choice.provider, context.settings_path)
    if bool(arguments.packet) == bool(arguments.revise):
        raise TaskError("Give either an incident packet to learn from, or --revise <draft>, not both.")
    if arguments.revise:
        teacher = LearnCommand(
            client,
            choice.model,
            "",
            choice.temperature,
            revise_template=_template(context.revise_prompt_path, "Revise"),
        )
        result = teacher.revise(Path(arguments.revise))
    else:
        teacher = LearnCommand(client, choice.model, _template(context.learn_prompt_path, "Learn"), choice.temperature)
        result = teacher.run(Path(arguments.packet or ""), Path(arguments.lessons_dir) / DRAFTS_SUBDIR)

    lines = [f"Draft lesson: {result.lesson_path}", f"Its tests:    {result.tests_path}"]
    if result.previous_path is not None:
        lines.append(f"Previous:     {result.previous_path}")
    if result.failures:
        lines.append("")
        lines.append(f"The draft fails {len(result.failures)} check(s):")
        for failure in result.failures:
            lines.append(f"  - {failure}")
    else:
        lines.append("Checks passed. Review it with: scan <folder> --review; then approve it with its tests.")
    Logger.print("\n".join(lines))
    return 1 if result.failures else 0


def _confirm(arguments: CliArguments, context: RunContext) -> Callable[[str], bool]:
    if arguments.yes:
        return _always_yes
    return context.confirm


def _always_yes(question: str) -> bool:
    Logger.print(question + " yes (--yes)")
    return True


def run_approve(arguments: CliArguments, context: RunContext) -> int:
    """The gate, then the hand-off: run the tests; if they pass, the lesson goes live, the folder the last
    review scanned is scanned again with it, the remaining warnings are listed, and after confirmation
    they are filed as issues in the repo they were found in."""
    judge = _judge(COMMAND_SCAN, arguments, context)
    draft = Path(arguments.draft or "")
    result = ApproveCommand(judge).run(draft, Path(arguments.lessons_dir))
    Logger.print(ApproveCommand.report(result))
    if not result.approved or result.approved_path is None:
        return 1

    record = ReviewRecord.load(draft.parent)
    if record is None:
        Logger.print("No review scan on record (scan <folder> --review): no issues filed.")
        return 0
    lesson = Lesson.load(result.approved_path)
    folder = Path(record.folder)
    Logger.print("")
    Logger.print(f"Re-scanning {folder} with the approved lesson...")
    findings = ScanCommand(judge).run(folder, [lesson])
    Logger.print(ScanReport.console(findings, 1))
    Logger.print("")
    filing = file_findings(findings, folder, [lesson], IssueFiler(context.issue_tracker), _confirm(arguments, context))
    Logger.print("\n".join(filing))
    return 0
