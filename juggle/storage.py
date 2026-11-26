"""SQLite response cache and API usage ledger."""

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "results" / "part1.sqlite3"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SQLiteStore:
    """Small persistent cache and usage ledger for repeatable evaluations."""

    def __init__(self, path: Path = DB_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS llm_cache (
                    cache_key TEXT PRIMARY KEY,
                    model TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS usage_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id INTEGER NOT NULL,
                    model TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    prompt_tokens INTEGER NOT NULL,
                    completion_tokens INTEGER NOT NULL,
                    estimated_cost_usd REAL NOT NULL,
                    cache_hit INTEGER NOT NULL
                );
                """
            )

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    @staticmethod
    def cache_key(model: str, prompt: str) -> str:
        return hashlib.sha256(f"{model}\0{prompt}".encode("utf-8")).hexdigest()

    def get(self, key: str) -> str | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT response_json FROM llm_cache WHERE cache_key = ?", (key,)
            ).fetchone()
        return row[0] if row else None

    def put(self, key: str, model: str, response_json: str) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO llm_cache VALUES (?, ?, ?, ?)",
                (key, model, response_json, utc_now()),
            )

    def log_usage(
        self,
        case_id: int,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost: float,
        cache_hit: bool,
    ) -> None:
        with self.connect() as db:
            db.execute(
                """INSERT INTO usage_log
                   (case_id, model, created_at, prompt_tokens, completion_tokens,
                    estimated_cost_usd, cache_hit)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    case_id,
                    model,
                    utc_now(),
                    prompt_tokens,
                    completion_tokens,
                    cost,
                    int(cache_hit),
                ),
            )

    def original_usage(self, case_id: int, model: str) -> tuple[int, int, float]:
        with self.connect() as db:
            row = db.execute(
                """SELECT prompt_tokens, completion_tokens, estimated_cost_usd
                   FROM usage_log
                   WHERE case_id = ? AND model = ? AND cache_hit = 0
                   ORDER BY id DESC LIMIT 1""",
                (case_id, model),
            ).fetchone()
        return (int(row[0]), int(row[1]), float(row[2])) if row else (0, 0, 0.0)

    def total_estimated_cost(self) -> float:
        with self.connect() as db:
            row = db.execute(
                "SELECT COALESCE(SUM(estimated_cost_usd), 0) FROM usage_log"
            ).fetchone()
        return float(row[0])
