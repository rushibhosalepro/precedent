from precedent.backtest import policy_hash, run_backtest
from precedent.models import Case
from tests.conftest import make_rule


def decided(case_id, fields, outcome):
    return Case(
        id=case_id, type="refund", version=2, source_msg=None, requested_by={"id": "x", "name": "x"},
        created_at="2026-09-01T00:00:00Z", fields=fields,
        history=[{"event": "decided", "outcome": outcome, "under": "manual"}],
    )


HISTORY = [
    decided("C-001", {"item_state": "unopened", "days_since_purchase": 20}, "deny"),
    decided("C-002", {"item_state": "unopened", "days_since_purchase": 10}, "approve"),
    decided("C-003", {"item_state": "opened", "days_since_purchase": 20}, "deny"),
    decided("C-004", {"days_since_purchase": 20}, "approve"),
]


def test_policy_sets_are_compared_and_coverage_is_reported():
    draft = make_rule("P-007", {"item_state": {"eq": "unopened"}, "days_since_purchase": {"max": 30}}, status="draft")
    report = run_backtest(draft, [], HISTORY)
    assert report.total == 4
    assert report.unresolved == ["C-004"]
    assert report.evaluated == 3
    assert [c["case"] for c in report.newly_covered] == ["C-001", "C-002"]
    assert [c["agrees"] for c in report.newly_covered] == [False, True]
    assert report.unchanged == ["C-003"]
    assert not report.blocks_adoption
    assert "evaluated 3 (75%)" in report.summary()
    assert report.summary().startswith("WARNING")


def test_a_draft_that_conflicts_with_an_active_rule_blocks_adoption():
    active = [make_rule("P-003", {"days_since_purchase": {"min": 15}}, "deny")]
    draft = make_rule("P-007", {"item_state": {"eq": "unopened"}, "days_since_purchase": {"max": 30}}, status="draft")
    report = run_backtest(draft, active, HISTORY)
    assert [c["case"] for c in report.new_conflicts] == ["C-001"]
    assert report.blocks_adoption


def test_a_new_version_replaces_the_old_one_only_in_the_proposed_policy():
    v1 = make_rule("P-007", {"item_state": {"eq": "unopened"}, "days_since_purchase": {"max": 14}})
    v2 = make_rule("P-007", {"item_state": {"eq": "unopened"}, "days_since_purchase": {"max": 30}}, version=2, status="draft")
    v2.supersedes = "P-007@1"
    report = run_backtest(v2, [v1], HISTORY)
    assert not report.new_conflicts
    assert [c["case"] for c in report.newly_covered] == ["C-001"]


def test_policy_hash_changes_with_the_rule_set():
    a = make_rule("P-001", {"days_since_purchase": {"max": 1}})
    b = make_rule("P-002", {"days_since_purchase": {"max": 2}})
    assert policy_hash([a, b]) == policy_hash([b, a])
    assert policy_hash([a]) != policy_hash([a, b])
