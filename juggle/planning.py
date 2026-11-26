"""Typed inputs, user preferences, and results for the schedule solver."""

from datetime import datetime
from math import ceil
from typing import Self

from pydantic import BaseModel, Field, PositiveInt, model_validator


class PlanningTask(BaseModel):
    task_id: str
    title: str
    effort_minutes: PositiveInt
    due_at: datetime
    grade_weight: float | None = Field(default=None, ge=0, le=100)
    effort_history_minutes: list[PositiveInt] = Field(default_factory=list)

    @property
    def planning_effort_minutes(self) -> int:
        """Use nearest-rank P80 effort when history exists; otherwise use the estimate."""
        if not self.effort_history_minutes:
            return int(self.effort_minutes)
        ordered = sorted(self.effort_history_minutes)
        return int(ordered[ceil(0.80 * len(ordered)) - 1])


class AvailabilityWindow(BaseModel):
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.end <= self.start:
            raise ValueError("availability window end must be after start")
        return self


class FixedCommitment(BaseModel):
    label: str
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.end <= self.start:
            raise ValueError("commitment end must be after start")
        return self


class UserProfile(BaseModel):
    """Hard work/sleep limits and a soft preferred start hour for an individual."""

    daily_work_limit_minutes: int = Field(default=240, gt=0)
    minimum_session_minutes: int = Field(default=30, gt=0)
    maximum_session_minutes: int = Field(default=120, gt=0)
    earliest_work_hour: int = Field(default=8, ge=0, le=23)
    latest_work_hour: int = Field(default=21, ge=1, le=23)
    preferred_start_hour: int = Field(default=9, ge=0, le=23)
    sleep_start_hour: int = Field(default=22, ge=0, le=23)
    sleep_end_hour: int = Field(default=7, ge=0, le=23)

    @model_validator(mode="after")
    def validate_profile(self) -> Self:
        if self.maximum_session_minutes < self.minimum_session_minutes:
            raise ValueError("maximum_session_minutes must be at least the minimum")
        if self.latest_work_hour <= self.earliest_work_hour:
            raise ValueError("latest_work_hour must be after earliest_work_hour")
        if self.sleep_start_hour == self.sleep_end_hour:
            raise ValueError("sleep_start_hour and sleep_end_hour must differ")
        return self


class ScheduleRequest(BaseModel):
    planning_start: datetime
    planning_end: datetime
    tasks: list[PlanningTask]
    availability: list[AvailabilityWindow]
    commitments: list[FixedCommitment] = Field(default_factory=list)
    profile: UserProfile = Field(default_factory=UserProfile)
    slot_minutes: int = Field(default=30, gt=0)

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        if self.planning_end <= self.planning_start:
            raise ValueError("planning_end must be after planning_start")
        if 60 % self.slot_minutes:
            raise ValueError("slot_minutes must divide evenly into 60")
        task_ids = [task.task_id for task in self.tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("task_id values must be unique")

        moments = [
            self.planning_start,
            self.planning_end,
            *(window.start for window in self.availability),
            *(window.end for window in self.availability),
            *(item.start for item in self.commitments),
            *(item.end for item in self.commitments),
            *(task.due_at for task in self.tasks),
        ]
        awareness = {moment.utcoffset() is not None for moment in moments}
        if len(awareness) > 1:
            raise ValueError(
                "all schedule datetimes must be consistently timezone-aware or naive"
            )
        return self


class PlannedBlock(BaseModel):
    task_id: str
    title: str
    start: datetime
    end: datetime


class SchedulePlan(BaseModel):
    blocks: list[PlannedBlock] = Field(default_factory=list)


class VerificationResult(BaseModel):
    is_valid: bool
    violations: list[str] = Field(default_factory=list)


class TriageOption(BaseModel):
    rank: int
    selected_task_ids: list[str]
    deferred_task_ids: list[str]
    lost_grade_weight: float
    plan: SchedulePlan


class ScheduleOutcome(BaseModel):
    plan: SchedulePlan | None = None
    triage_options: list[TriageOption] = Field(default_factory=list)
