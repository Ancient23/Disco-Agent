import pytest

from ue_agent.cost_tracker import CostTracker


def test_initial_cost_is_zero():
    tracker = CostTracker(warning_threshold_usd=5.0)
    assert tracker.total_cost_usd == 0.0
    assert tracker.warning_emitted is False


def test_add_cost_below_threshold():
    tracker = CostTracker(warning_threshold_usd=5.0)
    warnings = tracker.add_cost(2.0)
    assert tracker.total_cost_usd == 2.0
    assert warnings == []


def test_add_cost_crossing_threshold():
    tracker = CostTracker(warning_threshold_usd=5.0)
    tracker.add_cost(3.0)
    warnings = tracker.add_cost(3.0)
    assert tracker.total_cost_usd == 6.0
    assert len(warnings) == 1
    assert "6.00" in warnings[0]
    assert "5.00" in warnings[0]


def test_warning_emitted_only_once():
    tracker = CostTracker(warning_threshold_usd=5.0)
    tracker.add_cost(6.0)
    w1 = tracker.add_cost(1.0)
    assert w1 == []


def test_accumulates_multiple_adds():
    tracker = CostTracker(warning_threshold_usd=10.0)
    tracker.add_cost(3.0)
    tracker.add_cost(3.0)
    tracker.add_cost(3.0)
    assert tracker.total_cost_usd == 9.0
    assert tracker.warning_emitted is False
    warnings = tracker.add_cost(2.0)
    assert tracker.total_cost_usd == 11.0
    assert len(warnings) == 1
