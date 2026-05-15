"""Test continuous overlap scoring used in correlation_article.

Locks the behavior that fixed the -1.00 saturation bug — zero overlap between
small sets must produce a *modulated* negative, not flat -1.00.
"""
import pytest

from correlation_article import _overlap_score


def test_empty_sets_return_neutral():
    assert _overlap_score(set(), set()) == 0.0
    assert _overlap_score(set(), {"a", "b"}) == 0.0
    assert _overlap_score({"a"}, set()) == 0.0


def test_zero_overlap_small_sets_is_modest_negative_not_saturated():
    score = _overlap_score({"a", "b", "c"}, {"d", "e", "f"})
    assert score < 0, "zero overlap should be negative"
    assert score > -0.8, f"3v3 zero overlap should not saturate near -1.0, got {score}"


def test_zero_overlap_larger_sets_more_confident():
    small = _overlap_score({"a", "b", "c"}, {"d", "e", "f"})
    large = _overlap_score({"a", "b", "c", "d", "e"}, {"f", "g", "h", "i", "j"})
    assert large < small, "larger sets with zero overlap should be more strongly negative"


def test_full_overlap_is_positive():
    score = _overlap_score({"a", "b", "c"}, {"a", "b", "c"})
    assert score > 0.5, f"full 3v3 overlap should be strongly positive, got {score}"


def test_partial_overlap_is_modulated():
    score = _overlap_score({"a", "b", "c"}, {"a", "e", "f"})
    assert -0.5 < score < 0, f"1-of-3 overlap should be mild negative, got {score}"


def test_small_full_match_low_confidence():
    score = _overlap_score({"a"}, {"a"})
    # Match exists, but n=1 → low confidence, modest positive
    assert 0 < score < 0.5, f"1v1 match should be modest positive, got {score}"


def test_score_bounded_by_one():
    big_set = set(str(i) for i in range(50))
    other = set(str(i) for i in range(50, 100))
    score = _overlap_score(big_set, other)
    assert -1.0 <= score <= 1.0
