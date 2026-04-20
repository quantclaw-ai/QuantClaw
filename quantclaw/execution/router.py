"""LLM model routing per agent, with cost tracking and budget warnings."""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Fallback defaults when config has no 'temperatures' section.
# Config file (quantclaw.yaml) temperatures override these values.
AGENT_TEMPERATURES: dict[str, float] = {
    "miner": 0.9,
    "researcher": 0.7,
    "scheduler": 0.5,
    "trainer": 0.5,
    "debugger": 0.3,
    "reporter": 0.3,
    "ingestor": 0.2,
    "validator": 0.2,
    "sentinel": 0.2,
    "risk_monitor": 0.1,
    "executor": 0.1,
    "compliance": 0.1,
}

SIDECAR_URL = "http://localhost:24122"

# Default USD per 1M tokens: {model_substring: (input_rate, output_rate)}.
# Longest-matching substring wins. Override via config.cost.rates.
DEFAULT_RATES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus":       (15.00, 75.00),
    "claude-sonnet":     ( 3.00, 15.00),
    "claude-haiku":      ( 0.80,  4.00),
    "gpt-4o-mini":       ( 0.15,  0.60),
    "gpt-4o":            ( 2.50, 10.00),
    "gpt-5":             ( 5.00, 20.00),
    "o1":                (15.00, 60.00),
}


def _lookup_rate(model: str, rates: dict[str, tuple[float, float]]) -> tuple[float, float]:
    """Longest-substring match; fall back to (0, 0) meaning unknown cost."""
    best: tuple[str, tuple[float, float]] | None = None
    for key, rate in rates.items():
        if key in model and (best is None or len(key) > len(best[0])):
            best = (key, rate)
    return best[1] if best else (0.0, 0.0)


@dataclass
class CostTracker:
    """Cumulative LLM spend. Publishes cost.budget_warning when thresholds trip."""

    budget_usd: float = 10.0
    warning_thresholds: tuple[float, ...] = (0.5, 0.8, 1.0)
    rates: dict[str, tuple[float, float]] = field(default_factory=lambda: dict(DEFAULT_RATES_PER_MTOK))
    total_usd: float = 0.0
    per_agent_usd: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    per_model_tokens: dict[str, dict[str, int]] = field(
        default_factory=lambda: defaultdict(lambda: {"input": 0, "output": 0})
    )
    _warned_at: set[float] = field(default_factory=set)

    def record(self, agent: str, model: str, input_tokens: int, output_tokens: int) -> float:
        """Record a call and return its USD cost."""
        in_rate, out_rate = _lookup_rate(model, self.rates)
        cost = (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000
        self.total_usd += cost
        self.per_agent_usd[agent] += cost
        stats = self.per_model_tokens[model]
        stats["input"] += input_tokens
        stats["output"] += output_tokens
        return cost

    def next_threshold_to_fire(self) -> float | None:
        """Return a threshold fraction (0.5/0.8/1.0/...) we have newly crossed, else None."""
        if self.budget_usd <= 0:
            return None
        frac = self.total_usd / self.budget_usd
        for threshold in sorted(self.warning_thresholds):
            if frac >= threshold and threshold not in self._warned_at:
                self._warned_at.add(threshold)
                return threshold
        return None

    def summary(self) -> dict:
        return {
            "total_usd": round(self.total_usd, 4),
            "budget_usd": self.budget_usd,
            "budget_used_pct": round(self.total_usd / self.budget_usd * 100, 1) if self.budget_usd else None,
            "per_agent_usd": {k: round(v, 4) for k, v in self.per_agent_usd.items()},
            "per_model_tokens": dict(self.per_model_tokens),
        }


class LLMRouter:
    def __init__(self, config: dict, event_bus=None):
        self._config = config
        self._models = config.get("models", {})
        self._providers = config.get("providers", {})
        self._temperatures = config.get("temperatures", {})
        self._api_key = config.get("api_key", "")  # Frontend-provided API key
        self._oauth_token = config.get("oauth_token", "")  # OAuth access token
        self._event_bus = event_bus

        cost_cfg = config.get("cost", {})
        rates = dict(DEFAULT_RATES_PER_MTOK)
        rates.update({k: tuple(v) for k, v in cost_cfg.get("rates", {}).items()})
        self._cost = CostTracker(
            budget_usd=float(cost_cfg.get("budget_usd", 10.0)),
            warning_thresholds=tuple(cost_cfg.get("warning_thresholds", (0.5, 0.8, 1.0))),
            rates=rates,
        )

    @property
    def cost(self) -> CostTracker:
        return self._cost

    def get_model(self, agent_name: str) -> str:
        return self._models.get(agent_name, "opus")

    def get_provider(self, agent_name: str) -> dict:
        model_key = self.get_model(agent_name)
        return self._providers.get(model_key, {"provider": "anthropic", "model": "claude-opus-4-6"})

    def get_ollama_url(self) -> str:
        return self._config.get("ollama_url", "http://localhost:11434")

    def get_temperature(self, agent_name: str) -> float:
        if agent_name in self._temperatures:
            return self._temperatures[agent_name]
        return AGENT_TEMPERATURES.get(agent_name, 0.5)

    async def call(self, agent_name: str, messages: list[dict], system: str = None,
                   temperature: float | None = None) -> str:
        provider = self.get_provider(agent_name)
        provider_name = provider.get("provider", "anthropic")
        model = provider.get("model", "claude-opus-4-6")

        temp = temperature if temperature is not None else self.get_temperature(agent_name)

        # Resolve the correct OAuth token for THIS provider (not a random one).
        # Using a provider-mismatched bearer token is what produces "Invalid bearer
        # token" from the sidecar, because OAuth tokens are provider-specific.
        provider_oauth = self._get_provider_oauth(provider_name) if provider_name in ("openai", "anthropic") else ""

        logger.info(
            "LLMRouter.call: agent=%s, provider=%s, model=%s, has_api_key=%s, has_oauth=%s",
            agent_name, provider_name, model,
            bool(self._api_key), bool(provider_oauth),
        )

        # OAuth path: only when we have a token for THIS specific provider.
        if provider_oauth and provider_name in ("openai", "anthropic"):
            text = await self._call_sidecar(provider_name, model, messages, system, temp, provider_oauth)
            return text

        # API key path: call provider directly and capture usage.
        if provider_name == "anthropic":
            if not self._api_key:
                raise RuntimeError(self._friendly_auth_error("anthropic"))
            text, in_tok, out_tok = await self._call_anthropic(model, messages, system, temp)
        elif provider_name == "openai":
            if not self._api_key:
                raise RuntimeError(self._friendly_auth_error("openai"))
            text, in_tok, out_tok = await self._call_openai(model, messages, system, temp)
        elif provider_name == "ollama":
            text, in_tok, out_tok = await self._call_ollama(model, messages, system, temp)
        else:
            raise ValueError(f"Unknown provider: {provider_name}")

        self._cost.record(agent_name, model, in_tok, out_tok)
        await self._maybe_warn_budget()
        return text

    def _get_provider_oauth(self, provider_name: str) -> str:
        """Return a valid OAuth access token for the given provider, or empty string.

        Looks in ``data/oauth_credentials.json`` first (the authoritative store,
        per-provider). Falls back to the legacy single ``self._oauth_token`` only
        when that field was explicitly set AND there are no stored OAuth creds —
        a fallback for scripted / testing scenarios. Never returns a token that
        belongs to a DIFFERENT provider than requested.
        """
        try:
            from quantclaw.dashboard.oauth import get_access_token
            token = get_access_token(provider_name)
            if token:
                return token
        except Exception:
            logger.exception("LLMRouter: failed to read OAuth store")

        # Legacy fallback: only trust self._oauth_token when NO per-provider creds
        # exist on disk at all — otherwise we risk wrong-provider token reuse.
        try:
            from quantclaw.dashboard.oauth import _load_credentials
            if not _load_credentials() and self._oauth_token:
                return self._oauth_token
        except Exception:
            pass
        return ""

    @staticmethod
    def _friendly_auth_error(provider_name: str) -> str:
        """A message the scheduler can surface verbatim to the user."""
        pretty = {"openai": "OpenAI / ChatGPT", "anthropic": "Anthropic / Claude"}.get(provider_name, provider_name)
        env_var = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}.get(provider_name, provider_name.upper() + "_API_KEY")
        return (
            f"This task was routed to {pretty} but no credentials are configured "
            f"for that provider. Either sign in to {pretty} in Settings, set "
            f"{env_var} in your environment, or change the model assignment in "
            f"Settings → Agents to a provider you are authenticated with."
        )

    async def _maybe_warn_budget(self) -> None:
        """Publish cost.budget_warning on newly-crossed thresholds."""
        threshold = self._cost.next_threshold_to_fire()
        if threshold is None or self._event_bus is None:
            return
        try:
            from quantclaw.events.types import Event, EventType
            await self._event_bus.publish(Event(
                type=EventType.COST_BUDGET_WARNING,
                source_agent="llm_router",
                payload={
                    "threshold_pct": int(threshold * 100),
                    "total_usd": round(self._cost.total_usd, 4),
                    "budget_usd": self._cost.budget_usd,
                    "per_agent_usd": {k: round(v, 4) for k, v in self._cost.per_agent_usd.items()},
                },
            ))
        except Exception:
            logger.exception("Failed to publish cost.budget_warning")

    async def _call_sidecar(self, provider: str, model: str, messages: list[dict],
                            system: str | None = None, temperature: float = 0.5,
                            access_token: str | None = None) -> str:
        """Route LLM call through Node.js sidecar for OAuth authentication.

        ``access_token`` MUST be a token valid for ``provider``. The caller
        (``call``) is responsible for looking up the right provider's token.
        """
        import httpx

        token = access_token or ""
        if not token:
            raise RuntimeError(self._friendly_auth_error(provider))

        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)

        endpoint = f"{SIDECAR_URL}/chat/{provider}"

        async def post(tok: str):
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    endpoint,
                    json={
                        "model": model,
                        "messages": msgs,
                        "system_prompt": system or "",
                        "access_token": tok,
                    },
                )
                return resp.json()

        try:
            data = await post(token)

            if data.get("error"):
                err = str(data["error"])
                is_auth_err = "401" in err or "unauthorized" in err.lower() or "invalid bearer" in err.lower()
                if is_auth_err:
                    new_token = await self._refresh_oauth(provider)
                    if new_token:
                        # Also update the legacy field so any old callers see it.
                        self._oauth_token = new_token
                        data = await post(new_token)
                if data.get("error"):
                    # Upgrade to a user-actionable message when it's auth-related.
                    final_err = str(data["error"])
                    if "401" in final_err or "invalid bearer" in final_err.lower():
                        raise RuntimeError(
                            self._friendly_auth_error(provider)
                            + f" (sidecar response: {final_err[:160]})"
                        )
                    raise RuntimeError(f"Sidecar error: {final_err}")

            return data.get("response", "")
        except httpx.ConnectError:
            raise RuntimeError(
                "Node.js sidecar not running. Start it with: node quantclaw/sidecar/server.js"
            )

    async def _refresh_oauth(self, provider: str) -> str | None:
        """Try to refresh an expired OAuth token."""
        try:
            from quantclaw.dashboard.oauth import refresh_token
            return await refresh_token(provider)
        except Exception:
            logger.exception("OAuth token refresh failed for %s", provider)
            return None

    async def _call_anthropic(self, model: str, messages: list[dict],
                              system: str = None, temperature: float = 0.5) -> tuple[str, int, int]:
        import anthropic
        client_kwargs = {}
        if self._api_key:
            client_kwargs["api_key"] = self._api_key
        client = anthropic.AsyncAnthropic(**client_kwargs)
        call_kwargs = {"model": model, "max_tokens": 4096, "messages": messages,
                       "temperature": temperature}
        if system:
            call_kwargs["system"] = system
        response = await client.messages.create(**call_kwargs)
        usage = getattr(response, "usage", None)
        in_tok = getattr(usage, "input_tokens", 0) if usage else 0
        out_tok = getattr(usage, "output_tokens", 0) if usage else 0
        return response.content[0].text, in_tok, out_tok

    async def _call_openai(self, model: str, messages: list[dict],
                           system: str = None, temperature: float = 0.5) -> tuple[str, int, int]:
        import openai
        client_kwargs = {}
        if self._api_key:
            client_kwargs["api_key"] = self._api_key
        client = openai.AsyncOpenAI(**client_kwargs)
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        response = await client.chat.completions.create(
            model=model, messages=msgs, temperature=temperature)
        usage = getattr(response, "usage", None)
        in_tok = getattr(usage, "prompt_tokens", 0) if usage else 0
        out_tok = getattr(usage, "completion_tokens", 0) if usage else 0
        return response.choices[0].message.content, in_tok, out_tok

    async def _call_ollama(self, model: str, messages: list[dict],
                           system: str = None, temperature: float = 0.5) -> tuple[str, int, int]:
        import httpx
        ollama_url = self.get_ollama_url()
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(messages)
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{ollama_url}/api/chat",
                json={"model": model, "messages": msgs, "stream": False,
                      "options": {"temperature": temperature}},
            )
            data = resp.json()
            text = data.get("message", {}).get("content", "")
            in_tok = int(data.get("prompt_eval_count", 0))
            out_tok = int(data.get("eval_count", 0))
            return text, in_tok, out_tok
