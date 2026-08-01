import pytest
from causal_graph.schema import (
    ValidationError, Confidence, Status, new_id, parse_node_ref,
    validate_probability, validate_likelihood_ratio,
)


def test_new_id_has_prefix():
    assert new_id("fact").startswith("fact_")


def test_parse_node_ref_fact():
    assert parse_node_ref("fact:f1") == ("fact", "f1")


def test_parse_node_ref_deduction():
    assert parse_node_ref("deduction:d1") == ("deduction", "d1")


def test_parse_node_ref_rejects_bad_format():
    with pytest.raises(ValidationError):
        parse_node_ref("f1")
    with pytest.raises(ValidationError):
        parse_node_ref("evidence:e1")


def test_validate_probability_accepts_bounds():
    assert validate_probability(0.0) == 0.0
    assert validate_probability(1.0) == 1.0
    assert validate_probability(0.5) == 0.5


def test_validate_probability_rejects_out_of_bounds():
    with pytest.raises(ValidationError):
        validate_probability(1.5)
    with pytest.raises(ValidationError):
        validate_probability(-0.1)


def test_validate_likelihood_ratio_rejects_non_positive():
    with pytest.raises(ValidationError):
        validate_likelihood_ratio(0)
    with pytest.raises(ValidationError):
        validate_likelihood_ratio(-2.0)


def test_validate_likelihood_ratio_rejects_non_finite():
    with pytest.raises(ValidationError):
        validate_likelihood_ratio(float("nan"))
    with pytest.raises(ValidationError):
        validate_likelihood_ratio(float("inf"))


def test_confidence_and_status_values():
    assert Confidence.VERIFIED.value == "verified"
    assert Status.STALE.value == "stale"
