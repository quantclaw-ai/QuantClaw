"""Ingestor: fetches market data, macro indicators, and web intelligence.

Automatically ingests data from all configured free sources (no API key)
and any API-key sources the user has enabled during onboarding.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from quantclaw.agents.base import BaseAgent, AgentResult, AgentStatus

logger = logging.getLogger(__name__)

# Plugins that require no API key and are auto-ingested.
FREE_PLUGINS = frozenset([
    "data_yfinance", "data_fred", "data_sec_edgar", "data_worldbank",
    "data_imf", "data_bls", "data_treasury", "data_ecb", "data_bis",
    "data_cftc", "data_openinsider", "data_stooq",
])

# Fundamentals-only plugins: fetch_ohlcv returns empty, so auto-ingest uses
# fetch_fundamentals/fetch_fields instead.
_FUNDAMENTALS_ONLY = frozenset(["data_sec_edgar", "data_openinsider"])


class IngestorAgent(BaseAgent):
    name = "ingestor"
    model = "opus"
    daemon = False

    async def execute(self, task: dict) -> AgentResult:
        task_type = task.get("task", "")
        symbols = task.get("symbols", [])
        query = task.get("query", "")
        start = task.get("start") or None
        end = task.get("end") or datetime.now(timezone.utc).date().isoformat()

        # Extract suggested_data_sources from upstream Researcher.
        extra_fields = self._extract_suggested_fields(task)

        results = {}

        # Check cache inventory first and report what's already available.
        inventory = self._get_cache_inventory()
        if inventory:
            cached = {
                sym: info for sym, info in inventory.items()
                if info.get("fresh", False)
            }
            if cached:
                results["cached_symbols"] = list(cached.keys())
                logger.info(
                    "Cache has fresh data for %d symbols: %s",
                    len(cached),
                    list(cached.keys())[:10],
                )

        if symbols:
            # Distinguish cache hits from network fetches in the
            # narrative so it's obvious when the planner re-asks for
            # symbols already on disk. The underlying CachedDataPlugin
            # was already deduping the actual network calls — this just
            # surfaces what was happening invisibly before. ``cached``
            # may be empty if it's a fresh install or wasn't populated
            # for these specific symbols yet.
            cached_set = set(
                sym for sym, info in inventory.items()
                if info.get("fresh", False)
            ) if inventory else set()
            cache_hits = [s for s in symbols if s in cached_set]
            cache_misses = [s for s in symbols if s not in cached_set]

            # Phrasing note: a "cache hit" only confirms the file
            # exists and is mtime-fresh — the underlying date range may
            # not fully cover the new request, so the plugin can still
            # backfill missing tails. The narrative therefore says "in
            # cache" / "reusing", not "skipping network fetch".
            if cache_hits and not cache_misses:
                await self._narrate(
                    f"All {len(symbols)} symbol{'s' if len(symbols) != 1 else ''} in local cache "
                    f"({', '.join(cache_hits[:5])}{'…' if len(cache_hits) > 5 else ''}) — "
                    f"reusing on-disk data (only missing date ranges, if any, will be backfilled)."
                )
            elif cache_hits:
                await self._narrate(
                    f"Fetching {len(cache_misses)} new symbol{'s' if len(cache_misses) != 1 else ''} "
                    f"({', '.join(cache_misses[:5])}{'…' if len(cache_misses) > 5 else ''}); "
                    f"{len(cache_hits)} already in cache (reusing on-disk data)."
                )
            else:
                await self._narrate(
                    f"Fetching market data for {len(symbols)} symbol{'s' if len(symbols) != 1 else ''}"
                    + (f" ({', '.join(symbols[:5])}{'…' if len(symbols) > 5 else ''})" if symbols else "")
                    + (f" with {len(extra_fields)} extra fields" if extra_fields else "")
                    + "…"
                )

            bundle = await self._fetch_market_data(symbols, start, end, extra_fields)
            results["ohlcv"] = bundle.metadata
            ok_count = sum(
                1 for v in bundle.metadata.values()
                if isinstance(v, dict) and "error" not in v
            )
            # Always summarize the result — even when everything was in
            # cache, the bundle reports how many symbols actually
            # produced rows (cached files can be empty/corrupt).
            await self._narrate(
                f"Fetched {ok_count}/{len(symbols)} symbols successfully."
            )

            if bundle.availability:
                results["availability"] = bundle.availability
                recommended = (
                    bundle.availability.get("summary", {})
                    .get("recommended_common_window", {})
                )
                if recommended:
                    results["recommended_window"] = recommended

            derived_columns = self._derive_columns_from_bundle(bundle)
            if derived_columns:
                results["columns"] = derived_columns

            if extra_fields:
                enrichment = self._summarize_extra_fields(bundle, extra_fields)
                if enrichment:
                    results["extra_fields"] = enrichment

        await self._narrate("Auto-ingesting macro/alt-data sources…")
        macro = await self._auto_ingest_free_sources(start, end)
        if macro:
            results["macro"] = macro
            total_series = sum(
                v.get("series_count", 0) for v in macro.values() if isinstance(v, dict)
            )
            await self._narrate(
                f"Ingested {total_series} series from {len(macro)} macro source{'s' if len(macro) != 1 else ''}."
            )

        if "columns" not in results:
            results["columns"] = ["open", "high", "low", "close", "volume"]

        if query:
            search_results = await self._search_web(query)
            results["search"] = search_results

        if not symbols and not query and task_type:
            search_results = await self._search_web(task_type)
            results["search"] = search_results

        if not results:
            return AgentResult(
                status=AgentStatus.FAILED,
                error="No symbols or query provided",
            )

        if "ohlcv" in results:
            ohlcv = results["ohlcv"]
            if isinstance(ohlcv, dict):
                if "error" in ohlcv:
                    return AgentResult(
                        status=AgentStatus.FAILED,
                        error=f"Data fetch failed: {ohlcv['error']}",
                    )
                all_errors = all(
                    isinstance(value, dict) and "error" in value
                    for value in ohlcv.values()
                ) if ohlcv else False
                if all_errors and ohlcv:
                    first_error = next(iter(ohlcv.values()))["error"]
                    return AgentResult(
                        status=AgentStatus.FAILED,
                        error=f"Failed to fetch data for all symbols. First error: {first_error}",
                    )

        return AgentResult(status=AgentStatus.SUCCESS, data=results)

    def _get_cache_inventory(self) -> dict:
        """Check what data is already cached on disk."""
        try:
            from quantclaw.plugins.data_cache import CachedDataPlugin
            from quantclaw.plugins.manager import PluginManager

            data_plugin_names = self._config.get("plugins", {}).get("data", ["data_yfinance"])
            if isinstance(data_plugin_names, str):
                data_plugin_names = [data_plugin_names]
            pm = PluginManager()
            pm.discover()
            plugin = pm.get("data", data_plugin_names[0])
            if isinstance(plugin, CachedDataPlugin):
                return plugin.cached_inventory()
        except Exception:
            logger.debug("Could not query cache inventory")
        return {}

    def _extract_suggested_fields(self, task: dict) -> list[str]:
        """Extract suggested_data_sources from upstream Researcher results."""
        upstream = task.get("_upstream_results", {})
        for data in upstream.values():
            if isinstance(data, dict) and "suggested_data_sources" in data:
                sources = data["suggested_data_sources"]
                if isinstance(sources, list):
                    return [
                        source for source in sources
                        if isinstance(source, str) and source != "ohlcv"
                    ]
        return []

    def _derive_columns_from_bundle(self, bundle) -> list[str]:
        columns: list[str] = []
        seen: set[str] = set()
        for meta in bundle.metadata.values():
            if not isinstance(meta, dict):
                continue
            for column in meta.get("columns", []):
                if column not in seen:
                    seen.add(column)
                    columns.append(column)
        return columns or ["open", "high", "low", "close", "volume"]

    def _summarize_extra_fields(self, bundle, requested_fields: list[str]) -> dict:
        enrichment: dict = {}
        for symbol, meta in bundle.metadata.items():
            if not isinstance(meta, dict):
                continue
            field_history = meta.get("field_history", {})
            available_fields = [
                field_name for field_name in requested_fields
                if field_name in field_history
            ]
            if not available_fields:
                continue
            enrichment[symbol] = {
                "fields": available_fields,
                "rows": meta.get("rows", 0),
                "history": {
                    field_name: field_history[field_name]
                    for field_name in available_fields
                },
            }
        return enrichment

    @staticmethod
    def _ingest_one_plugin_sync(plugin, plugin_name: str, requested_start: str, end: str) -> dict | None:
        """Synchronously fetch all symbols for one plugin.

        Runs entirely off the event loop (via ``asyncio.to_thread`` from
        the caller). Returns a result dict or None if no usable data.
        """
        try:
            series_ids = plugin.list_symbols()
        except Exception:
            logger.debug("list_symbols failed for %s", plugin_name)
            return None

        if plugin_name in _FUNDAMENTALS_ONLY:
            fetched = {}
            for sid in series_ids:
                try:
                    fundamentals = plugin.fetch_fundamentals(sid)
                    if fundamentals:
                        fetched[sid] = {"fundamentals": fundamentals}
                except Exception:
                    logger.debug("Failed fundamentals %s/%s", plugin_name, sid)
            if not fetched:
                return None
            logger.info(
                "Auto-ingested %d fundamentals from %s",
                len(fetched), plugin_name,
            )
            return {
                "series_count": len(fetched),
                "type": "fundamentals",
                "series": fetched,
            }

        fetched = {}
        for sid in series_ids:
            try:
                df = plugin.fetch_ohlcv(sid, requested_start, end)
                if not df.empty:
                    fetched[sid] = {
                        "rows": len(df),
                        "start": str(df.index[0]),
                        "end": str(df.index[-1]),
                    }
            except Exception:
                logger.debug("Failed to fetch %s/%s", plugin_name, sid)
        if not fetched:
            return None
        logger.info(
            "Auto-ingested %d series from %s", len(fetched), plugin_name,
        )
        return {
            "series_count": len(fetched),
            "type": "time_series",
            "series": fetched,
        }

    async def _auto_ingest_free_sources(self, start: str | None, end: str) -> dict:
        """Auto-ingest free macro and alternative sources.

        Each free plugin's ``fetch_ohlcv`` / ``fetch_fundamentals`` uses
        synchronous ``requests.get`` (DataPlugin is a sync interface).
        Calling them directly from this async method blocks the event
        loop for the full network duration — for WorldBank that's
        hundreds of sequential calls and was wedging the loop for 17+
        minutes, causing /api/health to time out, WS broadcasts to
        stall, and the floor to look frozen.
        We dispatch each plugin's whole sync workload to a thread and
        run plugins in parallel via ``asyncio.gather``.
        """
        import asyncio
        from quantclaw.plugins.manager import PluginManager

        data_plugin_names = self._config.get("plugins", {}).get("data", ["data_yfinance"])
        if isinstance(data_plugin_names, str):
            data_plugin_names = [data_plugin_names]

        free_names = [
            name for name in data_plugin_names
            if name in FREE_PLUGINS and name not in ("data_yfinance", "data_stooq")
        ]
        if not free_names:
            return {}

        pm = PluginManager()
        pm.discover()
        requested_start = start or "1970-01-01"

        async def run_one(plugin_name: str):
            plugin = pm.get("data", plugin_name)
            if plugin is None:
                return plugin_name, None
            try:
                result = await asyncio.to_thread(
                    self._ingest_one_plugin_sync, plugin, plugin_name, requested_start, end,
                )
                return plugin_name, result
            except Exception:
                logger.debug("Auto-ingest failed for %s", plugin_name)
                return plugin_name, None

        outcomes = await asyncio.gather(*(run_one(n) for n in free_names))
        return {name: result for name, result in outcomes if result is not None}

    async def _fetch_market_data(
        self,
        symbols: list[str],
        start: str | None,
        end: str,
        extra_fields: list[str] | None = None,
    ):
        """Fetch market data plus provider-depth metadata."""
        from quantclaw.agents.market_data import MarketDataBundle, load_market_data

        try:
            return load_market_data(
                self._config,
                symbols,
                start,
                end,
                extra_fields=extra_fields,
            )
        except Exception as exc:
            logger.exception("Data plugin initialization failed")
            return MarketDataBundle(
                frames={},
                metadata={"error": str(exc)},
                availability={},
            )

    async def _search_web(self, query: str) -> list[dict]:
        """Search the web using the shared search tool."""
        from quantclaw.agents.tools.web_search import is_search_allowed, web_search

        if not is_search_allowed(self.name):
            return [{"error": "Search not allowed for this agent"}]

        try:
            return await web_search(query, config=self._config, max_results=5)
        except Exception as exc:
            logger.exception("Web search failed for query: %s", query)
            return [{"error": str(exc)}]
