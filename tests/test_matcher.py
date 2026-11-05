import pytest

from precedent.matcher import CONFLICT, MATCH, MISSING, NEAR_MISS, NONE, match
from tests.conftest import make_rule

UNOPENED_30 = make_rule("P-007", {"item_state": {"eq": "unopened"}, "days_since_purchase": {"max": 30}})
DAMAGED_60 = make_rule("P-002", {"item_state": {"eq": "damaged"}, "days_since_purchase": {"max": 60}})
OLD_DENY = make_rule("P-003", {"days_since_purchase": {"min": 25}}, "deny")


@pytest.mark.parametrize(
    "fields, rules, result, cited",
    [
        ({"item_state": "unopened", "days_since_purchase": 22}, [UNOPENED_30], MATCH, "P-007@1"),
        ({"item_state": "opened", "days_since_purchase": 22}, [UNOPENED_30], NEAR_MISS, None),
        ({"item_state": "opened", "days_since_purchase": 40}, [UNOPENED_30], NONE, None),
        ({"days_since_purchase": 22}, [UNOPENED_30], MISSING, None),
        ({"item_state": "unopened", "days_since_purchase": 28}, [UNOPENED_30, OLD_DENY], CONFLICT, None),
        ({"item_state": "damaged", "days_since_purchase": 10}, [UNOPENED_30, DAMAGED_60], MATCH, "P-002@1"),
        ({}, [], NONE, None),
    ],
)
def test_each_result(fields, rules, result, cited):
    got = match(fields, rules)
    assert got.result == result
    assert (got.cited.ref if got.cited else None) == cited


def test_unknown_is_never_false():
    got = match({"days_since_purchase": 22}, [UNOPENED_30])
    assert got.missing_fields == ["item_state"]
    assert not got.near_misses


def test_a_possible_disagreeing_rule_asks_instead_of_matching():
    # Matches P-008 for sure; P-009 would deny if the missing reason were "fraud".
    approve = make_rule("P-008", {"days_since_purchase": {"max": 30}})
    deny = make_rule("P-009", {"reason": {"eq": "fraud"}}, "deny")
    got = match({"days_since_purchase": 5, "item_state": "opened"}, [approve, deny])
    assert got.result == MISSING
    assert got.missing_fields == ["reason"]


def test_most_specific_rule_is_cited_and_order_does_not_matter():
    broad = make_rule("P-001", {"days_since_purchase": {"max": 60}})
    narrow = make_rule("P-005", {"days_since_purchase": {"max": 60}, "item_state": {"eq": "damaged"}})
    fields = {"item_state": "damaged", "days_since_purchase": 3}
    assert match(fields, [broad, narrow]).cited.ref == "P-005@1"
    assert match(fields, [narrow, broad]).cited.ref == "P-005@1"


def test_near_miss_names_the_failing_condition():
    got = match({"item_state": "opened", "days_since_purchase": 22}, [UNOPENED_30])
    assert got.near_misses[0].failed == ["item_state"]
