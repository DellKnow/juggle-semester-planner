from datetime import datetime

from juggle.planning import (
    AvailabilityWindow,
    FixedCommitment,
    PlannedBlock,
    PlanningTask,
    SchedulePlan,
    ScheduleRequest,
)
from juggle.verifier import verify_schedule


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def base_request(commitments=None):
    return ScheduleRequest(
        planning_start=dt("2027-09-06T08:00"),
        planning_end=dt("2027-09-06T18:00"),
        tasks=[
            PlanningTask(
                task_id="essay",
                title="Essay",
                effort_minutes=60,
                due_at=dt("2027-09-06T16:00"),
            )
        ],
        availability=[
            AvailabilityWindow(
                start=dt("2027-09-06T09:00"),
                end=dt("2027-09-06T12:00"),
            )
        ],
        commitments=commitments or [],
    )


def one_block(start="2027-09-06T09:00", end="2027-09-06T10:00"):
    return SchedulePlan(
        blocks=[
            PlannedBlock(
                task_id="essay",
                title="Essay",
                start=dt(start),
                end=dt(end),
            )
        ]
    )


def test_accepts_valid_schedule():
    result = verify_schedule(base_request(), one_block())

    assert result.is_valid
    assert result.violations == []


def test_rejects_overlap_with_fixed_commitment():
    request = base_request(
        [
            FixedCommitment(
                label="work",
                start=dt("2027-09-06T09:30"),
                end=dt("2027-09-06T10:30"),
            )
        ]
    )

    result = verify_schedule(request, one_block("2027-09-06T09:00", "2027-09-06T10:00"))

    assert not result.is_valid
    assert any("overlaps fixed commitment" in item for item in result.violations)


def test_rejects_late_task():
    request = base_request()
    request.tasks[0].due_at = dt("2027-09-06T09:30")

    result = verify_schedule(request, one_block("2027-09-06T09:00", "2027-09-06T10:00"))

    assert not result.is_valid
    assert any("after its deadline" in item for item in result.violations)


def test_rejects_block_outside_availability():
    result = verify_schedule(
        base_request(),
        one_block("2027-09-06T12:00", "2027-09-06T13:00"),
    )

    assert not result.is_valid
    assert any("outside availability" in item for item in result.violations)


def test_reports_missing_task():
    result = verify_schedule(base_request(), SchedulePlan())

    assert not result.is_valid
    assert any("is missing from schedule" in item for item in result.violations)


def test_rejects_overlapping_task_blocks():
    request = base_request()
    request.tasks.append(
        PlanningTask(
            task_id="reading",
            title="Reading",
            effort_minutes=30,
            due_at=dt("2027-09-06T16:00"),
        )
    )
    plan = SchedulePlan(
        blocks=[
            PlannedBlock(
                task_id="essay",
                title="Essay",
                start=dt("2027-09-06T09:00"),
                end=dt("2027-09-06T10:00"),
            ),
            PlannedBlock(
                task_id="reading",
                title="Reading",
                start=dt("2027-09-06T09:30"),
                end=dt("2027-09-06T10:00"),
            ),
        ]
    )

    result = verify_schedule(request, plan)

    assert not result.is_valid
    assert any("Task blocks overlap" in item for item in result.violations)


def test_rejects_effort_beyond_slot_rounded_requirement():
    result = verify_schedule(
        base_request(),
        one_block("2027-09-06T09:00", "2027-09-06T11:00"),
    )
    assert not result.is_valid
    assert any("expected 60" in item for item in result.violations)


def test_rejects_block_that_is_not_aligned_to_planning_grid():
    result = verify_schedule(
        base_request(),
        one_block("2027-09-06T09:15", "2027-09-06T10:15"),
    )
    assert not result.is_valid
    assert any("not aligned to the time grid" in item for item in result.violations)
