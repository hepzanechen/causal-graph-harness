HIGH_CONFIDENCE_THRESHOLD = 0.9
REVERSAL_ODDS_MULTIPLE = 2.0


def _odds(p: float) -> float:
    p = min(max(p, 1e-9), 1 - 1e-9)
    return p / (1 - p)


def crosses_high_confidence(old_posterior: float, new_posterior: float) -> bool:
    return old_posterior < HIGH_CONFIDENCE_THRESHOLD <= new_posterior


def is_reversal(prior: float, current_posterior: float, new_posterior: float) -> bool:
    if new_posterior == current_posterior:
        return False
    trend_up = current_posterior >= prior
    if trend_up and new_posterior < current_posterior:
        shift = _odds(current_posterior) / _odds(new_posterior)
        return shift >= REVERSAL_ODDS_MULTIPLE
    if not trend_up and new_posterior > current_posterior:
        shift = _odds(new_posterior) / _odds(current_posterior)
        return shift >= REVERSAL_ODDS_MULTIPLE
    return False
