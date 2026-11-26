"""Annotated evaluation data loading and synthetic syllabus generation."""

import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any

from .schemas import SyllabusCase


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "annotated_syllabi.json"


def load_cases(path: Path = DATA_PATH) -> list[SyllabusCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [SyllabusCase.model_validate(row) for row in payload["cases"]]


def generate_synthetic_syllabi(count: int, seed: int = 470) -> list[dict[str, Any]]:
    """Generate extra synthetic syllabus snippets with known deliverable dates."""
    rng = random.Random(seed)
    course_names = ["CSCI", "MATH", "CHEM", "ENG", "BIO", "PHYS"]
    generated = []
    for index in range(1, count + 1):
        course = f"{rng.choice(course_names)} {rng.randint(100, 499)}"
        day = rng.randint(1, 27)
        month = rng.choice([9, 10, 11])
        due = datetime(2027, month, day, 23, 59)
        title = f"Synthetic assignment {index}"
        generated.append(
            {
                "id": index,
                "course": course,
                "title": title,
                "due_date": due.date().isoformat(),
                "due_time": due.strftime("%H:%M"),
                "syllabus": (
                    f"{course}, Fall 2027. {title} is due "
                    f"{due.strftime('%B')} {day}, 2027 at 11:59 pm."
                ),
                "annotation": {"title": title, "due_date": due.date().isoformat()},
            }
        )
    return generated
