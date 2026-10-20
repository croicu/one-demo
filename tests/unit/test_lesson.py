from pathlib import Path

import pytest

from one_demo.errors import TaskError
from one_demo.lesson import Lesson

LESSON_TEXT = """# Lesson

## Decision

Apply in order:

1. H3 holds → clear (H3)
2. D1 fails → clear (H1)
3. H2 holds → clear (H2)
4. D2 holds → flag (D1, D2)
5. otherwise → flag (D1, missing-fact)

## Source

1. not a rule → flag (X)
"""

REPO_LESSON = Path(__file__).parent.parent.parent / "experiments" / "model_check" / "reference" / "retry-no-backoff.md"


def _lesson(tmp_path, text=LESSON_TEXT):
    path = tmp_path / "sample-lesson.md"
    path.write_text(text, encoding="utf-8")
    return Lesson.load(path)


def test_load_parses_rules_in_order_and_only_from_decision_section(tmp_path):
    lesson = _lesson(tmp_path)

    assert lesson.lesson_id == "sample-lesson"
    assert len(lesson.rules) == 5
    assert lesson.rules[0].condition == "H3"
    assert lesson.rules[1].state == "fails"
    assert lesson.rules[3].conditions == ["D1", "D2"]
    assert lesson.rules[4].condition is None


def test_checked_conditions_in_first_mention_order(tmp_path):
    assert _lesson(tmp_path).checked_conditions() == ["H3", "D1", "H2", "D2"]


@pytest.mark.parametrize(
    "states, verdict, conditions",
    [
        ({"D1": "holds", "D2": "holds", "H2": "fails", "H3": "fails"}, "flag", ["D1", "D2"]),
        ({"D1": "fails", "D2": "holds", "H2": "fails", "H3": "fails"}, "clear", ["H1"]),
        ({"D1": "holds", "D2": "unknown", "H2": "unknown", "H3": "fails"}, "flag", ["D1", "missing-fact"]),
        ({"D1": "holds", "D2": "unknown", "H2": "holds", "H3": "fails"}, "clear", ["H2"]),
        ({"D1": "holds", "D2": "holds", "H2": "fails", "H3": "holds"}, "clear", ["H3"]),
        ({"D1": "unknown", "D2": "unknown", "H2": "unknown", "H3": "unknown"}, "flag", ["D1", "missing-fact"]),
        ({}, "flag", ["D1", "missing-fact"]),
    ],
)
def test_decide_first_matching_rule_wins(tmp_path, states, verdict, conditions):
    assert _lesson(tmp_path).decide(states) == (verdict, conditions)


def test_lesson_without_decision_section_is_rejected(tmp_path):
    with pytest.raises(TaskError):
        _lesson(tmp_path, "# Lesson\n\nNo rules here.\n")


def test_missing_lesson_file_is_rejected(tmp_path):
    with pytest.raises(TaskError):
        Lesson.load(tmp_path / "nowhere.md")


def test_repo_lesson_parses():
    if not REPO_LESSON.exists():
        pytest.skip("workshop-only reference lesson")
    lesson = Lesson.load(REPO_LESSON)

    assert lesson.checked_conditions() == ["H3", "D1", "H2", "D2"]
    assert lesson.rules[-1].condition is None


CANDIDATES_SECTION = """
## Candidates

- Files: `*.vb`
- `\\bLoop\\b` (a loop)
- `\\bCatch\\b`
"""


def test_candidates_section_is_parsed_and_kept_from_the_judge(tmp_path):
    lesson = _lesson(tmp_path, LESSON_TEXT + CANDIDATES_SECTION)

    assert lesson.candidate_patterns == [r"\bLoop\b", r"\bCatch\b"]
    assert lesson.file_glob == "*.vb"
    assert "## Candidates" not in lesson.judge_text
    assert "## Decision" in lesson.judge_text


def test_invalid_candidate_pattern_is_rejected(tmp_path):
    with pytest.raises(TaskError):
        _lesson(tmp_path, LESSON_TEXT + "\n## Candidates\n\n- `(unclosed`\n")


def test_repo_lesson_brings_its_own_retry_query():
    if not REPO_LESSON.exists():
        pytest.skip("workshop-only reference lesson")
    lesson = Lesson.load(REPO_LESSON)

    assert len(lesson.candidate_patterns) == 3
    assert lesson.file_glob == "*.cs"
    assert "## Candidates" not in lesson.judge_text
