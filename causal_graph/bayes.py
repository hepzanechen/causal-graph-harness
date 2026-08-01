import math


def posterior_from_odds(prior: float, likelihood_ratio: float) -> float:
    if prior <= 0.0:
        return 0.0
    if prior >= 1.0:
        return 1.0
    odds = prior / (1 - prior)
    new_odds = odds * likelihood_ratio
    return new_odds / (1 + new_odds)


def _find(parent: dict, x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def _union(parent: dict, a, b) -> None:
    ra, rb = _find(parent, a), _find(parent, b)
    if ra != rb:
        parent[ra] = rb


def group_correlated(updates: list) -> list:
    ids = [u["evidence_id"] for u in updates]
    parent = {i: i for i in ids}
    by_id = {u["evidence_id"]: u for u in updates}
    for u in updates:
        for other in u.get("correlated_with", []):
            if other in parent:
                _union(parent, u["evidence_id"], other)
    groups: dict = {}
    for i in ids:
        root = _find(parent, i)
        groups.setdefault(root, []).append(by_id[i])
    return list(groups.values())


def compute_posterior(prior: float, updates: list) -> float:
    posterior = prior
    for group in group_correlated(updates):
        # "Strongest" evidence is the one farthest from neutral (LR=1) on the
        # log scale, not the numerically largest ratio: 0.01 is stronger
        # counter-evidence than 0.5, even though 0.5 > 0.01.
        strongest = max(group, key=lambda u: abs(math.log(u["likelihood_ratio"])))
        posterior = posterior_from_odds(posterior, strongest["likelihood_ratio"])
    return posterior
