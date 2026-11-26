from datetime import datetime

import pytest

from juggle.planning import (
    AvailabilityWindow,
    PlanningTask,
    ScheduleRequest,
    UserProfile,
)
from juggle.solver import InfeasibleScheduleError, solve_schedule
from juggle.verifier import verify_schedule


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def request(profile, tasks=None):
    return ScheduleRequest(
        planning_start=dt("2027-09-06T08:00"),
        planning_end=dt("2027-09-06T18:00"),
        tasks=tasks or [
            PlanningTask(
                task_id="paper",
                title="Paper",
                effort_minutes=60,
                due_at=dt("2027-09-06T17:00"),
            )
        ],
        availability=[
            AvailabilityWindow(
                start=dt("2027-09-06T08:00"),
                end=dt("2027-09-06T17:00"),
            )
        ],
        profile=profile,
    )


def test_preferred_start_time_changes_the_plan():
    morning_profile = UserProfile(preferred_start_hour=9)
    afternoon_profile = UserProfile(preferred_start_hour=13)

    morning_plan = solve_schedule(request(morning_profile))
    afternoon_plan = solve_schedule(request(afternoon_profile))

    assert morning_plan.blocks[0].start.hour == 9
    assert afternoon_plan.blocks[0].start.hour == 13
    assert verify_schedule(request(morning_profile), morning_plan).is_valid
    assert verify_schedule(request(afternoon_profile), afternoon_plan).is_valid


def test_daily_limit_change_changes_feasibility():
    tasks = [
        PlanningTask(
            task_id=f"task-{index}",
            title=f"Task {index}",
            effort_minutes=90,
            due_at=dt("2027-09-06T17:00"),
        )
        for index in (1, 2)
    ]
    low_capacity = request(
        UserProfile(daily_work_limit_minutes=120), tasks
    )
    higher_capacity = request(
        UserProfile(daily_work_limit_minutes=180), tasks
    )

    with pytest.raises(InfeasibleScheduleError):
        solve_schedule(low_capacity)

    plan = solve_schedule(higher_capacity)
    assert verify_schedule(higher_capacity, plan).is_valid


def test_long_task_splits_at_profile_session_limit():
    long_task = PlanningTask(
        task_id="project",
        title="Project",
        effort_minutes=180,
        due_at=dt("2027-09-06T17:00"),
    )
    schedule_request = request(
        UserProfile(maximum_session_minutes=90),
        [long_task],
    )

    plan = solve_schedule(schedule_request)

    assert len(plan.blocks) == 2
    assert sum(
        int((block.end - block.start).total_seconds() / 60)
        for block in plan.blocks
    ) >= long_task.effort_minutes
    assert verify_schedule(schedule_request, plan).is_valid


def test_recorded_effort_uses_80th_percentile():
    task_with_history = PlanningTask(
        task_id="lab", title="Lab report", effort_minutes=60,
        effort_history_minutes=[30, 60, 90, 120, 150],
        due_at=dt("2027-09-06T17:00"),
    )
    schedule_request = request(UserProfile(), [task_with_history])
    plan = solve_schedule(schedule_request)
    assert task_with_history.planning_effort_minutes == 120
    assert sum(int((block.end - block.start).total_seconds() / 60) for block in plan.blocks) == 120
    assert verify_schedule(schedule_request, plan).is_valid


def test_sleep_remains_protected_when_work_hours_are_widened():
    sleep_profile = UserProfile(
        earliest_work_hour=0, latest_work_hour=23, sleep_start_hour=22,
        sleep_end_hour=7, preferred_start_hour=22,
    )
    schedule_request = ScheduleRequest(
        planning_start=dt("2027-09-06T00:00"), planning_end=dt("2027-09-07T00:00"),
        tasks=[PlanningTask(task_id="reading", title="Reading", effort_minutes=60,
                            due_at=dt("2027-09-06T23:00"))],
        availability=[AvailabilityWindow(start=dt("2027-09-06T00:00"),
                                         end=dt("2027-09-06T23:00"))],
        profile=sleep_profile,
    )
    plan = solve_schedule(schedule_request)
    assert all(block.end.hour <= 22 for block in plan.blocks)
    assert verify_schedule(schedule_request, plan).is_valid
