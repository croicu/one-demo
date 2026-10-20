"""Finds candidate methods in C# source with plain pattern matching: no compiler, no model. This is the
cheap deterministic step before the judge. The scanner itself knows no patterns: each lesson brings its
own (its '## Candidates' section), and a method qualifies when its body matches all of them, with
strings and comments removed first."""

from __future__ import annotations

import re
from pathlib import Path

from .diagnostics import Logger
from .judge_types import SourceFile
from .scan_types import Candidate

CATEGORY_SCAN = "scan"

_SKIPPED_FOLDERS = {".git", "bin", "obj", "out", "node_modules", "TestResults"}
_TYPE_PATTERN = re.compile(r"\b(?:class|record|struct)\s+(?P<name>\w+)(?:<[^>{]*>)?(?:\s*\([^)]*\))?\s*(?::\s*(?P<base>[\w.]+))?")
_METHOD_PATTERN = re.compile(
    r"^[ \t]*(?:(?:public|private|protected|internal|static|async|override|virtual|sealed|new|unsafe|extern)\s+)+"
    r"[\w<>\[\],.?]+(?:\s*<[^>]*>)?\s+(?P<name>\w+)\s*\((?P<params>[^;{}]*?)\)\s*(?:where\b[^{]*)?\{",
    re.MULTILINE,
)
_NAMESPACE_PATTERN = re.compile(r"^\s*namespace\s+(?P<name>[\w.]+)", re.MULTILINE)
_USING_PATTERN = re.compile(r"^\s*using\s+(?:static\s+)?(?P<name>[\w.]+)\s*;", re.MULTILINE)
_MAX_BASE_DEPTH = 3


class CandidateFinder:
    def find(self, root: Path, patterns: list[str], file_glob: str = "*.cs") -> list[Candidate]:
        """The methods under root whose body matches every pattern. No patterns, no candidates: a lesson
        without a query finds nothing rather than everything."""
        if not patterns:
            return []
        compiled = []
        for pattern in patterns:
            compiled.append(re.compile(pattern))
        files = self._source_files(root, file_glob)
        Logger.info(f"scan: reading {len(files)} file(s) matching {file_glob} under {root}.", CATEGORY_SCAN)
        types_by_name = self._index_types(root, files)
        candidates = []
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace")
            for name, start, body in self._methods(text):
                if not self.matches_all(body, compiled):
                    continue
                type_name, base_name = self._enclosing_type(text, start)
                subject = f"{type_name}.{name}" if type_name else name
                relative = path.relative_to(root).as_posix()
                line = text.count("\n", 0, start) + 1
                candidate = Candidate(subject=subject, path=relative, line=line)
                candidate.files = self._files_for(root, path, base_name, types_by_name)
                Logger.diagnostic(f"scan: candidate {subject} at {relative}:{line}", CATEGORY_SCAN)
                candidates.append(candidate)
        Logger.info(f"scan: {len(candidates)} candidate(s).", CATEGORY_SCAN)
        return candidates

    @staticmethod
    def matches_all(body: str, compiled: list[re.Pattern]) -> bool:
        code = CandidateFinder.strip_strings_and_comments(body)
        for pattern in compiled:
            if pattern.search(code) is None:
                return False
        return True

    @staticmethod
    def _source_files(root: Path, file_glob: str) -> list[Path]:
        if not root.is_dir():
            return []
        files = []
        for path in sorted(root.rglob(file_glob)):
            skipped = False
            for part in path.relative_to(root).parts:
                if part in _SKIPPED_FOLDERS:
                    skipped = True
            if not skipped:
                files.append(path)
        return files

    @staticmethod
    def _index_types(root: Path, files: list[Path]) -> dict[str, list[Path]]:
        """Type name -> every file declaring a type of that name, so a candidate's base class can be
        found. A large repo can declare the same name in several places."""
        types_by_name: dict[str, list[Path]] = {}
        for path in files:
            code = CandidateFinder.strip_strings_and_comments(path.read_text(encoding="utf-8", errors="replace"))
            for match in _TYPE_PATTERN.finditer(code):
                paths = types_by_name.setdefault(match.group("name"), [])
                if path not in paths:
                    paths.append(path)
        return types_by_name

    @staticmethod
    def closest(candidate_path: Path, paths: list[Path]) -> Path:
        """Of several files declaring the same type name, the one the candidate's code can actually see:
        first a declaration in a namespace the candidate's file is in or imports with 'using', then the
        one sharing the most folders with it."""
        visible = CandidateFinder._namespaces_in_scope(candidate_path)
        best = paths[0]
        best_score = (-1, -1)
        for path in paths:
            in_scope = 1 if CandidateFinder._declared_namespaces(path) & visible else 0
            shared = 0
            for left, right in zip(candidate_path.parent.parts, path.parent.parts):
                if left != right:
                    break
                shared += 1
            if (in_scope, shared) > best_score:
                best = path
                best_score = (in_scope, shared)
        return best

    @staticmethod
    def _declared_namespaces(path: Path) -> set[str]:
        names = set()
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in _NAMESPACE_PATTERN.finditer(text):
            names.add(match.group("name"))
        return names

    @staticmethod
    def _namespaces_in_scope(path: Path) -> set[str]:
        """The file's own namespaces, their enclosing namespaces, and every 'using' import."""
        names = set()
        for name in CandidateFinder._declared_namespaces(path):
            parts = name.split(".")
            for length in range(1, len(parts) + 1):
                names.add(".".join(parts[:length]))
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in _USING_PATTERN.finditer(text):
            names.add(match.group("name"))
        return names

    @staticmethod
    def _methods(text: str) -> list[tuple[str, int, str]]:
        """(name, start offset, body) for each method with a block body. The body is found by matching
        braces while skipping strings, characters and comments."""
        methods = []
        for match in _METHOD_PATTERN.finditer(text):
            if match.group("name") in ("if", "for", "foreach", "while", "switch", "catch", "using", "lock"):
                continue
            open_brace = match.end() - 1
            close_brace = CandidateFinder._matching_brace(text, open_brace)
            if close_brace < 0:
                continue
            methods.append((match.group("name"), match.start(), text[open_brace : close_brace + 1]))
        return methods

    @staticmethod
    def _enclosing_type(text: str, offset: int) -> tuple[str | None, str | None]:
        """The last type declared before the method: its name and its first base type."""
        code = CandidateFinder.strip_strings_and_comments(text[:offset])
        type_name = None
        base_name = None
        for match in _TYPE_PATTERN.finditer(code):
            type_name = match.group("name")
            base_name = match.group("base")
        if base_name is not None:
            base_name = base_name.split(".")[-1]
        return type_name, base_name

    @staticmethod
    def _files_for(root: Path, path: Path, base_name: str | None, types_by_name: dict[str, list[Path]]) -> list[SourceFile]:
        """The candidate's own file, plus the files of its base classes found in the repo: the context the
        judge needs (a doc comment on a base class covers derived classes)."""
        chosen = [path]
        name = base_name
        depth = 0
        while name is not None and name in types_by_name and depth < _MAX_BASE_DEPTH:
            base_path = CandidateFinder.closest(path, types_by_name[name])
            if base_path in chosen:
                break
            chosen.append(base_path)
            text = base_path.read_text(encoding="utf-8", errors="replace")
            name = None
            for match in _TYPE_PATTERN.finditer(CandidateFinder.strip_strings_and_comments(text)):
                if match.group("name") == base_name and match.group("base"):
                    name = match.group("base").split(".")[-1]
            base_name = name
            depth += 1
        files = []
        for chosen_path in chosen:
            relative = chosen_path.relative_to(root).as_posix()
            files.append(SourceFile(path=str(chosen_path), shown_name=relative))
        return files

    @staticmethod
    def _matching_brace(text: str, open_index: int) -> int:
        depth = 0
        index = open_index
        while index < len(text):
            skip_to = CandidateFinder._skip_literal_or_comment(text, index)
            if skip_to > index:
                index = skip_to
                continue
            character = text[index]
            if character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
                if depth == 0:
                    return index
            index += 1
        return -1

    @staticmethod
    def strip_strings_and_comments(text: str) -> str:
        """The code with every string, character literal and comment replaced by a space, so a keyword
        or brace inside one is never mistaken for code."""
        kept = []
        index = 0
        while index < len(text):
            skip_to = CandidateFinder._skip_literal_or_comment(text, index)
            if skip_to > index:
                kept.append(" ")
                index = skip_to
                continue
            kept.append(text[index])
            index += 1
        return "".join(kept)

    @staticmethod
    def _skip_literal_or_comment(text: str, index: int) -> int:
        """If a string, character literal or comment starts at index, the index just past its end;
        otherwise index itself."""
        if text.startswith("//", index):
            end = text.find("\n", index)
            return len(text) if end < 0 else end
        if text.startswith("/*", index):
            end = text.find("*/", index + 2)
            return len(text) if end < 0 else end + 2
        start = index
        verbatim = False
        while start < len(text) and text[start] in "$@":
            if text[start] == "@":
                verbatim = True
            start += 1
        if start < len(text) and text[start] == '"' and (start > index or text[index] == '"'):
            return CandidateFinder._end_of_string(text, start, verbatim)
        if text[index] == "'":
            end = index + 1
            while end < len(text) and text[end] != "'":
                end += 2 if text[end] == "\\" else 1
            return min(end + 1, len(text))
        return index

    @staticmethod
    def _end_of_string(text: str, quote: int, verbatim: bool) -> int:
        index = quote + 1
        while index < len(text):
            character = text[index]
            if verbatim and character == '"' and text.startswith('""', index):
                index += 2
                continue
            if not verbatim and character == "\\":
                index += 2
                continue
            if character == '"':
                return index + 1
            index += 1
        return len(text)
