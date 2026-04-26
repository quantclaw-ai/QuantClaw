"use client";
import { useEffect, useState } from "react";

const API = "http://localhost:24120";

interface CatalogResponse {
  models: string[];
  source: "live" | "cache" | "fallback";
  fetched_at: number | null;
}

interface UseProviderModelsResult {
  models: string[];
  loading: boolean;
  source: CatalogResponse["source"] | null;
  refresh: () => void;
}

const _memCache = new Map<string, { models: string[]; source: CatalogResponse["source"]; ts: number }>();
const CLIENT_TTL_MS = 5 * 60 * 1000; // 5 min — backend has its own 1h cache

function readApiKey(providerId: string): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(`quantclaw_key_${providerId}`) ?? "";
}

export function useProviderModels(
  providerId: string,
  fallback: string[] = [],
): UseProviderModelsResult {
  const [models, setModels] = useState<string[]>(fallback);
  const [loading, setLoading] = useState(false);
  const [source, setSource] = useState<CatalogResponse["source"] | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!providerId) return;

    const apiKey = readApiKey(providerId);
    const cacheKey = `${providerId}::${apiKey ? "k" : "anon"}`;
    const cached = _memCache.get(cacheKey);
    if (cached && Date.now() - cached.ts < CLIENT_TTL_MS && tick === 0) {
      setModels(cached.models);
      setSource(cached.source);
      return;
    }

    let cancelled = false;
    setLoading(true);
    const headers: Record<string, string> = {};
    if (apiKey) headers["x-provider-key"] = apiKey;

    const url = `${API}/api/providers/${encodeURIComponent(providerId)}/models${tick > 0 ? "?refresh=true" : ""}`;
    fetch(url, { headers })
      .then((res) => res.json() as Promise<CatalogResponse>)
      .then((data) => {
        if (cancelled) return;
        const list = data.models?.length ? data.models : fallback;
        setModels(list);
        setSource(data.source);
        _memCache.set(cacheKey, { models: list, source: data.source, ts: Date.now() });
      })
      .catch(() => {
        if (cancelled) return;
        setModels(fallback);
        setSource("fallback");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // fallback intentionally excluded — it's a stable default per call site
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [providerId, tick]);

  return {
    models,
    loading,
    source,
    refresh: () => setTick((n) => n + 1),
  };
}

/** Provider IDs that the dashboard supports. */
const ALL_PROVIDERS = [
  "ollama",
  "openai",
  "anthropic",
  "google",
  "deepseek",
  "xai",
  "mistral",
  "groq",
  "openrouter",
  "together",
] as const;

interface AvailableModel {
  provider: string;
  model: string;
}

interface UseAllAvailableModelsResult {
  available: AvailableModel[];
  loading: boolean;
}

/**
 * Returns every model available across all configured providers, fetched live
 * from each provider's /v1/models endpoint. A provider is considered "configured"
 * if it has either an OAuth flag or an API key in localStorage (or for ollama,
 * if the daemon is reachable).
 */
export function useAllAvailableModels(): UseAllAvailableModelsResult {
  const [available, setAvailable] = useState<AvailableModel[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const configured = ALL_PROVIDERS.filter((p) => {
      if (p === "ollama") return true; // catalog endpoint will probe localhost
      const hasKey = !!localStorage.getItem(`quantclaw_key_${p}`);
      const hasOAuth = localStorage.getItem(`quantclaw_oauth_${p}`) === "true";
      return hasKey || hasOAuth;
    });

    let cancelled = false;
    setLoading(true);

    Promise.all(
      configured.map(async (providerId) => {
        const apiKey = localStorage.getItem(`quantclaw_key_${providerId}`) ?? "";
        const headers: Record<string, string> = {};
        if (apiKey) headers["x-provider-key"] = apiKey;
        try {
          const res = await fetch(
            `${API}/api/providers/${encodeURIComponent(providerId)}/models`,
            { headers },
          );
          const data = (await res.json()) as CatalogResponse;
          return (data.models ?? []).map((m) => ({ provider: providerId, model: m }));
        } catch {
          return [];
        }
      }),
    ).then((lists) => {
      if (cancelled) return;
      setAvailable(lists.flat());
      setLoading(false);
    });

    return () => {
      cancelled = true;
    };
  }, []);

  return { available, loading };
}
