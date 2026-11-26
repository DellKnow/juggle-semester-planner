from datetime import datetime

from juggle.planning import (
    AvailabilityWindow,
    PlanningTask,
    ScheduleRequest,
    UserProfile,
)
from juggle.solver import solve_with_triage
from juggle.verifier import verify_schedule


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def test_overload_returns_three_options_ranked_by_lost_grade_weight():
    request = ScheduleRequest(
        planning_start=dt("2027-09-06T08:00"),
        planning_end=dt("2027-09-06T18:00"),
        tasks=[
            PlanningTask(
                task_id="exam-a",
                title="Exam A",
                effort_minutes=120,
                due_at=dt("2027-09-06T17:00"),
                grade_weight=45,
            ),
            PlanningTask(
                task_id="exam-b",
                title="Exam B",
                effort_minutes=120,
                due_at=dt("2027-09-06T17:00"),
                grade_weight=35,
            ),
            PlanningTask(
                task_id="project",
                title="Project",
                effort_minutes=120,
                due_at=dt("2027-09-06T17:00"),
                grade_weight=20,
            ),
        ],
        availability=[
            AvailabilityWindow(
                start=dt("2027-09-06T08:00"),
                end=dt("2027-09-06T17:00"),
            )
        ],
        profile=UserProfile(daily_work_limit_minutes=120),
    )

    outcome = solve_with_triage(request)

    assert outcome.plan is None
    assert len(outcome.triage_options) == 3
    assert [option.lost_grade_weight for option in outcome.triage_options] == [
        55,
        65,
        80,
    ]
    for option in outcome.triage_options:
        selected_request = request.model_copy(
            update={
                "tasks": [
                    task for task in request.tasks
                    if task.task_id in option.selected_task_ids
                ]
            }
        )
        assert verify_schedule(selected_request, option.plan).is_valid
