"use client";
import { useEffect, useState } from "react";
import { useLang } from "../../lang-context";
import { useProviderModels } from "../../useProviderModels";

const API = "http://localhost:24120";

type Lang = "en" | "zh" | "ja";

interface ProviderConfig {
  id: string;
  name: string;
  pairable?: boolean;
  pairUrl?: string;
  needsKey?: boolean;
  local?: boolean;
  models?: string[];
}

const PROVIDERS: ProviderConfig[] = [
  { id: "ollama", name: "Ollama", local: true },
  { id: "openai", name: "OpenAI", pairable: true, pairUrl: "https://platform.openai.com/account/api-keys", needsKey: true,
    models: ["gpt-5.4", "gpt-5.4-mini", "gpt-5.3-codex"] },
  { id: "anthropic", name: "Anthropic", pairable: true, pairUrl: "https://console.anthropic.com/settings/keys", needsKey: true,
    models: ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001", "claude-sonnet-4-5-20250929", "claude-opus-4-5-20251101"] },
  { id: "google", name: "Google Gemini", needsKey: true,
    models: ["gemini-3.1-pro-preview", "gemini-3-flash-preview", "gemini-3.1-flash-lite-preview", "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-flash-image"] },
  { id: "deepseek", name: "DeepSeek", needsKey: true,
    models: ["deepseek-chat", "deepseek-reasoner"] },
  { id: "xai", name: "xAI", needsKey: true,
    models: ["grok-4.20-0309-reasoning", "grok-4.20-0309-non-reasoning", "grok-4-1-fast-reasoning", "grok-4-1-fast-non-reasoning"] },
  { id: "mistral", name: "Mistral", needsKey: true,
    models: ["mistral-large-latest", "mistral-medium-latest", "mistral-small-latest", "codestral-2501", "devstral-2-25-12"] },
  { id: "groq", name: "Groq", needsKey: true,
    models: ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3-32b", "meta-llama/llama-4-scout-17b-16e-instruct"] },
  { id: "openrouter", name: "OpenRouter", needsKey: true,
    models: ["openai/gpt-5.4", "anthropic/claude-opus-4-6", "anthropic/claude-sonnet-4-6", "google/gemini-3.1-pro-preview", "deepseek/deepseek-chat", "meta-llama/llama-3.3-70b"] },
  { id: "together", name: "Together AI", needsKey: true,
    models: ["meta-llama/Llama-3.3-70B-Instruct-Turbo", "deepseek-ai/DeepSeek-V3", "Qwen/Qwen2.5-72B-Instruct-Turbo"] },
];

const translations: Record<Lang, Record<string, string>> = {
  en: {
    title: "Settings",
    modelProvider: "Model Provider",
    activeProvider: "Active Provider",
    apiKey: "API Key",
    apiKeySaved: "✓ Key saved",
    apiKeyPlaceholder: "Enter API key...",
    save: "Save",
    remove: "Remove",
    pairWithBrowser: "Sign in with browser",
    orManualKey: "or enter API key manually",
    ollamaModels: "Available Models",
    ollamaOffline: "Ollama is not running — start it or select another provider",
    ollamaNoModels: "No models installed — run: ollama pull qwen3:8b",
    selectedModel: "Active model",
    customModel: "or type any model name (gpt-5.5, etc.)",
    use: "Use",
    language: "Language",
    brokerConnection: "Broker Connection",
    brokerValue: "Paper Trading",
    dataSources: "Data Sources",
    dataValue: "Auto-configured from onboarding",
    notifications: "Notifications",
    notifValue: "Not configured",
    configured: "Configured",
    notConfigured: "Not configured",
    notificationsSaved: "Saved locally. Matching events route through configured channels while QuantClaw is running.",
    local: "Local",
    connected: "Connected",
  },
  zh: {
    title: "设置",
    modelProvider: "模型提供商",
    activeProvider: "当前提供商",
    apiKey: "API 密钥",
    apiKeySaved: "✓ 密钥已保存",
    apiKeyPlaceholder: "输入 API 密钥...",
    save: "保存",
    remove: "移除",
    pairWithBrowser: "通过浏览器登录授权",
    orManualKey: "或手动输入 API 密钥",
    ollamaModels: "可用模型",
    ollamaOffline: "Ollama 未运行 — 请启动或选择其他提供商",
    ollamaNoModels: "未安装模型 — 请运行：ollama pull qwen3:8b",
    selectedModel: "当前模型",
    customModel: "或输入任意模型名 (如 gpt-5.5)",
    use: "使用",
    language: "语言",
    brokerConnection: "券商连接",
    brokerValue: "模拟交易",
    dataSources: "数据源",
    dataValue: "已根据引导配置自动设置",
    notifications: "通知",
    notifValue: "未配置",
    local: "本地",
    connected: "已连接",
  },
  ja: {
    title: "設定",
    modelProvider: "モデルプロバイダー",
    activeProvider: "アクティブプロバイダー",
    apiKey: "API キー",
    apiKeySaved: "✓ キー保存済み",
    apiKeyPlaceholder: "API キーを入力...",
    save: "保存",
    remove: "削除",
    pairWithBrowser: "ブラウザでサインイン",
    orManualKey: "または API キーを手動入力",
    ollamaModels: "利用可能なモデル",
    ollamaOffline: "Ollama が実行されていません — 起動するか他のプロバイダーを選択",
    ollamaNoModels: "モデル未インストール — 実行: ollama pull qwen3:8b",
    selectedModel: "使用中のモデル",
    customModel: "または任意のモデル名を入力 (例: gpt-5.5)",
    use: "使用",
    language: "言語",
    brokerConnection: "ブローカー接続",
    brokerValue: "ペーパートレード",
    dataSources: "データソース",
    dataValue: "オンボーディングから自動設定",
    notifications: "通知",
    notifValue: "未設定",
    local: "ローカル",
    connected: "接続済み",
  },
};

const langNames: Record<string, string> = { en: "English", zh: "简体中文", ja: "日本語" };

interface DataProvider {
  id: string;
  name: string;
  free?: boolean;
  keyUrl?: string;
}

const FREE_SOURCES: DataProvider[] = [
  { id: "yfinance", name: "Yahoo Finance", free: true },
  { id: "fred", name: "FRED", free: true },
  { id: "sec_edgar", name: "SEC EDGAR", free: true },
  { id: "worldbank", name: "World Bank", free: true },
  { id: "imf", name: "IMF", free: true },
  { id: "bls", name: "BLS", free: true },
  { id: "treasury", name: "Treasury", free: true },
  { id: "ecb", name: "ECB", free: true },
  { id: "bis", name: "BIS", free: true },
  { id: "cftc", name: "CFTC COT", free: true },
  { id: "openinsider", name: "OpenInsider", free: true },
  { id: "stooq", name: "Stooq", free: true },
];

const API_KEY_SOURCES: DataProvider[] = [
  { id: "alphavantage", name: "Alpha Vantage", keyUrl: "https://www.alphavantage.co/support/#api-key" },
  { id: "nasdaq", name: "Nasdaq Data Link", keyUrl: "https://data.nasdaq.com/sign-up" },
  { id: "twelvedata", name: "Twelve Data", keyUrl: "https://twelvedata.com/pricing" },
  { id: "eia", name: "EIA", keyUrl: "https://www.eia.gov/opendata/register.php" },
  { id: "finnhub", name: "Finnhub", keyUrl: "https://finnhub.io/register" },
  { id: "tiingo", name: "Tiingo", keyUrl: "https://www.tiingo.com/account/api/token" },
  { id: "fmp", name: "FMP", keyUrl: "https://site.financialmodelingprep.com/developer/docs" },
  { id: "simfin", name: "SimFin", keyUrl: "https://app.simfin.com/login" },
  { id: "polygon", name: "Polygon.io", keyUrl: "https://polygon.io/dashboard/signup" },
];

const dataI18n: Record<string, Record<string, string>> = {
  en: {
    title: "Data Sources",
    free: "Auto-ingested (free)",
    apiKey: "API-key providers",
    enterKey: "Enter API key...",
    save: "Save",
    remove: "Remove",
    saved: "Configured",
    getKey: "Get key",
    hint: "Click a provider to configure its API key. Free sources work automatically.",
  },
  zh: {
    title: "数据源",
    free: "自动采集（免费）",
    apiKey: "需要 API 密钥",
    enterKey: "输入 API 密钥...",
    save: "保存",
    remove: "移除",
    saved: "已配置",
    getKey: "获取密钥",
    hint: "点击提供商配置其 API 密钥。免费数据源自动工作。",
  },
  ja: {
    title: "データソース",
    free: "自動取得（無料）",
    apiKey: "APIキーが必要",
    enterKey: "APIキーを入力...",
    save: "保存",
    remove: "削除",
    saved: "設定済み",
    getKey: "キーを取得",
    hint: "プロバイダーをクリックしてAPIキーを設定。無料ソースは自動的に動作します。",
  },
};

function readStoredDataKeys(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const keys: Record<string, string> = {};
  for (const p of API_KEY_SOURCES) {
    const k = localStorage.getItem(`quantclaw_data_${p.id}`);
    if (k) keys[p.id] = k;
  }
  return keys;
}

function readStoredProviderKeys(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const keys: Record<string, string> = {};
  for (const p of PROVIDERS) {
    if (p.needsKey) {
      const k = localStorage.getItem(`quantclaw_key_${p.id}`);
      if (k) keys[p.id] = k;
    }
  }
  return keys;
}

function DataSourcesSection({ lang }: { lang: string }) {
  const dt = dataI18n[lang] || dataI18n.en;
  const [dataKeys, setDataKeys] = useState<Record<string, string>>(() => readStoredDataKeys());
  const [expanded, setExpanded] = useState<string | null>(null);
  const [keyInput, setKeyInput] = useState("");

  const saveDataKey = (providerId: string) => {
    if (!keyInput.trim()) return;
    const updated = { ...dataKeys, [providerId]: keyInput.trim() };
    setDataKeys(updated);
    localStorage.setItem(`quantclaw_data_${providerId}`, keyInput.trim());
    setKeyInput("");
    setExpanded(null);
  };

  const removeDataKey = (providerId: string) => {
    const updated = { ...dataKeys };
    delete updated[providerId];
    setDataKeys(updated);
    localStorage.removeItem(`quantclaw_data_${providerId}`);
  };

  return (
    <div className="card-cyber p-5">
      <h3 className="font-medium mb-4">{dt.title}</h3>

      {/* Free sources */}
      <p className="text-[10px] font-mono text-muted uppercase tracking-wider mb-2">{dt.free}</p>
      <div className="flex flex-wrap gap-1.5 mb-5">
        {FREE_SOURCES.map((s) => (
          <span key={s.id} className="text-[10px] font-mono px-2 py-0.5 rounded bg-circuit-light/8 text-circuit-light border border-circuit/20">
            {s.name}
          </span>
        ))}
      </div>

      {/* API-key sources — interactive */}
      <p className="text-[10px] font-mono text-muted uppercase tracking-wider mb-2">{dt.apiKey}</p>
      <div className="space-y-1.5">
        {API_KEY_SOURCES.map((provider) => {
          const hasKey = !!dataKeys[provider.id];
          const isExpanded = expanded === provider.id;

          return (
            <div key={provider.id}>
              <button
                onClick={() => {
                  setExpanded(isExpanded ? null : provider.id);
                  setKeyInput("");
                }}
                className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-all cursor-pointer ${
                  isExpanded
                    ? "bg-keel/50 border border-circuit/20"
                    : "bg-hull/40 border border-trace hover:border-trace-glow"
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className={`w-1.5 h-1.5 rounded-full ${hasKey ? "bg-circuit-light" : "bg-trace-glow"}`} />
                  <span className="text-[#7a8aa0] font-medium">{provider.name}</span>
                </div>
                {hasKey && (
                  <span className="text-[9px] font-mono text-circuit-light bg-circuit/10 px-1.5 py-0.5 rounded">
                    {dt.saved}
                  </span>
                )}
              </button>

              {isExpanded && (
                <div className="mt-1 px-3 py-3 bg-void/50 border border-trace rounded-lg">
                  {hasKey ? (
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-xs text-circuit-light font-mono">{dt.saved}</p>
                        <p className="text-[10px] text-[#2a3a5a] font-mono mt-0.5">
                          ••••••••{dataKeys[provider.id].slice(-4)}
                        </p>
                      </div>
                      <button
                        onClick={() => removeDataKey(provider.id)}
                        className="text-xs text-claw/60 hover:text-claw transition-colors cursor-pointer"
                      >
                        {dt.remove}
                      </button>
                    </div>
                  ) : (
                    <>
                      <div className="flex gap-2">
                        <input
                          type="password"
                          value={keyInput}
                          onChange={(e) => setKeyInput(e.target.value)}
                          onKeyDown={(e) => e.key === "Enter" && saveDataKey(provider.id)}
                          placeholder={dt.enterKey}
                          className="flex-1 bg-hull/60 border border-trace rounded-lg px-3 py-2 text-xs text-[#8a9ab0] placeholder-[#2a3a5a] outline-none focus:border-gold/30 transition-colors font-mono"
                        />
                        <button
                          onClick={() => saveDataKey(provider.id)}
                          disabled={!keyInput.trim()}
                          className="px-3 py-2 rounded-lg bg-gold text-void text-xs font-medium hover:bg-gold-light disabled:opacity-40 disabled:cursor-not-allowed transition-all cursor-pointer"
                        >
                          {dt.save}
                        </button>
                      </div>
                      {provider.keyUrl && (
                        <a
                          href={provider.keyUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-[10px] text-circuit/60 hover:text-circuit-light mt-2 inline-block transition-colors font-mono"
                        >
                          {dt.getKey} ↗
                        </a>
                      )}
                    </>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <p className="text-[10px] text-[#1a2a4a] mt-3 font-mono">{dt.hint}</p>
    </div>
  );
}

interface NotificationStatus {
  channels: Record<string, { configured: boolean; fields: string[] }>;
  routes: { event: string; channels: string[]; urgency: string }[];
}

function NotificationsSection({ t }: { t: Record<string, string> }) {
  const [status, setStatus] = useState<NotificationStatus | null>(null);
  const [telegramToken, setTelegramToken] = useState("");
  const [telegramChatId, setTelegramChatId] = useState("");
  const [discordWebhook, setDiscordWebhook] = useState("");
  const [slackWebhook, setSlackWebhook] = useState("");
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API}/api/settings/notifications`)
      .then((res) => res.json())
      .then((data) => setStatus(data))
      .catch(() => {});
  }, []);

  const saveChannel = async (channel: "telegram" | "discord" | "slack") => {
    setError("");
    const payload: Record<string, Record<string, string>> = {};
    if (channel === "telegram") {
      payload.telegram = {};
      if (telegramToken.trim()) payload.telegram.bot_token = telegramToken.trim();
      if (telegramChatId.trim()) payload.telegram.chat_id = telegramChatId.trim();
    } else if (channel === "discord") {
      payload.discord = {};
      if (discordWebhook.trim()) payload.discord.webhook_url = discordWebhook.trim();
    } else {
      payload.slack = {};
      if (slackWebhook.trim()) payload.slack.webhook_url = slackWebhook.trim();
    }

    if (Object.keys(payload[channel]).length === 0) return;

    const res = await fetch(`${API}/api/settings/notifications`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok || data.error || data.detail) {
      setError(data.detail || data.error || "Failed to save notifications");
      return;
    }

    setTelegramToken("");
    setTelegramChatId("");
    setDiscordWebhook("");
    setSlackWebhook("");
    setSaved(channel);
    setStatus(data);
    setTimeout(() => setSaved(null), 2000);
  };

  const clearChannel = async (channel: "telegram" | "discord" | "slack") => {
    setError("");
    const payload = channel === "telegram"
      ? { telegram: { bot_token: "", chat_id: "" } }
      : channel === "discord"
        ? { discord: { webhook_url: "" } }
        : { slack: { webhook_url: "" } };
    const res = await fetch(`${API}/api/settings/notifications`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok || data.error || data.detail) {
      setError(data.detail || data.error || "Failed to update notifications");
      return;
    }
    setStatus(data);
  };

  const channelState = (channel: string) =>
    status?.channels?.[channel]?.configured
      ? (t.configured || "Configured")
      : (t.notConfigured || "Not configured");

  const inputClass = "w-full bg-keel/50 border border-trace rounded-lg px-3 py-2 text-xs font-mono text-[#8a9ab0] outline-none focus:border-gold/30 transition-colors";
  const buttonClass = "px-3 py-2 rounded-lg bg-gold/10 border border-gold/30 text-gold text-xs font-medium hover:bg-gold/20 transition-all cursor-pointer";
  const removeClass = "px-3 py-2 rounded-lg bg-keel/50 border border-trace text-muted text-xs hover:border-trace-glow transition-all cursor-pointer";

  return (
    <div className="card-cyber p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-medium">{t.notifications}</h3>
        {saved && <span className="text-[10px] text-circuit-light font-mono">{saved} saved</span>}
      </div>
      {error && <p className="text-xs text-claw-light mb-3">{error}</p>}

      <div className="grid gap-3">
        <div className="rounded-lg border border-trace bg-keel/30 p-3">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-medium">Telegram</p>
            <span className="text-[10px] font-mono text-muted">{channelState("telegram")}</span>
          </div>
          <div className="grid gap-2 md:grid-cols-2">
            <input className={inputClass} type="password" value={telegramToken} onChange={(e) => setTelegramToken(e.target.value)} placeholder="Bot token" />
            <input className={inputClass} value={telegramChatId} onChange={(e) => setTelegramChatId(e.target.value)} placeholder="Chat ID" />
          </div>
          <div className="flex gap-2 mt-2">
            <button className={buttonClass} onClick={() => saveChannel("telegram")}>{t.save}</button>
            <button className={removeClass} onClick={() => clearChannel("telegram")}>{t.remove}</button>
          </div>
        </div>

        <div className="rounded-lg border border-trace bg-keel/30 p-3">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-medium">Discord</p>
            <span className="text-[10px] font-mono text-muted">{channelState("discord")}</span>
          </div>
          <input className={inputClass} type="password" value={discordWebhook} onChange={(e) => setDiscordWebhook(e.target.value)} placeholder="Webhook URL" />
          <div className="flex gap-2 mt-2">
            <button className={buttonClass} onClick={() => saveChannel("discord")}>{t.save}</button>
            <button className={removeClass} onClick={() => clearChannel("discord")}>{t.remove}</button>
          </div>
        </div>

        <div className="rounded-lg border border-trace bg-keel/30 p-3">
          <div className="flex items-center justify-between mb-2">
            <p className="text-sm font-medium">Slack</p>
            <span className="text-[10px] font-mono text-muted">{channelState("slack")}</span>
          </div>
          <input className={inputClass} type="password" value={slackWebhook} onChange={(e) => setSlackWebhook(e.target.value)} placeholder="Webhook URL" />
          <div className="flex gap-2 mt-2">
            <button className={buttonClass} onClick={() => saveChannel("slack")}>{t.save}</button>
            <button className={removeClass} onClick={() => clearChannel("slack")}>{t.remove}</button>
          </div>
        </div>
      </div>

      <p className="text-[10px] text-[#2a3a5a] mt-3 font-mono">
        {t.notificationsSaved || "Saved locally. Matching events route through configured channels while QuantClaw is running."}
      </p>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {(status?.routes || []).map((route) => (
          <span key={`${route.event}-${route.channels.join(",")}`} className="text-[10px] font-mono px-2 py-0.5 rounded bg-hull/50 text-muted border border-trace/50">
            {route.event} {"->"} {route.channels.join(", ")}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const { lang, setLang } = useLang();
  const t = translations[lang] || translations.en;

  const [activeProvider, setActiveProvider] = useState(() => {
    if (typeof window === "undefined") return "ollama";
    return localStorage.getItem("quantclaw_provider") || "ollama";
  });
  const [apiKeys, setApiKeys] = useState<Record<string, string>>(() => readStoredProviderKeys());
  const [keyInput, setKeyInput] = useState("");
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState(() => {
    if (typeof window === "undefined") return "";
    return localStorage.getItem("quantclaw_model") || "";
  });
  const [customModelInput, setCustomModelInput] = useState("");
  const [ollamaStatus, setOllamaStatus] = useState<"checking" | "online" | "offline">("checking");
  const [oauthStatus, setOauthStatus] = useState<Record<string, { authenticated: boolean; flow_status?: string }>>({});
  const [oauthLoading, setOauthLoading] = useState<string | null>(null);

  useEffect(() => {
    // Check OAuth status for pairable providers
    for (const p of PROVIDERS) {
      if (p.pairable) {
        fetch(`${API}/api/oauth/status/${p.id}`)
          .then((r) => r.json())
          .then((data) => setOauthStatus((prev) => ({ ...prev, [p.id]: data })))
          .catch(() => {});
      }
    }

    // Check Ollama
    const savedModel = localStorage.getItem("quantclaw_model");
    fetch("http://localhost:11434/api/tags", { signal: AbortSignal.timeout(3000) })
      .then((r) => r.json())
      .then((data) => {
        const names = (data.models || []).map((m: { name: string }) => m.name);
        setOllamaModels(names);
        setOllamaStatus("online");
        if (!savedModel && names.length > 0) {
          const best = names.includes("qwen3:30b") ? "qwen3:30b" : names.includes("qwen3:8b") ? "qwen3:8b" : names[0];
          setSelectedModel(best);
          localStorage.setItem("quantclaw_model", best);
        }
      })
      .catch(() => setOllamaStatus("offline"));
  }, []);

  const selectProvider = (id: string) => {
    setActiveProvider(id);
    localStorage.setItem("quantclaw_provider", id);
    setKeyInput("");
  };

  const saveKey = (providerId: string) => {
    if (!keyInput.trim()) return;
    const updated = { ...apiKeys, [providerId]: keyInput.trim() };
    setApiKeys(updated);
    localStorage.setItem(`quantclaw_key_${providerId}`, keyInput.trim());
    setKeyInput("");
  };

  const removeKey = (providerId: string) => {
    const updated = { ...apiKeys };
    delete updated[providerId];
    setApiKeys(updated);
    localStorage.removeItem(`quantclaw_key_${providerId}`);
  };

  const selectModel = (model: string) => {
    setSelectedModel(model);
    localStorage.setItem("quantclaw_model", model);
    // Persist custom (non-catalog) models per provider so they show up in
    // the Agents page dropdown and any other place that lists models.
    if (activeProvider && !liveModels.includes(model)) {
      const key = `quantclaw_custom_models_${activeProvider}`;
      let existing: string[] = [];
      try {
        existing = JSON.parse(localStorage.getItem(key) || "[]");
      } catch {}
      if (!existing.includes(model)) {
        existing.push(model);
        localStorage.setItem(key, JSON.stringify(existing));
      }
    }
  };

  const startOAuth = async (providerId: string) => {
    setOauthLoading(providerId);
    try {
      // Start the OAuth flow (backend opens browser)
      await fetch(`${API}/api/oauth/start/${providerId}`, { method: "POST" });

      // Poll for completion
      const poll = setInterval(async () => {
        try {
          const statusRes = await fetch(`${API}/api/oauth/status/${providerId}`);
          const status = await statusRes.json();

          if (status.flow_status === "code_received") {
            // Exchange the code for a token
            const exchangeRes = await fetch(`${API}/api/oauth/exchange/${providerId}`, { method: "POST" });
            const result = await exchangeRes.json();

            if (result.status === "authenticated") {
              setOauthStatus((prev) => ({ ...prev, [providerId]: { authenticated: true } }));
              setOauthLoading(null);
              clearInterval(poll);
            }
          } else if (status.authenticated) {
            setOauthStatus((prev) => ({ ...prev, [providerId]: { authenticated: true } }));
            setOauthLoading(null);
            clearInterval(poll);
          } else if (status.flow_status === "error") {
            setOauthLoading(null);
            clearInterval(poll);
          }
        } catch {
          // Keep polling
        }
      }, 2000);

      // Stop polling after 5 minutes
      setTimeout(() => {
        clearInterval(poll);
        setOauthLoading(null);
      }, 300000);
    } catch {
      setOauthLoading(null);
    }
  };

  const disconnectOAuth = async (providerId: string) => {
    await fetch(`${API}/api/oauth/disconnect/${providerId}`, { method: "POST" });
    setOauthStatus((prev) => ({ ...prev, [providerId]: { authenticated: false } }));
  };

  const currentProviderConfig = PROVIDERS.find((p) => p.id === activeProvider);
  const { models: liveModels, loading: modelsLoading, source: modelsSource, refresh: refreshModels } =
    useProviderModels(activeProvider, currentProviderConfig?.models ?? []);

  // Migration: if the saved active model isn't in the catalog or the custom
  // list yet (e.g. typed in an older build), backfill it so it shows up in
  // every dropdown across the app.
  useEffect(() => {
    if (!activeProvider || !selectedModel || liveModels.length === 0) return;
    if (liveModels.includes(selectedModel)) return;
    const key = `quantclaw_custom_models_${activeProvider}`;
    let existing: string[] = [];
    try { existing = JSON.parse(localStorage.getItem(key) || "[]"); } catch {}
    if (!existing.includes(selectedModel)) {
      existing.push(selectedModel);
      localStorage.setItem(key, JSON.stringify(existing));
    }
  }, [activeProvider, selectedModel, liveModels]);

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6 text-gold" style={{ fontFamily: "var(--font-display)" }}>{t.title}</h1>
      <div className="space-y-4">

        {/* Model Provider */}
        <div className="card-cyber p-5">
          <h3 className="font-medium mb-4">{t.modelProvider}</h3>

          {/* Provider tabs */}
          <div className="flex flex-wrap gap-2 mb-5">
            {PROVIDERS.map((p) => {
              const isActive = activeProvider === p.id;
              const hasKey = !!apiKeys[p.id];
              return (
                <button
                  key={p.id}
                  onClick={() => selectProvider(p.id)}
                  className={`relative px-3 py-2 rounded-lg text-sm transition-all cursor-pointer ${
                    isActive
                      ? "bg-gold/10 border border-gold/40 text-gold"
                      : "bg-keel/50 border border-trace text-[#6a7a9a] hover:border-trace-glow"
                  }`}
                >
                  {p.name}
                  {/* Status dot */}
                  {(hasKey || (p.local && ollamaStatus === "online") || oauthStatus[p.id]?.authenticated) && (
                    <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-circuit-light" />
                  )}
                </button>
              );
            })}
          </div>

          {/* Provider configuration panel */}
          {currentProviderConfig && (
            <div className="border border-trace rounded-xl p-4 bg-void/50">
              <div className="flex items-center gap-2 mb-3">
                <span className="text-sm font-medium text-[#a0b0cc]">{currentProviderConfig.name}</span>
                {currentProviderConfig.local && (
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-circuit/15 text-circuit-light">{t.local}</span>
                )}
                {apiKeys[activeProvider] && (
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-circuit-light/15 text-circuit-light">{t.connected}</span>
                )}
              </div>

              {/* Ollama: model picker */}
              {currentProviderConfig.local && (
                <div className="space-y-3">
                  {ollamaStatus === "checking" && (
                    <p className="text-sm text-muted flex items-center gap-2">
                      <span className="w-3 h-3 border-2 border-muted border-t-transparent rounded-full animate-spin" />
                      ...
                    </p>
                  )}
                  {ollamaStatus === "offline" && (
                    <div className="space-y-2">
                      <p className="text-sm text-gold">{t.ollamaOffline}</p>
                      <a href="https://ollama.com/download" target="_blank" rel="noopener noreferrer"
                        className="text-xs text-gold/70 hover:text-gold-light transition-colors">
                        ollama.com/download ↗
                      </a>
                    </div>
                  )}
                  {ollamaStatus === "online" && ollamaModels.length === 0 && (
                    <p className="text-sm text-muted font-mono">{t.ollamaNoModels}</p>
                  )}
                  {ollamaStatus === "online" && ollamaModels.length > 0 && (
                    <div>
                      <p className="text-xs text-muted mb-2">{t.ollamaModels}</p>
                      <div className="flex flex-wrap gap-2">
                        {ollamaModels.map((m) => (
                          <button
                            key={m}
                            onClick={() => selectModel(m)}
                            className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-all cursor-pointer ${
                              selectedModel === m
                                ? "bg-gold/10 border border-gold/40 text-gold"
                                : "bg-keel/40 border border-trace text-muted hover:border-trace-glow"
                            }`}
                          >
                            {m}
                          </button>
                        ))}
                      </div>
                      {selectedModel && (
                        <p className="text-[10px] text-[#2a3a5a] mt-2 font-mono">
                          {t.selectedModel}: {selectedModel}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* API key providers */}
              {currentProviderConfig.needsKey && (
                <div className="space-y-3">
                  {/* OAuth pairing */}
                  {currentProviderConfig.pairable && (
                    <>
                      {oauthStatus[activeProvider]?.authenticated ? (
                        <div className="flex items-center justify-between bg-circuit-light/5 border border-circuit/30 rounded-xl px-4 py-3">
                          <p className="text-xs text-circuit-light font-mono flex items-center gap-2">
                            <span className="w-1.5 h-1.5 rounded-full bg-circuit-light" />
                            ✓ {currentProviderConfig.name} {t.connected}
                          </p>
                          <button
                            onClick={() => disconnectOAuth(activeProvider)}
                            className="text-xs text-claw/60 hover:text-claw transition-colors cursor-pointer"
                          >
                            {t.remove}
                          </button>
                        </div>
                      ) : oauthLoading === activeProvider ? (
                        <div className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl border border-gold/30 bg-gold/5 text-gold text-sm">
                          <span className="w-4 h-4 border-2 border-gold border-t-transparent rounded-full animate-spin" />
                          {({ en: "Waiting for authorization...", zh: "等待授权中...", ja: "認証を待機中..." } as Record<string, string>)[lang] || "Waiting for authorization..."}
                        </div>
                      ) : (
                        <button
                          onClick={() => startOAuth(activeProvider)}
                          className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl border border-gold/30 bg-gold/5 text-gold text-sm font-medium hover:bg-gold/10 transition-all cursor-pointer"
                        >
                          <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M6 2L10 2C11.1 2 12 2.9 12 4V5M4 7H12M4 10H9M3 5H13C13.5523 5 14 5.44772 14 6V13C14 13.5523 13.5523 14 13 14H3C2.44772 14 2 13.5523 2 13V6C2 5.44772 2.44772 5 3 5Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
                          {t.pairWithBrowser}
                        </button>
                      )}
                      <div className="flex items-center gap-3">
                        <div className="flex-1 h-px bg-trace" />
                        <span className="text-[10px] text-[#2a3a5a] font-mono">{t.orManualKey}</span>
                        <div className="flex-1 h-px bg-trace" />
                      </div>
                    </>
                  )}

                  {/* Key already saved */}
                  {apiKeys[activeProvider] ? (
                    <div className="flex items-center justify-between bg-circuit-light/5 border border-circuit/30 rounded-xl px-4 py-3">
                      <div>
                        <p className="text-xs text-circuit-light font-mono">{t.apiKeySaved}</p>
                        <p className="text-[10px] text-[#2a3a5a] font-mono mt-0.5">
                          ••••••••{apiKeys[activeProvider].slice(-4)}
                        </p>
                      </div>
                      <button
                        onClick={() => removeKey(activeProvider)}
                        className="text-xs text-claw/60 hover:text-claw transition-colors cursor-pointer"
                      >
                        {t.remove}
                      </button>
                    </div>
                  ) : (
                    <div className="flex gap-2">
                      <input
                        type="password"
                        value={keyInput}
                        onChange={(e) => setKeyInput(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && saveKey(activeProvider)}
                        placeholder={t.apiKeyPlaceholder}
                        className="flex-1 bg-hull/60 border border-trace rounded-xl px-4 py-2.5 text-sm text-[#a0b0cc] placeholder-[#2a3a5a] outline-none focus:border-gold/30 transition-colors font-mono"
                      />
                      <button
                        onClick={() => saveKey(activeProvider)}
                        disabled={!keyInput.trim()}
                        className="px-4 py-2.5 rounded-xl bg-gold text-void text-sm font-medium hover:bg-gold-light disabled:opacity-40 disabled:cursor-not-allowed transition-all cursor-pointer"
                      >
                        {t.save}
                      </button>
                    </div>
                  )}
                </div>
              )}

              {/* Model selector — fetched live from provider's /v1/models */}
              {liveModels.length > 0 && (
                <div className="mt-4 pt-4 border-t border-trace/40">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-xs text-muted">{t.selectedModel}</p>
                    <div className="flex items-center gap-2 text-[10px] font-mono text-[#2a3a5a]">
                      {modelsLoading && <span>loading…</span>}
                      {!modelsLoading && modelsSource && (
                        <span className={modelsSource === "live" ? "text-emerald-500/70" : modelsSource === "cache" ? "text-cyan-500/60" : "text-amber-500/60"}>
                          {modelsSource}
                        </span>
                      )}
                      <button
                        onClick={refreshModels}
                        className="text-[#3a4a6a] hover:text-muted transition-colors"
                        title="Refetch from provider"
                      >
                        ↻
                      </button>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {liveModels.map((m) => (
                      <button
                        key={m}
                        onClick={() => selectModel(m)}
                        className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-all cursor-pointer ${
                          selectedModel === m
                            ? "bg-gold/10 border border-gold/40 text-gold"
                            : "bg-keel/40 border border-trace text-muted hover:border-trace-glow"
                        }`}
                      >
                        {m}
                      </button>
                    ))}
                    {selectedModel && !liveModels.includes(selectedModel) && (
                      <button
                        onClick={() => selectModel(selectedModel)}
                        className="px-3 py-1.5 rounded-lg text-xs font-mono bg-gold/10 border border-gold/40 text-gold cursor-default"
                        title="Custom model"
                      >
                        {selectedModel}
                      </button>
                    )}
                  </div>

                  {/* Custom model input — for any release the catalog endpoint
                      can't see (Codex subscription models, preview tiers, etc.) */}
                  <div className="mt-3 flex items-center gap-2">
                    <input
                      type="text"
                      value={customModelInput}
                      onChange={(e) => setCustomModelInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && customModelInput.trim()) {
                          selectModel(customModelInput.trim());
                          setCustomModelInput("");
                        }
                      }}
                      placeholder={t.customModel}
                      className="flex-1 bg-keel/40 border border-trace rounded-lg px-3 py-1.5 text-xs font-mono text-muted placeholder:text-[#2a3a5a] focus:outline-none focus:border-trace-glow"
                    />
                    <button
                      onClick={() => {
                        if (customModelInput.trim()) {
                          selectModel(customModelInput.trim());
                          setCustomModelInput("");
                        }
                      }}
                      disabled={!customModelInput.trim()}
                      className="px-3 py-1.5 rounded-lg text-xs font-mono bg-gold/10 border border-gold/40 text-gold hover:bg-gold/20 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
                    >
                      {t.use}
                    </button>
                  </div>

                  {selectedModel && (
                    <p className="text-[10px] text-[#2a3a5a] mt-2 font-mono">
                      {t.selectedModel}: {selectedModel}
                    </p>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Language */}
        <div className="card-cyber p-4">
          <h3 className="font-medium mb-3">{t.language}</h3>
          <div className="flex gap-2">
            {(["en", "zh", "ja"] as const).map((code) => (
              <button
                key={code}
                onClick={() => setLang(code)}
                className={`px-3 py-2 rounded-lg text-sm transition-all cursor-pointer ${
                  lang === code
                    ? "bg-gold/10 border border-gold/40 text-gold"
                    : "bg-keel/50 border border-trace text-[#6a7a9a] hover:border-trace-glow"
                }`}
              >
                {langNames[code]}
              </button>
            ))}
          </div>
        </div>

        {/* Broker */}
        <div className="card-cyber p-4">
          <h3 className="font-medium mb-2">{t.brokerConnection}</h3>
          <p className="text-sm text-muted">{t.brokerValue}</p>
        </div>

        {/* Data sources */}
        <DataSourcesSection lang={lang} />

        {/* Notifications */}
        <NotificationsSection t={t} />
      </div>
    </div>
  );
}
