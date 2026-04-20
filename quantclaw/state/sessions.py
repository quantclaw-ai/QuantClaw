"""Session tracking."""
from __future__ import annotations
from quantclaw.state.db import StateDB

class SessionStore:
    def __init__(self, db: StateDB):
        self._db = db

    async def start(self, session_type: str, metadata: str = None) -> int:
        cursor = await self._db.conn.execute(
            "INSERT INTO sessions (session_type, metadata) VALUES (?, ?)",
            (session_type, metadata),
        )
        await self._db.conn.commit()
        return cursor.lastrowid

    async def end(self, session_id: int):
        await self._db.conn.execute(
            "UPDATE sessions SET ended_at = CURRENT_TIMESTAMP WHERE id = ?", (session_id,)
        )
        await self._db.conn.commit()
