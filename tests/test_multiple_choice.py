"""Scoring a multiple-choice answer is easy; reading one is not.

MMLU and its relatives ask a model to pick a letter. The scoring is a string
comparison. The difficulty is deciding *what the model picked* from free-form
output, and getting that wrong is how a benchmark ends up measuring output
formatting and reporting it as accuracy.

Two failure modes this is built against:

**Scanning for any letter.** "A bird can fly south" does not answer "A". A
scorer that greps for a capital A-D reads the model's prose and scores it.

**Treating unreadable as wrong.** A model that answered in a shape the harness
cannot parse gets `None` here, never `0.0`. Zero means "answered incorrectly";
conflating the two understates every model whose formatting differs from the
one the harness happened to expect, silently, in a direction that looks like a
quality difference.
"""

from __future__ import annotations

import pytest

from aihwbench.evaluators import get_evaluator

EVALUATOR = get_evaluator("multiple_choice")


def score(response: str, expected: str = "B") -> float | None:
    return EVALUATOR.evaluate(response, expected).score


# --- the shapes a model actually answers in --------------------------------


@pytest.mark.parametrize(
    "response",
    [
        "B",
        "(B)",
        "B.",
        "B)",
        "  b  ",
        "The answer is B.",
        "Answer: B",
        "answer = B",
        "The correct answer is (B)",
        "The correct choice is B",
        "Option B is correct",
        "B) Paris",
        "B. Paris is the capital of France",
    ],
)
def test_a_correct_answer_is_recognised_however_it_is_phrased(response):
    assert score(response) == 1.0


@pytest.mark.parametrize(
    "response",
    ["A", "(A)", "The answer is A.", "Answer: A", "A) London", "Option A is correct"],
)
def test_a_wrong_answer_scores_zero(response):
    assert score(response) == 0.0


def test_case_does_not_matter():
    assert score("the answer is b") == 1.0


# --- what it refuses to read -----------------------------------------------


def test_prose_beginning_with_a_letter_is_not_an_answer():
    """The classic defect: "A bird can fly" scored as the answer "A".

    A scorer with this bug measures how often a model starts a sentence with
    the letter that happens to be correct.
    """
    assert score("A bird can fly south for the winter", "A") is None
    assert score("Paris is the capital of France", "B") is None


def test_an_unreadable_answer_is_unknown_not_wrong():
    """`None` and `0.0` are different claims about the model.

    Scoring an unparseable response as wrong understates a model that answered
    correctly in an unexpected shape, and the understatement is invisible.
    """
    result = EVALUATOR.evaluate("I would need more context to say.", "B")
    assert result.score is None
    assert "no answer letter" in (result.detail or "")


def test_an_answer_that_names_two_letters_is_not_an_answer():
    """Taking the first would reward a model for thinking out loud.

    Taking the last would be a guess dressed as a convention. Refusing is
    visible in the results; guessing is not.
    """
    result = EVALUATOR.evaluate("The answer is A, but actually the answer is B", "B")
    assert result.score is None
    assert "more than one answer" in (result.detail or "")


def test_a_letter_that_begins_a_longer_word_is_not_a_letter():
    """ "Answer: Bob" names a person, not choice B."""
    assert score("Answer: Bob") is None


def test_an_empty_response_is_unknown():
    assert score("") is None
    assert score("   ") is None


def test_a_hedged_answer_with_no_marker_is_not_read():
    assert score("I think it is either A or B") is None


# --- contract ---------------------------------------------------------------


def test_no_expected_answer_yields_no_score():
    result = EVALUATOR.evaluate("B", None)
    assert result.score is None
    assert "no expected value" in (result.detail or "")


def test_an_expected_value_that_is_not_a_choice_letter_is_refused():
    """Guarding the dataset, not the model.

    A row whose `expected` is "Paris" rather than "B" is a malformed item, and
    scoring it against an extracted letter would report the model as wrong.
    """
    result = EVALUATOR.evaluate("B", "Paris")
    assert result.score is None
    assert "not a single choice letter" in (result.detail or "")


def test_the_expected_answer_may_carry_decoration():
    assert EVALUATOR.evaluate("B", "(B)").score == 1.0
    assert EVALUATOR.evaluate("B", "b.").score == 1.0


def test_choices_beyond_d_are_supported():
    """Not every multiple-choice set has four options."""
    assert EVALUATOR.evaluate("The answer is F", "F").score == 1.0


def test_it_is_registered_so_the_cli_can_reach_it():
    from aihwbench.evaluators import list_evaluators

    assert "multiple_choice" in list_evaluators()


def test_the_pattern_carries_no_control_characters():
    """A `\\b` written into a non-raw string becomes a backspace.

    That happened here: the marker pattern began with a literal 0x08, so it
    required an unprintable character before the word "answer" and matched
    nothing. Every explicitly-marked answer scored as unreadable, which looks
    exactly like a model that formats badly.
    """
    from aihwbench.evaluators import _ANSWER_MARKER, _BARE_LETTER, _LEADING_LETTER

    for pattern in (_ANSWER_MARKER, _BARE_LETTER, _LEADING_LETTER):
        assert all(ord(c) >= 32 for c in pattern.pattern), pattern.pattern


def test_no_compiled_pattern_anywhere_carries_a_control_character():
    """One escape-collapse bug is a typo; the same one twice is a bug class.

    `\b`, `\f`, `\v` and `\a` are all valid regex escapes *and* valid
    string escapes, so a pattern written without a raw-string prefix silently
    becomes an unprintable byte. The regex still compiles and still runs; it
    just never matches, which reads as "the thing being detected did not
    happen" rather than as a fault.
    """
    import importlib
    import pkgutil
    import re

    import aihwbench

    offenders: list[str] = []
    for module_info in pkgutil.walk_packages(aihwbench.__path__, "aihwbench."):
        # `__main__` runs the CLI on import and would parse pytest's argv.
        if module_info.name.endswith(".__main__"):
            continue
        try:
            module = importlib.import_module(module_info.name)
        except Exception:  # pragma: no cover - optional dependency modules
            continue
        for name, value in vars(module).items():
            if isinstance(value, re.Pattern) and not all(
                ord(c) >= 32 or c == chr(10) for c in value.pattern
            ):
                offenders.append(f"{module_info.name}.{name}")
    assert not offenders, f"regex patterns containing control characters: {offenders}"
