"""Persistent mission memory with analytics endpoints."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class MemoryStore:
    db_path: Path = Path("godbot_memory.db")

    def __post_init__(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS missions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    objective TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    status TEXT NOT NULL,
                    final_report TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mission_id INTEGER NOT NULL,
                    agent_name TEXT NOT NULL,
                    model TEXT NOT NULL,
                    output TEXT NOT NULL,
                    thought_log TEXT NOT NULL,
                    FOREIGN KEY (mission_id) REFERENCES missions (id)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_agent_runs_mission_id ON agent_runs(mission_id)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_missions_created_at ON missions(created_at)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    mission_id INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES chat_sessions (id)
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_sessions_created_at ON chat_sessions(created_at)"
            )
            conn.commit()

    def save_mission(self, objective: str, status: str, final_report: str) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO missions (objective, status, final_report) VALUES (?, ?, ?)",
                (objective, status, final_report),
            )
            conn.commit()
            return int(cur.lastrowid)

    def save_agent_run(self, mission_id: int, agent_name: str, model: str, output: str, thought_log: list[str]) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO agent_runs (mission_id, agent_name, model, output, thought_log) VALUES (?, ?, ?, ?, ?)",
                (mission_id, agent_name, model, output, json.dumps(thought_log)),
            )
            conn.commit()

    def list_recent_missions(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, objective, created_at, status, final_report FROM missions ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def search_missions(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        pattern = f"%{query}%"
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, objective, created_at, status
                FROM missions
                WHERE objective LIKE ? OR final_report LIKE ?
                ORDER BY id DESC LIMIT ?
                """,
                (pattern, pattern, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_agent_runs(self, mission_id: int) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT agent_name, model, output, thought_log FROM agent_runs WHERE mission_id=? ORDER BY id",
                (mission_id,),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            payload = dict(row)
            payload["thought_log"] = json.loads(payload["thought_log"])
            out.append(payload)
        return out

    def get_stats(self) -> dict[str, Any]:
        with self._conn() as conn:
            missions = conn.execute("SELECT COUNT(*) AS c FROM missions").fetchone()["c"]
            success = conn.execute("SELECT COUNT(*) AS c FROM missions WHERE status='success'").fetchone()["c"]
            runs = conn.execute("SELECT COUNT(*) AS c FROM agent_runs").fetchone()["c"]
        ratio = (success / missions) if missions else 0.0
        return {
            "total_missions": missions,
            "successful_missions": success,
            "success_rate": round(ratio, 3),
            "agent_runs": runs,
        }

    def create_chat_session(self, title: str = "New chat") -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO chat_sessions (title) VALUES (?)",
                (title[:200],),
            )
            conn.commit()
            return int(cur.lastrowid)

    def add_chat_message(
        self,
        session_id: int,
        role: str,
        content: str,
        mission_id: int | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO chat_messages (session_id, role, content, mission_id) VALUES (?, ?, ?, ?)",
                (session_id, role, content, mission_id),
            )
            conn.commit()

    def list_chat_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, title, created_at FROM chat_sessions ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_chat_messages(self, session_id: int) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, role, content, mission_id, created_at FROM chat_messages WHERE session_id=? ORDER BY id",
                (session_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def update_chat_session_title(self, session_id: int, title: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE chat_sessions SET title=? WHERE id=?",
                (title[:200], session_id),
            )
            conn.commit()
