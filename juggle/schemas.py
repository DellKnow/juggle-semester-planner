"""Pydantic schemas shared by the Juggle prototype."""

from typing import Any

from pydantic import BaseModel, Field, field_validator


class Deliverable(BaseModel):
    course: str | None = None
    title: str
    type: str | None = None
    due_date_expression: str | None = None
    due_date: str | None = None
    due_time: str | None = None
    time_assumed: bool = False
    grade_weight: float | None = None
    source_quote: str | None = None

    @field_validator("grade_weight", mode="before")
    @classmethod
    def parse_grade_weight(cls, value: Any) -> Any:
        if isinstance(value, str) and value.strip().endswith("%"):
            return float(value.strip()[:-1].strip())
        return value


class Ambiguity(BaseModel):
    item: str
    issue: str
    question: str


class BlockedTime(BaseModel):
    start: str
    end: str
    reason: str | None = None


class DueDateChange(BaseModel):
    task: str
    due_date: str


class EffortUpdate(BaseModel):
    task: str
    estimated_minutes: int = Field(gt=0)


class ScheduleDelta(BaseModel):
    blocked_times: list[BlockedTime] = Field(default_factory=list)
    due_changes: list[DueDateChange] = Field(default_factory=list)
    effort_updates: list[EffortUpdate] = Field(default_factory=list)


class ScheduleBlock(BaseModel):
    task: str
    start: str
    end: str


class B1Response(BaseModel):
    deliverables: list[Deliverable] = Field(default_factory=list)
    ambiguities: list[Ambiguity] = Field(default_factory=list)
    schedule_blocks: list[ScheduleBlock] = Field(default_factory=list)
    triage_options: list[str] = Field(default_factory=list)
    injection_detected: bool = False
    notes: list[str] = Field(default_factory=list)


class SyllabusCase(BaseModel):
    id: int
    title: str
    syllabus: str
    context: dict[str, Any] = Field(default_factory=dict)
    gold: dict[str, Any]
