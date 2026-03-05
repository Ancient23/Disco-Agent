from __future__ import annotations

import json
from datetime import datetime, timezone

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow TEXT NOT NULL,
    project TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT 'Win64',
    params TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending',
    discord_channel_id TEXT NOT NULL DEFAULT '',
    discord_message_id TEXT NOT NULL DEFAULT '',
    requested_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    result TEXT
);
"""


class TaskQueue:
    def __init__(self, db_path: str = "tasks.db"):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_SCHEMA)

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    async def enqueue(
        self,
        workflow: str,
        project: str,
        platform: str,
        params: dict,
        discord_channel_id: str,
        discord_message_id: str,
        requested_by: str,
    ) -> int:
        assert self._db
        cursor = await self._db.execute(
            """INSERT INTO tasks
               (workflow, project, platform, params,
                discord_channel_id, discord_message_id, requested_by, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                workflow, project, platform, json.dumps(params),
                discord_channel_id, discord_message_id, requested_by, self._now(),
            ),
        )
        await self._db.commit()
        return cursor.lastrowid

    async def fetch_next(self) -> dict | None:
        assert self._db
        cursor = await self._db.execute(
            "SELECT * FROM tasks WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1"
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        task = dict(row)
        now = self._now()
        await self._db.execute(
            "UPDATE tasks SET status = 'running', started_at = ? WHERE id = ?",
            (now, task["id"]),
        )
        await self._db.commit()
        task["status"] = "running"
        task["started_at"] = now
        return task

    async def complete(self, task_id: int, result: dict) -> None:
        assert self._db
        await self._db.execute(
            "UPDATE tasks SET status = 'completed', finished_at = ?, result = ? WHERE id = ?",
            (self._now(), json.dumps(result), task_id),
        )
        await self._db.commit()

    async def fail(self, task_id: int, result: dict) -> None:
        assert self._db
        await self._db.execute(
            "UPDATE tasks SET status = 'failed', finished_at = ?, result = ? WHERE id = ?",
            (self._now(), json.dumps(result), task_id),
        )
        await self._db.commit()

    async def cancel(self, task_id: int) -> None:
        assert self._db
        await self._db.execute(
            "UPDATE tasks SET status = 'cancelled', finished_at = ? WHERE id = ?",
            (self._now(), task_id),
        )
        await self._db.commit()

    async def is_cancelled(self, task_id: int) -> bool:
        assert self._db
        cursor = await self._db.execute(
            "SELECT status FROM tasks WHERE id = ?", (task_id,)
        )
        row = await cursor.fetchone()
        return row is not None and row["status"] == "cancelled"

    async def get(self, task_id: int) -> dict | None:
        assert self._db
        cursor = await self._db.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_active(self) -> list[dict]:
        assert self._db
        cursor = await self._db.execute(
            "SELECT * FROM tasks WHERE status IN ('pending', 'running') ORDER BY created_at ASC"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
