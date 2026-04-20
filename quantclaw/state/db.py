"""SQLite state database for QuantClaw."""
from __future__ import annotations
import aiosqlite
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT NOT NULL,
    command TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    result TEXT,
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    payload TEXT,
    source_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS plans (
    id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    steps_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_type TEXT NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP,
    metadata TEXT
);
"""

class StateDB:
    def __init__(self, conn: aiosqlite.Connection):
        self._conn = conn

    @classmethod
    async def create(cls, db_path: str) -> StateDB:
        conn = await aiosqlite.connect(db_path)
        conn.row_factory = aiosqlite.Row
        await conn.executescript(SCHEMA)
        await conn.commit()
        return cls(conn)

    @property
    def conn(self) -> aiosqlite.Connection:
        return self._conn

    async def close(self):
        await self._conn.close()
