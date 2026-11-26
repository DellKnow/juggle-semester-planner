"""Independent checks for a proposed schedule."""

from collections import defaultdict
from datetime import datetime, time, timedelta
from math import ceil

from .planning import SchedulePlan, ScheduleRequest, VerificationResult


def _same_awareness(left: datetime, right: datetime) -> bool:
    return (left.utcoffset() is None) == (right.utcoffset() is None)


def _profile_sleep_overlap(start, end, profile, timezone) -> bool:
    """Check this block against the recurring sleep window in the profile."""
    overnight = profile.sleep_start_hour > profile.sleep_end_hour
    sleep_dates = [start.date()]
    if overnight:
        sleep_dates.append(start.date() - timedelta(days=1))

    for sleep_date in sleep_dates:
        sleep_start = datetime.combine(
            sleep_date,
            time(profile.sleep_start_hour, tzinfo=timezone),
        )
        end_date = sleep_date + timedelta(days=1) if overnight else sleep_date
        sleep_end = datetime.combine(
            end_date,
            time(profile.sleep_end_hour, tzinfo=timezone),
        )
        if start < sleep_end and end > sleep_start:
            return True
    return False


def verify_schedule(
    request: ScheduleRequest, plan: SchedulePlan
) -> VerificationResult:
    """Check constraints directly without relying on the CP-SAT model."""
    violations: list[str] = []
    tasks = {task.task_id: task for task in request.tasks}
    blocks_by_task: dict[str, list] = defaultdict(list)
    daily_work_minutes: dict[object, int] = defaultdict(int)
    profile = request.profile
    slot = request.slot_minutes
    comparable_blocks = []

    for block in plan.blocks:
        if block.task_id not in tasks:
            violations.append(f"Unknown task in schedule: {block.task_id}")
            continue
        if not _same_awareness(block.start, block.end):
            violations.append(
                f"Task block mixes timezone-aware and naive times: {block.task_id}"
            )
            continue
        if not _same_awareness(request.planning_start, block.start):
            violations.append(
                f"Task block timezone style differs from request: {block.task_id}"
            )
            continue

        blocks_by_task[block.task_id].append(block)
        comparable_blocks.append(block)

    for task_id, task in tasks.items():
        blocks = blocks_by_task.get(task_id, [])
        if not blocks:
            violations.append(f"Task is missing from schedule: {task_id}")
            continue
        if any(block.title != task.title for block in blocks):
            violations.append(f"Scheduled title does not match task: {task_id}")

        total_minutes = 0
        short_sessions = 0
        minimum_session = min(
            profile.minimum_session_minutes,
            task.planning_effort_minutes,
        )
        for block in blocks:
            if block.end <= block.start:
                violations.append(f"Task block has invalid duration: {task_id}")
                continue

            duration_minutes = int(
                (block.end - block.start).total_seconds() / 60
            )
            total_minutes += duration_minutes
            start_offset = (
                block.start - request.planning_start
            ).total_seconds() / 60
            end_offset = (
                block.end - request.planning_start
            ).total_seconds() / 60
            if (
                duration_minutes % slot
                or start_offset % slot
                or end_offset % slot
            ):
                violations.append(
                    f"Task block is not aligned to the time grid: {task_id}"
                )
            if duration_minutes > profile.maximum_session_minutes:
                violations.append(
                    f"Task session exceeds profile maximum: {task_id}"
                )
            if duration_minutes < minimum_session:
                short_sessions += 1

            if block.start.date() != block.end.date():
                violations.append(f"Task block crosses midnight: {task_id}")
            start_minute = block.start.hour * 60 + block.start.minute
            end_minute = block.end.hour * 60 + block.end.minute
            if start_minute < profile.earliest_work_hour * 60:
                violations.append(
                    f"Task starts before profile work hours: {task_id}"
                )
            if end_minute > profile.latest_work_hour * 60:
                violations.append(
                    f"Task ends after profile work hours: {task_id}"
                )
            if _profile_sleep_overlap(
                block.start,
                block.end,
                profile,
                request.planning_start.tzinfo,
            ):
                violations.append(f"Task overlaps protected sleep: {task_id}")
            if (
                block.start < request.planning_start
                or block.end > request.planning_end
            ):
                violations.append(f"Task lies outside planning horizon: {task_id}")
            if block.end > task.due_at:
                violations.append(f"Task ends after its deadline: {task_id}")
            if not any(
                window.start <= block.start and block.end <= window.end
                for window in request.availability
            ):
                violations.append(f"Task lies outside availability: {task_id}")
            for commitment in request.commitments:
                if (
                    block.start < commitment.end
                    and block.end > commitment.start
                ):
                    violations.append(
                        f"Task overlaps fixed commitment {commitment.label}: "
                        f"{task_id}"
                    )
            daily_work_minutes[block.start.date()] += duration_minutes

        expected_minutes = (
            ceil(task.planning_effort_minutes / slot) * slot
        )
        if total_minutes != expected_minutes:
            violations.append(
                f"Task effort is {total_minutes} minutes; "
                f"expected {expected_minutes}: {task_id}"
            )
        if short_sessions > 1:
            violations.append(
                f"Task has more than one short session: {task_id}"
            )

    for work_date, minutes in daily_work_minutes.items():
        if minutes > profile.daily_work_limit_minutes:
            violations.append(
                f"Daily work limit exceeded on {work_date}: {minutes} minutes"
            )

    for index, left in enumerate(comparable_blocks):
        for right in comparable_blocks[index + 1:]:
            if left.start < right.end and right.start < left.end:
                violations.append(
                    f"Task blocks overlap: {left.task_id} and {right.task_id}"
                )

    return VerificationResult(
        is_valid=not violations,
        violations=violations,
    )
