# tests/test_review.py
from causal_graph.review import crosses_high_confidence, is_reversal, HIGH_CONFIDENCE_THRESHOLD


def test_crosses_high_confidence_true_when_moving_past_threshold():
    assert crosses_high_confidence(0.85, 0.95) is True


def test_crosses_high_confidence_false_when_already_above():
    assert crosses_high_confidence(0.95, 0.97) is False


def test_crosses_high_confidence_false_when_staying_below():
    assert crosses_high_confidence(0.5, 0.6) is False


def test_is_reversal_true_on_large_downward_shift_against_uptrend():
    # prior 0.3, trending up to 0.8, then a new update drags it down sharply
    assert is_reversal(prior=0.3, current_posterior=0.8, new_posterior=0.2) is True


def test_is_reversal_false_on_small_shift():
    assert is_reversal(prior=0.3, current_posterior=0.8, new_posterior=0.75) is False


def test_is_reversal_false_when_continuing_the_trend():
    assert is_reversal(prior=0.3, current_posterior=0.5, new_posterior=0.8) is False
