"""The command line: the commands, their arguments, and the parsed result."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field

from .edition import COMMANDS, PROGRAM

COMMAND_CHAT = "chat"
COMMAND_TOOL_CHAT = "tool-chat"
COMMAND_JUDGE = "judge"
COMMAND_SCAN = "scan"
COMMAND_LEARN = "learn"
COMMAND_APPROVE = "approve"
DEFAULT_LESSONS_DIR = "lessons"
DRAFTS_SUBDIR = "drafts"


@dataclass
class CliArguments:
    debug: bool = False
    command: str | None = None
    prompt: str | None = None
    provider: str | None = None
    model: str | None = None
    lesson: str | None = None
    subject: str | None = None
    files: list[str] = field(default_factory=list)
    temperature: float | None = None
    root: str | None = None
    lessons_dir: str = DEFAULT_LESSONS_DIR
    review: bool = False
    summary: str | None = None
    packet: str | None = None
    draft: str | None = None
    revise: str | None = None
    issues: bool = False
    yes: bool = False
    transcript: str | None = None


def _add_model_arguments(parser: argparse.ArgumentParser, settings_section: str, temperature: bool = True) -> None:
    parser.add_argument(
        "--provider",
        default=None,
        help=f"provider section in settings.json (e.g. local, openai); overrides settings.{settings_section}.provider",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"model name; overrides settings.{settings_section}.model and the provider's own model",
    )
    if temperature:
        parser.add_argument(
            "--temperature",
            type=float,
            default=None,
            help="sampling temperature; overrides the provider's own (none set: the model's default)",
        )


def _add_lessons_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--lessons",
        default=DEFAULT_LESSONS_DIR,
        help=f"folder of approved lessons (default: {DEFAULT_LESSONS_DIR}); drafts are in <lessons>/{DRAFTS_SUBDIR}",
    )


def _add_chat(subparsers) -> None:
    chat_parser = subparsers.add_parser(COMMAND_CHAT, help="send one prompt to a model and print its reply")
    chat_parser.add_argument("prompt", help="the prompt to send")
    _add_model_arguments(chat_parser, COMMAND_CHAT, temperature=False)


def _add_tool_chat(subparsers) -> None:
    tool_chat_parser = subparsers.add_parser(COMMAND_TOOL_CHAT, help="the model fetches the message through a tool (get_message), then answers it")
    tool_chat_parser.add_argument("prompt", metavar="message", help="the message the get_message tool returns")
    tool_chat_parser.add_argument(
        "--transcript",
        default=None,
        help="write every round (request, response, tool results) to this JSONL file",
    )
    _add_model_arguments(tool_chat_parser, COMMAND_CHAT, temperature=False)


def _add_judge(subparsers) -> None:
    judge_parser = subparsers.add_parser(COMMAND_JUDGE, help="apply one lesson to one piece of code and print the verdict as JSON")
    judge_parser.add_argument("lesson", help="lesson file, e.g. lessons/persistent-failure-retry-pacing.md")
    judge_parser.add_argument("subject", help="the code under review, e.g. InventoryClient.GetStockAsync")
    judge_parser.add_argument("files", nargs="+", help="source files to show the model; <path>=<name> shows it as <name>")
    _add_model_arguments(judge_parser, COMMAND_JUDGE)


def _add_scan(subparsers) -> None:
    scan_parser = subparsers.add_parser(COMMAND_SCAN, help="judge a folder's code against every approved lesson")
    scan_parser.add_argument("root", help="folder to scan, e.g. a checked-out repository")
    _add_lessons_argument(scan_parser)
    scan_parser.add_argument(
        "--review",
        action="store_true",
        default=False,
        help=f"judge with the lessons in review (<lessons>/{DRAFTS_SUBDIR}) instead of the approved ones",
    )
    scan_parser.add_argument(
        "--summary",
        default=None,
        help="also write a Markdown report to this file (GitHub Actions: $GITHUB_STEP_SUMMARY is used automatically)",
    )
    scan_parser.add_argument(
        "--issues",
        action="store_true",
        default=False,
        help="file each new warning as an issue in the scanned GitHub repo (after asking); never with --review",
    )
    scan_parser.add_argument("--yes", action="store_true", default=False, help="file issues without asking")
    _add_model_arguments(scan_parser, COMMAND_SCAN)


def _add_learn(subparsers) -> None:
    learn_parser = subparsers.add_parser(COMMAND_LEARN, help="draft a lesson and its tests from a saved incident packet, into <lessons>/drafts")
    learn_parser.add_argument("packet", nargs="?", help="incident packet folder, e.g. incidents/azure-pipelines-agent-5448")
    learn_parser.add_argument(
        "--revise",
        default=None,
        metavar="DRAFT",
        help="rewrite this draft from the tests it failed in its last approve run (instead of learning anew)",
    )
    _add_lessons_argument(learn_parser)
    _add_model_arguments(learn_parser, COMMAND_LEARN)


def _add_approve(subparsers) -> None:
    approve_parser = subparsers.add_parser(COMMAND_APPROVE, help="run a draft lesson's tests; move it to the approved lessons only if all pass")
    approve_parser.add_argument("draft", help="draft lesson, e.g. lessons/drafts/retry-without-backoff.md")
    _add_lessons_argument(approve_parser)
    approve_parser.add_argument("--yes", action="store_true", default=False, help="file the issues without asking")
    _add_model_arguments(approve_parser, COMMAND_SCAN)


_BUILDERS = {
    COMMAND_CHAT: _add_chat,
    COMMAND_TOOL_CHAT: _add_tool_chat,
    COMMAND_JUDGE: _add_judge,
    COMMAND_SCAN: _add_scan,
    COMMAND_LEARN: _add_learn,
    COMMAND_APPROVE: _add_approve,
}


def parse_args(argv: list[str]) -> CliArguments:
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description="Learning from past failures to find recurring patterns in code.",
    )
    parser.add_argument("--debug", action="store_true", default=False, help="override settings.json's debug flag")
    subparsers = parser.add_subparsers(dest="command", metavar="command")
    for command in COMMANDS:
        _BUILDERS[command](subparsers)

    args = parser.parse_args(argv)
    return CliArguments(
        debug=args.debug,
        command=args.command,
        prompt=getattr(args, "prompt", None),
        provider=getattr(args, "provider", None),
        model=getattr(args, "model", None),
        lesson=getattr(args, "lesson", None),
        subject=getattr(args, "subject", None),
        files=list(getattr(args, "files", None) or []),
        temperature=getattr(args, "temperature", None),
        root=getattr(args, "root", None),
        lessons_dir=getattr(args, "lessons", DEFAULT_LESSONS_DIR),
        review=getattr(args, "review", False),
        summary=getattr(args, "summary", None),
        packet=getattr(args, "packet", None),
        draft=getattr(args, "draft", None),
        revise=getattr(args, "revise", None),
        issues=getattr(args, "issues", False),
        yes=getattr(args, "yes", False),
        transcript=getattr(args, "transcript", None),
    )
