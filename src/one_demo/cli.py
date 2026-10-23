from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from .cli_arguments import (
    COMMAND_APPROVE,
    COMMAND_CHAT,
    COMMAND_JUDGE,
    COMMAND_LEARN,
    COMMAND_SCAN,
    CliArguments,
    parse_args,
)
from .command_runs import RunContext, run_approve, run_chat, run_judge, run_learn, run_scan
from .contracts import IssueTracker, ModelClient
from .diagnostics import ConsoleLogSink, Logger
from .edition import PROGRAM
from .errors import AppError
from .github_issues import GhIssueTracker
from .judge_command import DEFAULT_PROMPT_PATH
from .local_model_client import client_for
from .settings import Settings

DEFAULT_LEARN_PROMPT_PATH = Path("prompts/learn_prompt.md")
DEFAULT_REVISE_PROMPT_PATH = Path("prompts/revise_prompt.md")

__all__ = ["CliArguments", "main", "parse_args"]


def _default_client_factory(provider: str, settings_path: Path | None) -> ModelClient:
    return client_for(provider, settings_path)


def _ask(question: str) -> bool:
    """Asks on the terminal; anything but y/yes is no, and no terminal at all means no."""
    try:
        answer = input(question + " [y/N] ")
    except EOFError:
        return False
    return answer.strip().lower() in ("y", "yes")


def _dispatch(arguments: CliArguments, context: RunContext) -> int:
    if arguments.command == COMMAND_CHAT:
        return run_chat(arguments, context)
    if arguments.command == COMMAND_JUDGE:
        return run_judge(arguments, context)
    if arguments.command == COMMAND_SCAN:
        return run_scan(arguments, context)
    if arguments.command == COMMAND_LEARN:
        return run_learn(arguments, context)
    if arguments.command == COMMAND_APPROVE:
        return run_approve(arguments, context)
    return 0


def main(
    argv: list[str] | None = None,
    settings_path: Path | None = None,
    client_factory: Callable[[str, Path | None], ModelClient] | None = None,
    prompt_path: Path = DEFAULT_PROMPT_PATH,
    learn_prompt_path: Path = DEFAULT_LEARN_PROMPT_PATH,
    revise_prompt_path: Path = DEFAULT_REVISE_PROMPT_PATH,
    issue_tracker: IssueTracker | None = None,
    confirm: Callable[[str], bool] | None = None,
) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)

    try:
        settings = Settings.load() if settings_path is None else Settings.load(path=settings_path)
    except AppError as error:
        print(f"{PROGRAM}: error: {error}", file=sys.stderr)
        return 1

    debug = settings.debug or arguments.debug

    Logger.set_logger(
        ConsoleLogSink(
            min_level=settings.logging,
            categories=settings.log_categories,
            excluded_categories=settings.excluded_categories,
        )
    )
    try:
        Logger.info(f"{PROGRAM}: started.")
        context = RunContext(
            settings_path=settings_path,
            client_factory=client_factory if client_factory is not None else _default_client_factory,
            judge_prompt_path=prompt_path,
            learn_prompt_path=learn_prompt_path,
            revise_prompt_path=revise_prompt_path,
            issue_tracker=issue_tracker if issue_tracker is not None else GhIssueTracker(),
            confirm=confirm if confirm is not None else _ask,
        )
        exit_code = _dispatch(arguments, context)
        Logger.info(f"{PROGRAM}: completed.")
        return exit_code
    except AppError as error:
        if debug:
            raise
        print(f"{PROGRAM}: error: {error}", file=sys.stderr)
        return 1
    finally:
        Logger.set_logger(None)


if __name__ == "__main__":
    raise SystemExit(main())
