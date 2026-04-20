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
            bundle = await self._fetch_market_data(symbols, start, end, extra_fields)
            results["ohlcv"] = bundle.metadata

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

        macro = await self._auto_ingest_free_sources(start, end)
        if macro:
            results["macro"] = macro

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

    async def _auto_ingest_free_sources(self, start: str | None, end: str) -> dict:
        """Auto-ingest free macro and alternative sources."""
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
        macro_results: dict = {}
        requested_start = start or "1970-01-01"

        for plugin_name in free_names:
            plugin = pm.get("data", plugin_name)
            if plugin is None:
                continue
            try:
                series_ids = plugin.list_symbols()

                if plugin_name in _FUNDAMENTALS_ONLY:
                    fetched = {}
                    for sid in series_ids:
                        try:
                            fundamentals = plugin.fetch_fundamentals(sid)
                            if fundamentals:
                                fetched[sid] = {"fundamentals": fundamentals}
                        except Exception:
                            logger.debug("Failed fundamentals %s/%s", plugin_name, sid)
                    if fetched:
                        macro_results[plugin_name] = {
                            "series_count": len(fetched),
                            "type": "fundamentals",
                            "series": fetched,
                        }
                        logger.info(
                            "Auto-ingested %d fundamentals from %s",
                            len(fetched),
                            plugin_name,
                        )
                    continue

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
                if fetched:
                    macro_results[plugin_name] = {
                        "series_count": len(fetched),
                        "type": "time_series",
                        "series": fetched,
                    }
                    logger.info(
                        "Auto-ingested %d series from %s",
                        len(fetched),
                        plugin_name,
                    )
            except Exception:
                logger.debug("Auto-ingest failed for %s", plugin_name)

        return macro_results

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
