"""Playbook: self-evolving persistent knowledge store (JSON-lines)."""
from __future__ import annotations

import gzip
import json
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Entry types for which only the LATEST per logical key is kept during compaction.
# Older snapshots are archived, not kept in the live log, since they are superseded.
_LATEST_ONLY_TYPES: frozenset[str] = frozenset({
    "campaign_state",
    "deployment_state",
})

# Default compaction thresholds; overridable via Playbook(...) constructor.
DEFAULT_MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB
DEFAULT_MAX_ENTRIES = 5000
DEFAULT_COMPACT_CHECK_EVERY = 500  # check file size every N writes


class EntryType(StrEnum):
    STRATEGY_RESULT = "strategy_result"
    WHAT_FAILED = "what_failed"
    MARKET_OBSERVATION = "market_observation"
    CEO_PREFERENCE = "ceo_preference"
    CAMPAIGN_STATE = "campaign_state"
    DEPLOYMENT_STATE = "deployment_state"
    ALLOCATION_DECISION = "allocation_decision"
    AGENT_PERFORMANCE = "agent_performance"
    FACTOR_LIBRARY = "factor_library"
    TRUST_MILESTONE = "trust_milestone"
    EVALUATOR_DIVERGENCE = "evaluator_divergence"
    EVALUATOR_CALIBRATION = "evaluator_calibration"
    SCAFFOLDING_EXPERIMENT = "scaffolding_experiment"


@dataclass(frozen=True)
class PlaybookEntry:
    entry_type: EntryType
    content: dict[str, Any]
    tags: list[str]
    timestamp: str


class Playbook:
    """Append-only JSONL knowledge store with tag and full-text search.

    Compaction: when the live log exceeds `max_file_bytes` or `max_entries`,
    the full history is archived to `playbook.jsonl.archive.YYYYMMDD-HHMMSS.gz`
    and the live file is truncated to the latest entries (with special-case
    dedup for entry types where only the newest snapshot matters).
    """

    def __init__(
        self,
        path: str = "data/playbook.jsonl",
        max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        compact_check_every: int = DEFAULT_COMPACT_CHECK_EVERY,
    ):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: list[PlaybookEntry] | None = None
        self._max_file_bytes = max_file_bytes
        self._max_entries = max_entries
        self._compact_check_every = compact_check_every
        self._writes_since_check = 0

    async def add(
        self,
        entry_type: EntryType,
        content: dict[str, Any],
        tags: list[str] | None = None,
    ) -> PlaybookEntry:
        entry = PlaybookEntry(
            entry_type=entry_type,
            content=content,
            tags=tags or [],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        line = json.dumps({
            "entry_type": entry.entry_type.value,
            "content": entry.content,
            "tags": entry.tags,
            "timestamp": entry.timestamp,
        })
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        if self._cache is not None:
            self._cache.append(entry)
        self._writes_since_check += 1
        if self._writes_since_check >= self._compact_check_every:
            self._writes_since_check = 0
            self.compact_if_needed()
        return entry

    # ── Compaction ──

    def compact_if_needed(self) -> bool:
        """Compact if the file exceeds size or entry count thresholds.

        Returns True if compaction occurred.
        """
        if not self._path.exists():
            return False
        size = self._path.stat().st_size
        if size <= self._max_file_bytes:
            # Also count-check — cheap once we're here since cache may be loaded.
            entries = self._load_all()
            if len(entries) <= self._max_entries:
                return False
        return self._compact_now()

    def _compact_now(self) -> bool:
        """Archive current log and truncate to retained entries."""
        entries = self._load_all()
        if not entries:
            return False

        # 1. Archive full history to timestamped gzip.
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        archive = self._path.with_suffix(f".jsonl.archive.{stamp}.gz")
        try:
            with open(self._path, "rb") as src, gzip.open(archive, "wb") as dst:
                shutil.copyfileobj(src, dst)
        except OSError:
            logger.exception("Playbook compaction: failed to write archive")
            return False

        # 2. Build retained set: dedup latest-only types + tail of the rest.
        retained = self._retained_entries(entries)

        # 3. Atomic rewrite.
        tmp = self._path.with_suffix(".jsonl.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            for e in retained:
                f.write(json.dumps({
                    "entry_type": e.entry_type.value,
                    "content": e.content,
                    "tags": e.tags,
                    "timestamp": e.timestamp,
                }) + "\n")
        tmp.replace(self._path)
        self._cache = retained
        logger.info(
            "Playbook compacted: %d entries -> %d, archive=%s",
            len(entries), len(retained), archive.name,
        )
        return True

    def _retained_entries(self, entries: list[PlaybookEntry]) -> list[PlaybookEntry]:
        """Keep latest snapshot per logical key for `_LATEST_ONLY_TYPES`,
        plus tail of remaining entries up to `max_entries`."""
        latest_by_key: dict[tuple[str, str], PlaybookEntry] = {}
        other: list[PlaybookEntry] = []

        for e in entries:
            if e.entry_type.value in _LATEST_ONLY_TYPES:
                key = (e.entry_type.value, self._dedup_key(e))
                prior = latest_by_key.get(key)
                if prior is None or e.timestamp > prior.timestamp:
                    latest_by_key[key] = e
            else:
                other.append(e)

        # Tail of non-latest-only, so we keep the most recent history.
        tail_budget = max(0, self._max_entries - len(latest_by_key))
        other_tail = other[-tail_budget:] if tail_budget else []

        merged = list(latest_by_key.values()) + other_tail
        merged.sort(key=lambda e: e.timestamp)
        return merged

    @staticmethod
    def _dedup_key(entry: PlaybookEntry) -> str:
        """Identify the logical 'subject' of a snapshot entry for dedup."""
        content = entry.content or {}
        for field in ("campaign_id", "deployment_id", "id", "strategy_path", "name"):
            if field in content:
                return f"{field}={content[field]}"
        return json.dumps(content, sort_keys=True)[:128]

    def invalidate(self) -> None:
        """Clear the in-memory cache, forcing next read from disk."""
        self._cache = None

    def _load_all(self) -> list[PlaybookEntry]:
        if self._cache is not None:
            return self._cache
        if not self._path.exists():
            return []
        entries: list[PlaybookEntry] = []
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                entries.append(PlaybookEntry(
                    entry_type=EntryType(data["entry_type"]),
                    content=data["content"],
                    tags=data.get("tags", []),
                    timestamp=data["timestamp"],
                ))
        self._cache = entries
        return entries

    async def _load_all_async(self) -> list[PlaybookEntry]:
        """Async wrapper around ``_load_all``. Disk I/O + JSON parsing of
        a 20MB file would otherwise block the event loop for tens to
        hundreds of milliseconds — multiplied across query/search/recent
        calls during a cycle, this becomes one of the contributors to
        backend stalls. Cache makes subsequent calls free; only the
        first pays the to_thread cost.
        """
        import asyncio as _asyncio
        return await _asyncio.to_thread(self._load_all)

    async def query(
        self,
        tags: list[str] | None = None,
        entry_type: EntryType | None = None,
    ) -> list[PlaybookEntry]:
        entries = await self._load_all_async()
        if entry_type is not None:
            entries = [e for e in entries if e.entry_type == entry_type]
        if tags:
            tag_set = set(tags)
            entries = [e for e in entries if tag_set & set(e.tags)]
        return entries

    async def search(self, text: str) -> list[PlaybookEntry]:
        lower = text.lower()
        entries = await self._load_all_async()
        return [
            e for e in entries
            if lower in json.dumps(e.content).lower()
        ]

    async def recent(self, n: int = 20) -> list[PlaybookEntry]:
        entries = await self._load_all_async()
        return entries[-n:]
