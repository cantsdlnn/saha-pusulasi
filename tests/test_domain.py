from datetime import UTC, datetime, timedelta

import pytest

from sahapusulasi.domain import Job, Technician, distance_km, priority_for, suggest_assignments

NOW = datetime(2026, 9, 26, 12, tzinfo=UTC)


def job(**overrides):
    values = dict(
        id=1,
        title="Ağ",
        customer="Şube",
        urgency="medium",
        sla_due=NOW + timedelta(hours=5),
        latitude=39.92,
        longitude=32.85,
        required_skill="network",
        duration_minutes=60,
    )
    values.update(overrides)
    return Job(**values)


def technician(**overrides):
    values = dict(
        id=1,
        name="Ayşe",
        skills=("network",),
        latitude=39.91,
        longitude=32.84,
        capacity_minutes=240,
    )
    values.update(overrides)
    return Technician(**values)


def test_priority_explains_urgency_and_sla_windows():
    assert priority_for(job(urgency="high", sla_due=NOW - timedelta(hours=2)), NOW).score == 140
    assert priority_for(job(sla_due=NOW + timedelta(hours=1)), NOW).score == 70
    assert priority_for(job(sla_due=NOW + timedelta(hours=20)), NOW).score == 35
    assert priority_for(job(sla_due=NOW + timedelta(hours=30)), NOW).score == 25


def test_priority_caps_extreme_overdue_score_and_requires_timezone():
    assert priority_for(job(sla_due=NOW - timedelta(days=30)), NOW).score == 165
    with pytest.raises(ValueError, match="saat dilimi"):
        priority_for(job(sla_due=NOW.replace(tzinfo=None)), NOW)


def test_haversine_distance_is_symmetric_and_validates_input():
    forward = distance_km(39.92, 32.85, 39.90, 32.80)
    reverse = distance_km(39.90, 32.80, 39.92, 32.85)
    assert forward == pytest.approx(reverse)
    assert forward == pytest.approx(4.82, rel=0.05)
    with pytest.raises(ValueError, match="sonlu"):
        distance_km(float("nan"), 0, 0, 0)


def test_suggestions_require_skill_and_capacity_and_rank_by_priority():
    jobs = [job(id=1, urgency="low"), job(id=2, urgency="high", sla_due=NOW - timedelta(hours=1))]
    suggestions = suggest_assignments(jobs, [technician()], NOW)
    assert [item.job_id for item in suggestions] == [2, 1]
    assert all(item.technician_name == "Ayşe" for item in suggestions)
    assert "Beceri eşleşti: network" in suggestions[0].reasons


def test_suggestions_skip_closed_unskilled_and_over_capacity_jobs():
    assert suggest_assignments([job(status="assigned")], [technician()], NOW) == []
    assert suggest_assignments([job(required_skill="electrical")], [technician()], NOW) == []
    assert suggest_assignments([job(duration_minutes=300)], [technician()], NOW) == []


def test_suggestion_tie_break_is_deterministic():
    technicians = [technician(id=2, name="B"), technician(id=1, name="A")]
    assert suggest_assignments([job()], technicians, NOW)[0].technician_id == 1
