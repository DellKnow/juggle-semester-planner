from datetime import datetime

import pytest

from juggle.planning import (
    AvailabilityWindow,
    FixedCommitment,
    PlanningTask,
    ScheduleRequest,
)
from juggle.solver import InfeasibleScheduleError, solve_schedule
from juggle.verifier import verify_schedule


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def request(tasks, availability, commitments=None):
    return ScheduleRequest(
        planning_start=dt("2027-09-06T08:00"),
        planning_end=dt("2027-09-06T18:00"),
        tasks=tasks,
        availability=availability,
        commitments=commitments or [],
    )


def task(task_id="essay", effort=60, due="2027-09-06T12:00"):
    return PlanningTask(
        task_id=task_id,
        title=task_id.title(),
        effort_minutes=effort,
        due_at=dt(due),
    )


def window(start="2027-09-06T09:00", end="2027-09-06T12:00"):
    return AvailabilityWindow(start=dt(start), end=dt(end))


def test_schedules_task_inside_availability_before_deadline():
    schedule_request = request([task()], [window()])

    plan = solve_schedule(schedule_request)
    result = verify_schedule(schedule_request, plan)

    assert result.is_valid
    assert plan.blocks[0].start >= dt("2027-09-06T09:00")
    assert plan.blocks[0].end <= dt("2027-09-06T12:00")


def test_solver_avoids_fixed_commitment():
    schedule_request = request(
        [task()],
        [window()],
        [FixedCommitment(
            label="class",
            start=dt("2027-09-06T09:30"),
            end=dt("2027-09-06T10:30"),
        )],
    )

    plan = solve_schedule(schedule_request)

    assert verify_schedule(schedule_request, plan).is_valid
    block = plan.blocks[0]
    assert block.end <= dt("2027-09-06T09:30") or block.start >= dt("2027-09-06T10:30")


def test_raises_when_no_block_fits_before_deadline():
    schedule_request = request(
        [task(effort=90, due="2027-09-06T10:00")],
        [window(start="2027-09-06T09:00", end="2027-09-06T10:00")],
    )

    with pytest.raises(InfeasibleScheduleError):
        solve_schedule(schedule_request)


def test_two_tasks_do_not_overlap():
    schedule_request = request(
        [task("essay", effort=60), task("reading", effort=60)],
        [window(start="2027-09-06T09:00", end="2027-09-06T12:00")],
    )

    plan = solve_schedule(schedule_request)

    assert len(plan.blocks) == 2
    assert verify_schedule(schedule_request, plan).is_valid
    ordered = sorted(plan.blocks, key=lambda block: block.start)
    assert ordered[0].end <= ordered[1].start
