import math

from causal_graph.bayes import posterior_from_odds, group_correlated, compute_posterior


def test_posterior_from_odds_hand_computed():
    # prior odds = 0.3/0.7; new_odds = odds * 4; posterior = new_odds/(1+new_odds)
    prior = 0.3
    lr = 4.0
    odds = prior / (1 - prior)
    expected = (odds * lr) / (1 + odds * lr)
    assert math.isclose(posterior_from_odds(prior, lr), expected, rel_tol=1e-9)


def test_posterior_from_odds_bounds():
    assert posterior_from_odds(0.0, 5.0) == 0.0
    assert posterior_from_odds(1.0, 0.1) == 1.0


def test_group_correlated_independent_by_default():
    updates = [
        {"evidence_id": "e1", "likelihood_ratio": 2.0, "correlated_with": []},
        {"evidence_id": "e2", "likelihood_ratio": 3.0, "correlated_with": []},
    ]
    groups = group_correlated(updates)
    assert sorted(len(g) for g in groups) == [1, 1]


def test_group_correlated_links_via_correlated_with():
    updates = [
        {"evidence_id": "e1", "likelihood_ratio": 2.0, "correlated_with": []},
        {"evidence_id": "e2", "likelihood_ratio": 3.0, "correlated_with": ["e1"]},
    ]
    groups = group_correlated(updates)
    assert len(groups) == 1
    assert len(groups[0]) == 2


def test_compute_posterior_independent_evidence_multiplies():
    prior = 0.3
    updates = [
        {"evidence_id": "e1", "likelihood_ratio": 2.0, "correlated_with": []},
        {"evidence_id": "e2", "likelihood_ratio": 3.0, "correlated_with": []},
    ]
    result = compute_posterior(prior, updates)
    expected = posterior_from_odds(posterior_from_odds(prior, 2.0), 3.0)
    assert math.isclose(result, expected, rel_tol=1e-9)


def test_compute_posterior_correlated_evidence_does_not_double_count():
    prior = 0.3
    independent_only = compute_posterior(
        prior, [{"evidence_id": "e1", "likelihood_ratio": 8.0, "correlated_with": []}]
    )
    correlated_pair = compute_posterior(
        prior,
        [
            {"evidence_id": "e1", "likelihood_ratio": 8.0, "correlated_with": []},
            {"evidence_id": "e2", "likelihood_ratio": 5.0, "correlated_with": ["e1"]},
        ],
    )
    # Correlated group uses the strongest single LR (8.0), not the product (40.0),
    # so it must equal applying 8.0 alone, not exceed it.
    assert math.isclose(correlated_pair, independent_only, rel_tol=1e-9)


def test_compute_posterior_correlated_group_picks_strongest_by_log_distance():
    # 0.01 is farther from neutral (LR=1) than 0.5 on the log scale, so it is
    # the "strongest" evidence in the group even though 0.5 > 0.01 numerically.
    prior = 0.5
    weaker_alone = compute_posterior(
        prior, [{"evidence_id": "e1", "likelihood_ratio": 0.5, "correlated_with": []}]
    )
    stronger_alone = compute_posterior(
        prior, [{"evidence_id": "e1", "likelihood_ratio": 0.01, "correlated_with": []}]
    )
    correlated_pair = compute_posterior(
        prior,
        [
            {"evidence_id": "e1", "likelihood_ratio": 0.5, "correlated_with": []},
            {"evidence_id": "e2", "likelihood_ratio": 0.01, "correlated_with": ["e1"]},
        ],
    )
    assert math.isclose(correlated_pair, stronger_alone, rel_tol=1e-9)
    assert not math.isclose(correlated_pair, weaker_alone, rel_tol=1e-9)
