"""CP-SAT solver for placing and splitting work sessions."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from math import ceil, floor

from ortools.sat.python import cp_model

from .planning import (
    PlannedBlock,
    ScheduleOutcome,
    SchedulePlan,
    ScheduleRequest,
    TriageOption,
)


class InfeasibleScheduleError(ValueError):
    """Raised when task effort cannot fit under the hard constraints."""


class ScheduleSearchTimeoutError(TimeoutError):
    """Raised when the solver cannot determine feasibility within its time limit."""


@dataclass(frozen=True)
class _Candidate:
    literal: cp_model.IntVar
    start_slot: int
    end_slot: int
    duration_slots: int
    work_date: date


def _slot_offset(moment: datetime, origin: datetime, slot_minutes: int) -> float:
    return (moment - origin).total_seconds() / (slot_minutes * 60)


def _day_bound(day: date, hour: int, timezone) -> datetime:
    return datetime.combine(day, time(hour=hour, minute=0, tzinfo=timezone))


def _overlaps_sleep(
    start: datetime, end: datetime, work_date: date, profile, timezone
) -> bool:
    sleep_days = [work_date]
    if profile.sleep_start_hour > profile.sleep_end_hour:
        sleep_days.append(work_date - timedelta(days=1))
    for sleep_day in sleep_days:
        sleep_start = _day_bound(sleep_day, profile.sleep_start_hour, timezone)
        end_day = (
            sleep_day + timedelta(days=1)
            if profile.sleep_start_hour > profile.sleep_end_hour
            else sleep_day
        )
        sleep_end = _day_bound(end_day, profile.sleep_end_hour, timezone)
        if start < sleep_end and end > sleep_start:
            return True
    return False


def solve_schedule(
    request: ScheduleRequest, max_time_seconds: float = 5.0
) -> SchedulePlan:
    """Schedule all effort in one or more contiguous, non-overlapping blocks."""
    if max_time_seconds <= 0:
        raise ValueError("max_time_seconds must be positive")
    model = cp_model.CpModel()
    slot = request.slot_minutes
    origin = request.planning_start
    horizon_end_slot = floor(_slot_offset(request.planning_end, origin, slot))
    profile = request.profile
    max_session_slots = max(1, floor(profile.maximum_session_minutes / slot))
    min_session_slots = max(1, ceil(profile.minimum_session_minutes / slot))
    daily_limit_slots = floor(profile.daily_work_limit_minutes / slot)

    candidates_by_task: dict[str, list[_Candidate]] = {}
    optional_intervals = []
    daily_work_terms: dict[date, list] = {}
    tasks_by_id = {task.task_id: task for task in request.tasks}

    for task_index, task in enumerate(request.tasks):
        required_slots = ceil(task.planning_effort_minutes / slot)
        task_candidates: list[_Candidate] = []
        short_literals: list[cp_model.IntVar] = []
        last_day = (request.planning_end - timedelta(microseconds=1)).date()
        current_day = request.planning_start.date()

        while current_day <= last_day:
            day_start = max(
                request.planning_start,
                _day_bound(current_day, profile.earliest_work_hour, origin.tzinfo),
            )
            day_end = min(
                request.planning_end,
                _day_bound(current_day, profile.latest_work_hour, origin.tzinfo),
            )

            for window in request.availability:
                segment_start = max(window.start, day_start)
                segment_end = min(window.end, day_end, task.due_at)
                if segment_end <= segment_start:
                    continue

                first_start = max(0, ceil(_slot_offset(segment_start, origin, slot)))
                last_end = min(
                    horizon_end_slot,
                    floor(_slot_offset(segment_end, origin, slot)),
                )
                for duration_slots in range(
                    1, min(max_session_slots, required_slots) + 1
                ):
                    last_start = last_end - duration_slots
                    for start_slot in range(first_start, last_start + 1):
                        end_slot = start_slot + duration_slots
                        start = origin + timedelta(minutes=start_slot * slot)
                        end = origin + timedelta(minutes=end_slot * slot)
                        if _overlaps_sleep(start, end, current_day, profile, origin.tzinfo):
                            continue
                        if any(
                            start < commitment.end and end > commitment.start
                            for commitment in request.commitments
                        ):
                            continue

                        literal = model.NewBoolVar(
                            f"task_{task_index}_candidate_{len(task_candidates)}"
                        )
                        interval = model.NewOptionalIntervalVar(
                            start_slot,
                            duration_slots,
                            end_slot,
                            literal,
                            f"task_{task_index}_interval_{len(task_candidates)}",
                        )
                        candidate = _Candidate(
                            literal=literal,
                            start_slot=start_slot,
                            end_slot=end_slot,
                            duration_slots=duration_slots,
                            work_date=current_day,
                        )
                        task_candidates.append(candidate)
                        optional_intervals.append(interval)
                        daily_work_terms.setdefault(current_day, []).append(
                            duration_slots * literal
                        )
                        if duration_slots < min_session_slots:
                            short_literals.append(literal)

            current_day += timedelta(days=1)

        if not task_candidates:
            raise InfeasibleScheduleError(
                f"No available work session can fit task {task.task_id!r} before its deadline"
            )

        model.Add(
            sum(
                candidate.duration_slots * candidate.literal
                for candidate in task_candidates
            )
            == required_slots
        )
        if short_literals:
            # At most one shorter-than-preferred final session per task.
            model.AddAtMostOne(short_literals)
        candidates_by_task[task.task_id] = task_candidates

    if optional_intervals:
        model.AddNoOverlap(optional_intervals)
    for terms in daily_work_terms.values():
        model.Add(sum(terms) <= daily_limit_slots)

    # Lexicographically prefer fewer sessions, then profile fit, then earlier blocks.
    objective_terms = []
    preferred_minute = profile.preferred_start_hour * 60
    max_blocks = sum(
        ceil(task.planning_effort_minutes / slot) for task in request.tasks
    )
    max_lower_cost_per_block = 1439 * 10 + max(0, horizon_end_slot)
    session_weight = max_blocks * max_lower_cost_per_block + 1
    for candidates in candidates_by_task.values():
        for candidate in candidates:
            start = origin + timedelta(minutes=candidate.start_slot * slot)
            start_minute = start.hour * 60 + start.minute
            preference_penalty = abs(start_minute - preferred_minute)
            cost = session_weight + preference_penalty * 10 + candidate.start_slot
            objective_terms.append(cost * candidate.literal)
    model.Minimize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_time_seconds
    solver.parameters.num_search_workers = 1
    status = solver.Solve(model)
    if status == cp_model.UNKNOWN:
        raise ScheduleSearchTimeoutError(
            f"CP-SAT could not determine feasibility within {max_time_seconds} seconds"
        )
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise InfeasibleScheduleError(
            "Tasks cannot all be placed without violating profile limits, "
            "availability, deadlines, commitments, or sleep"
        )

    blocks = []
    for task_id, candidates in candidates_by_task.items():
        task = tasks_by_id[task_id]
        for candidate in candidates:
            if solver.BooleanValue(candidate.literal):
                blocks.append(
                    PlannedBlock(
                        task_id=task_id,
                        title=task.title,
                        start=origin + timedelta(minutes=candidate.start_slot * slot),
                        end=origin + timedelta(minutes=candidate.end_slot * slot),
                    )
                )

    blocks.sort(key=lambda block: (block.start, block.task_id))
    plan = SchedulePlan(blocks=blocks)

    # Verify the generated plan through the independent checker before returning it.
    from .verifier import verify_schedule

    verification = verify_schedule(request, plan)
    if not verification.is_valid:
        raise RuntimeError(
            "solver produced an invalid schedule: "
            + "; ".join(verification.violations)
        )
    return plan


def solve_with_triage(
    request: ScheduleRequest,
    max_options: int = 3,
    max_subset_checks: int = 512,
    ungraded_penalty: float = 100.0,
    max_time_seconds: float = 1.0,
) -> ScheduleOutcome:
    """Return a full plan or up to three feasible plans ranked by grade cost.

    Up to 12 tasks generate every drop subset, then test the lowest-cost
    candidates up to max_subset_checks. Larger inputs use a bounded heuristic.
    """
    from itertools import combinations

    if max_options < 1 or max_subset_checks < 1:
        raise ValueError("max_options and max_subset_checks must be positive")
    if max_time_seconds <= 0:
        raise ValueError("max_time_seconds must be positive")

    try:
        full_plan = solve_schedule(request, max_time_seconds=max_time_seconds)
    except InfeasibleScheduleError:
        full_plan = None
    else:
        return ScheduleOutcome(plan=full_plan)

    tasks = request.tasks
    if len(tasks) <= 1:
        return ScheduleOutcome()

    def grade_cost(task) -> float:
        return (
            float(task.grade_weight)
            if task.grade_weight is not None
            else ungraded_penalty
        )

    candidates: set[frozenset[str]] = set()
    if len(tasks) <= 12:
        for count in range(1, len(tasks)):
            candidates.update(
                frozenset(task.task_id for task in group)
                for group in combinations(tasks, count)
            )
    else:
        ordered = sorted(tasks, key=lambda task: (grade_cost(task), task.task_id))
        for task in tasks:
            candidates.add(frozenset({task.task_id}))
        for count in range(1, len(tasks)):
            candidates.add(frozenset(task.task_id for task in ordered[:count]))
        for count in (2, 3):
            if count < len(tasks):
                candidates.update(
                    frozenset(task.task_id for task in group)
                    for group in combinations(ordered[:16], count)
                )

    ranked_drops = sorted(
        candidates,
        key=lambda dropped: (
            sum(grade_cost(task) for task in tasks if task.task_id in dropped),
            len(dropped),
            tuple(sorted(dropped)),
        ),
    )

    options = []
    for dropped in ranked_drops[:max_subset_checks]:
        selected = [task for task in tasks if task.task_id not in dropped]
        if not selected:
            continue
        reduced_request = request.model_copy(update={"tasks": selected})
        try:
            plan = solve_schedule(reduced_request, max_time_seconds=max_time_seconds)
        except InfeasibleScheduleError:
            continue
        options.append(
            TriageOption(
                rank=len(options) + 1,
                selected_task_ids=[task.task_id for task in selected],
                deferred_task_ids=sorted(dropped),
                lost_grade_weight=sum(
                    grade_cost(task) for task in tasks if task.task_id in dropped
                ),
                plan=plan,
            )
        )
        if len(options) == max_options:
            break

    return ScheduleOutcome(plan=None, triage_options=options)
