"""Public contracts: persisted/shared data (dataclasses) and behavioral Protocols meant for a
consumer to actually implement/inject (as opposed to contracts.py's Protocols, which wire this
project's own internals together and aren't meant for an external consumer to implement).
"""

from __future__ import annotations

from typing import Protocol


class LoggingSink(Protocol):
    """Injectable logging contract -- if this project is ever consumed as a library by another
    project (rather than run standalone), the host application can pass its own logger into your
    public constructors/factories and you write through it instead of your own private Logger.
    Mirrors diagnostics.DiagnosticsLogSink's method surface exactly, so any project generated from
    this same template already has a Logger that satisfies this structurally, with no changes
    needed on the host side.

    category defaults to the literal "general" here (not imported from
    diagnostics.CATEGORY_GENERAL) so this module has no outgoing dependency on diagnostics.py --
    see Architecture convention 9 (acyclic dependency graph).
    """

    def diagnostic(self, message: str, category: str = "general") -> None: ...

    def info(self, message: str, category: str = "general") -> None: ...

    def warning(self, message: str, category: str = "general") -> None: ...

    def error(self, message: str, category: str = "general") -> None: ...

    def fatal(self, message: str, category: str = "general") -> None: ...

    def perf(self, description: str, elapsed_seconds: float) -> None: ...
