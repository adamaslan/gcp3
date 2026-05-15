"""Test _pick_extreme_pair selection priority.

Locks the fix for the bug Gemini Code Assist flagged: when no convergence exists,
selection must fall back to the *strongest* divergence (largest |score|), not the
weakest (score closest to zero).
"""
from correlation_article import CorrelationResult
from story_picker import _pick_extreme_pair


def _pair(pair_id: str, score: float, signal: str) -> CorrelationResult:
    return CorrelationResult(
        pair_id=pair_id,
        source_a="a",
        source_b="b",
        score=score,
        signal=signal,
        summary="",
        data_a={},
        data_b={},
    )


def test_returns_none_for_empty():
    assert _pick_extreme_pair([]) is None


def test_any_convergence_beats_any_divergence():
    pairs = [
        _pair("strong-div", -0.95, "divergence"),
        _pair("weak-conv", 0.10, "neutral"),  # technically not "agreement" but score > 0
    ]
    # The positive score must win even when much weaker in magnitude
    assert _pick_extreme_pair(pairs).pair_id == "weak-conv"


def test_strongest_convergence_wins_among_positives():
    pairs = [
        _pair("mild-agree", 0.40, "agreement"),
        _pair("strong-agree", 0.85, "agreement"),
        _pair("weak-neutral", 0.05, "neutral"),
    ]
    assert _pick_extreme_pair(pairs).pair_id == "strong-agree"


def test_strongest_divergence_wins_when_no_convergence_exists():
    """The bug Gemini flagged: must NOT pick the score closest to zero."""
    pairs = [
        _pair("weak-div", -0.31, "divergence"),
        _pair("strong-div", -0.92, "divergence"),
        _pair("medium-div", -0.60, "divergence"),
    ]
    assert _pick_extreme_pair(pairs).pair_id == "strong-div"


def test_agreement_signal_breaks_tie_at_same_score():
    pairs = [
        _pair("neutral-positive", 0.50, "neutral"),
        _pair("agree-positive", 0.50, "agreement"),
    ]
    assert _pick_extreme_pair(pairs).pair_id == "agree-positive"


def test_all_zero_returns_something_deterministic():
    pairs = [
        _pair("a", 0.0, "neutral"),
        _pair("b", 0.0, "neutral"),
    ]
    # Both are equally valid — just confirm it returns one without crashing.
    assert _pick_extreme_pair(pairs) is not None
