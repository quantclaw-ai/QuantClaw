"""Live model catalog: fetch each provider's available models dynamically.

Replaces hardcoded model lists scattered across the frontend with a single
backend endpoint that queries each provider's /v1/models endpoint at runtime
and caches the response. New model releases (e.g. gpt-5.5) appear automatically
without code changes.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Cache TTL: model lists rarely change within an hour. Reduces upstream calls.
_CACHE_TTL_SECONDS = 3600

# In-memory cache: { (provider, key_fingerprint) -> {"models": [...], "fetched_at": ts} }
_cache: dict[tuple[str, str], dict[str, Any]] = {}
_cache_lock = asyncio.Lock()

# Hardcoded baseline — only used when live fetch fails AND no key is configured.
# Keep these conservative; the dynamic fetch is the source of truth.
_FALLBACK_MODELS: dict[str, list[str]] = {
    # OpenAI Codex OAuth has no public model catalog endpoint, so OAuth-only
    # users see this fallback list. The custom-model input on the settings page
    # is the escape hatch for newer releases (gpt-5.5, gpt-6, etc.) until they
    # show up here on a future package update.
    "openai": [
        "gpt-5",
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.3-codex",
        "gpt-4.1",
        "gpt-4o",
    ],
    "anthropic": [
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
    ],
    "google": [
        "gemini-3.1-pro-preview",
        "gemini-3-flash-preview",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
    ],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "xai": [
        "grok-4.20-0309-reasoning",
        "grok-4.20-0309-non-reasoning",
        "grok-4-1-fast-reasoning",
    ],
    "mistral": [
        "mistral-large-latest",
        "mistral-medium-latest",
        "mistral-small-latest",
        "codestral-2501",
    ],
    "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "openai/gpt-oss-120b",
        "qwen/qwen3-32b",
    ],
    "openrouter": [
        "openai/gpt-5.4",
        "anthropic/claude-opus-4-6",
        "anthropic/claude-sonnet-4-6",
        "google/gemini-3.1-pro-preview",
        "deepseek/deepseek-chat",
    ],
    "together": [
        "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "deepseek-ai/DeepSeek-V3",
        "Qwen/Qwen2.5-72B-Instruct-Turbo",
    ],
    "ollama": [],  # Ollama lives locally; empty list if daemon isn't running
}

# Patterns that mark a model as NOT chat-capable. Kept narrow on purpose: a
# future chat model with a name we didn't anticipate must NOT be filtered out.
# Each pattern targets a known non-chat product family, not a generic substring.
import re as _re

_NON_CHAT_REGEXES = [
    _re.compile(r"embedding", _re.I),         # text-embedding-*, embedding-*
    _re.compile(r"\bembed[-_]", _re.I),       # embed-v3, etc.
    _re.compile(r"\bwhisper", _re.I),         # whisper-1, whisper-large
    _re.compile(r"(?:^|[-/])tts(?:-|$)", _re.I),  # tts-1, gpt-4o-mini-tts
    _re.compile(r"transcribe", _re.I),        # gpt-4o-mini-transcribe
    _re.compile(r"dall-?e", _re.I),           # dall-e-2, dalle-3
    _re.compile(r"image[-_]?(?:1|gen)", _re.I),  # gpt-image-1, imagegen
    _re.compile(r"moderation", _re.I),        # text-moderation-*, omni-moderation-*
    _re.compile(r"\brerank", _re.I),          # cohere rerank
    _re.compile(r"\b(?:babbage|ada|davinci)-\d", _re.I),  # legacy completion
]


def _is_chat_model(model_id: str) -> bool:
    """Conservative filter: only exclude models that match a known non-chat
    pattern. Anything else (including unrecognized future names) passes."""
    return not any(rx.search(model_id) for rx in _NON_CHAT_REGEXES)


def _key_fingerprint(api_key: str | None) -> str:
    """Short, non-reversible fingerprint so different keys get separate cache slots."""
    if not api_key:
        return "anon"
    return f"k{hash(api_key) & 0xFFFF:04x}"


async def get_models(
    provider: str,
    api_key: str | None,
    base_url: str | None = None,
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Return chat-capable models for a provider, with caching and fallback.

    Returns: { "models": [...], "source": "live"|"cache"|"fallback", "fetched_at": float|None }
    """
    cache_key = (provider, _key_fingerprint(api_key))
    now = time.time()

    if not force_refresh:
        async with _cache_lock:
            cached = _cache.get(cache_key)
            if cached and (now - cached["fetched_at"]) < _CACHE_TTL_SECONDS:
                return {**cached, "source": "cache"}

    fetcher = _PROVIDER_FETCHERS.get(provider)
    if not fetcher:
        logger.warning("No fetcher for provider %s; using fallback", provider)
        return {
            "models": _FALLBACK_MODELS.get(provider, []),
            "source": "fallback",
            "fetched_at": None,
        }

    try:
        models = await fetcher(api_key=api_key, base_url=base_url)
        models = sorted({m for m in models if _is_chat_model(m)})
        result = {"models": models, "fetched_at": now}
        async with _cache_lock:
            _cache[cache_key] = result
        return {**result, "source": "live"}
    except Exception as exc:
        logger.warning("Live model fetch failed for %s: %s", provider, exc)
        return {
            "models": _FALLBACK_MODELS.get(provider, []),
            "source": "fallback",
            "fetched_at": None,
        }


# ─── Provider fetchers ────────────────────────────────────────────────────


async def _fetch_openai_compat(
    api_key: str | None,
    base_url: str,
    *,
    auth_header: str = "Authorization",
    auth_prefix: str = "Bearer ",
) -> list[str]:
    """OpenAI-compatible /models endpoint. Used by openai, deepseek, xai,
    mistral, groq, openrouter, together (most cloud providers)."""
    if not api_key:
        raise RuntimeError("api_key required")
    headers = {auth_header: f"{auth_prefix}{api_key}"}
    url = f"{base_url.rstrip('/')}/models"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        payload = resp.json()
    data = payload.get("data") or payload.get("models") or []
    return [item.get("id") for item in data if item.get("id")]


def _is_openai_oauth_token(token: str | None) -> bool:
    """OpenAI OAuth tokens are JWTs (eyJ...); standard API keys start with sk-."""
    if not token:
        return False
    return not token.startswith("sk-") and token.startswith("eyJ")


def _extract_chatgpt_account_id(token: str) -> str:
    """Pull chatgpt_account_id from the OAuth JWT payload (matches sidecar logic)."""
    import base64
    import json as _json
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return ""
        # base64url decode payload, padding-tolerant
        payload_raw = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = _json.loads(base64.urlsafe_b64decode(payload_raw))
        return (
            payload.get("https://api.openai.com/auth", {}).get("chatgpt_account_id", "")
        )
    except Exception:
        return ""


async def _fetch_openai_codex_models(token: str) -> list[str]:
    """Fetch the model list from chatgpt.com/backend-api — what the Codex/ChatGPT
    app uses to discover models available to a subscription account. Includes
    new releases like gpt-5.5 the moment OpenAI rolls them out per-account."""
    account_id = _extract_chatgpt_account_id(token)
    headers = {
        "Authorization": f"Bearer {token}",
        "originator": "quantclaw",
        "OpenAI-Beta": "responses=experimental",
    }
    if account_id:
        headers["chatgpt-account-id"] = account_id

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://chatgpt.com/backend-api/models", headers=headers
        )
        resp.raise_for_status()
        payload = resp.json()

    # chatgpt.com returns one of two shapes: {"models": [...]} or
    # {"categories": [{"category_models": [...]}, ...]}. Handle both.
    out: list[str] = []
    for m in payload.get("models", []):
        slug = m.get("slug") or m.get("id")
        if slug:
            out.append(slug)
    for cat in payload.get("categories", []):
        for m in cat.get("category_models", []) or cat.get("models", []):
            slug = m.get("slug") or m.get("id")
            if slug:
                out.append(slug)
    return out


async def _fetch_openai(api_key: str | None, base_url: str | None) -> list[str]:
    # Route OAuth tokens to chatgpt.com/backend-api (where Codex models live);
    # standard sk- keys go to api.openai.com/v1/models.
    if _is_openai_oauth_token(api_key):
        return await _fetch_openai_codex_models(api_key)
    return await _fetch_openai_compat(
        api_key, base_url or "https://api.openai.com/v1"
    )


async def _fetch_anthropic(api_key: str | None, base_url: str | None) -> list[str]:
    if not api_key:
        raise RuntimeError("api_key required")
    base = (base_url or "https://api.anthropic.com").rstrip("/")
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    url = f"{base}/v1/models"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        payload = resp.json()
    data = payload.get("data", [])
    return [item.get("id") for item in data if item.get("id")]


async def _fetch_google(api_key: str | None, base_url: str | None) -> list[str]:
    if not api_key:
        raise RuntimeError("api_key required")
    base = (base_url or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    url = f"{base}/models?key={api_key}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        payload = resp.json()
    models = payload.get("models", [])
    out: list[str] = []
    for m in models:
        # Only include models that support generateContent (chat-capable)
        methods = m.get("supportedGenerationMethods", [])
        if "generateContent" not in methods:
            continue
        name = m.get("name", "")
        # API returns "models/gemini-1.5-pro"; strip the prefix for UX consistency
        if name.startswith("models/"):
            name = name[len("models/"):]
        if name:
            out.append(name)
    return out


async def _fetch_deepseek(api_key: str | None, base_url: str | None) -> list[str]:
    return await _fetch_openai_compat(api_key, base_url or "https://api.deepseek.com/v1")


async def _fetch_xai(api_key: str | None, base_url: str | None) -> list[str]:
    return await _fetch_openai_compat(api_key, base_url or "https://api.x.ai/v1")


async def _fetch_mistral(api_key: str | None, base_url: str | None) -> list[str]:
    return await _fetch_openai_compat(api_key, base_url or "https://api.mistral.ai/v1")


async def _fetch_groq(api_key: str | None, base_url: str | None) -> list[str]:
    return await _fetch_openai_compat(api_key, base_url or "https://api.groq.com/openai/v1")


async def _fetch_openrouter(api_key: str | None, base_url: str | None) -> list[str]:
    # OpenRouter exposes /models without auth — convenient.
    base = (base_url or "https://openrouter.ai/api/v1").rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{base}/models", headers=headers)
        resp.raise_for_status()
        payload = resp.json()
    data = payload.get("data", [])
    return [item.get("id") for item in data if item.get("id")]


async def _fetch_together(api_key: str | None, base_url: str | None) -> list[str]:
    if not api_key:
        raise RuntimeError("api_key required")
    # Together's /models endpoint returns a flat array, not {data: [...]}
    base = (base_url or "https://api.together.xyz/v1").rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{base}/models", headers=headers)
        resp.raise_for_status()
        payload = resp.json()
    if isinstance(payload, list):
        return [item.get("id") for item in payload if item.get("id")]
    data = payload.get("data", [])
    return [item.get("id") for item in data if item.get("id")]


async def _fetch_ollama(api_key: str | None, base_url: str | None) -> list[str]:
    # Ollama runs locally; no auth, different endpoint shape.
    base = (base_url or "http://localhost:11434").rstrip("/")
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"{base}/api/tags")
        resp.raise_for_status()
        payload = resp.json()
    return [m.get("name") for m in payload.get("models", []) if m.get("name")]


_PROVIDER_FETCHERS = {
    "openai": _fetch_openai,
    "anthropic": _fetch_anthropic,
    "google": _fetch_google,
    "deepseek": _fetch_deepseek,
    "xai": _fetch_xai,
    "mistral": _fetch_mistral,
    "groq": _fetch_groq,
    "openrouter": _fetch_openrouter,
    "together": _fetch_together,
    "ollama": _fetch_ollama,
}
