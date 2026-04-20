"use client";
import { useEffect, useState } from "react";
import { useLang } from "../../lang-context";

const API = "http://localhost:24120";

type Lang = "en" | "zh" | "ja";

interface Agent {
  name: string;
  model: string;
  daemon: boolean;
  enabled: boolean;
}

// Agent tiers: which agents need powerful models vs lightweight ones
const AGENT_TIERS: Record<string, "heavy" | "medium" | "light"> = {
  validator: "heavy",
  researcher: "heavy",
  trainer: "heavy",
  miner: "heavy",
  risk_monitor: "heavy",
  executor: "medium",
  compliance: "medium",
  sentinel: "medium",
  debugger: "medium",
  ingestor: "medium",
  scheduler: "light",
  reporter: "light",
  cost_tracker: "light",
};

// Model ranking by capability (best first)
const MODEL_RANKING = [
  // Heavy
  "gpt-5.4", "claude-opus-4-6", "gemini-3.1-pro-preview", "gpt-5.4-mini", "claude-sonnet-4-6",
  "deepseek-reasoner", "grok-4.20-0309-reasoning",
  // Medium
  "gpt-5.3-codex", "claude-haiku-4-5-20251001", "gemini-2.5-flash", "deepseek-chat",
  "mistral-large-latest", "grok-4-1-fast-non-reasoning",
  // Light
  "gemini-2.5-flash-lite", "mistral-small-latest", "llama-3.3-70b-versatile",
  // Local
  "qwen3:30b", "qwen3:8b", "qwen3:4b",
];

function getAvailableModels(): { provider: string; model: string }[] {
  const models: { provider: string; model: string }[] = [];

  const ollamaModels = JSON.parse(localStorage.getItem("quantclaw_ollama_models") || "[]");
  for (const m of ollamaModels) {
    models.push({ provider: "ollama", model: m });
  }

  const providers = ["openai", "anthropic"];
  const providerModels: Record<string, string[]> = {
    openai: ["gpt-5.4", "gpt-5.4-mini", "gpt-5.3-codex"],
    anthropic: ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
  };
  for (const p of providers) {
    const hasOAuth = localStorage.getItem(`quantclaw_oauth_${p}`) === "true";
    const hasKey = !!localStorage.getItem(`quantclaw_key_${p}`);
    if (hasOAuth || hasKey) {
      for (const m of providerModels[p] || []) {
        models.push({ provider: p, model: m });
      }
    }
  }

  const apiKeyProviders: Record<string, string[]> = {
    google: ["gemini-3.1-pro-preview", "gemini-2.5-flash", "gemini-2.5-flash-lite"],
    deepseek: ["deepseek-chat", "deepseek-reasoner"],
    xai: ["grok-4.20-0309-reasoning", "grok-4-1-fast-non-reasoning"],
    mistral: ["mistral-large-latest", "mistral-small-latest"],
    groq: ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"],
  };
  for (const [p, pModels] of Object.entries(apiKeyProviders)) {
    if (localStorage.getItem(`quantclaw_key_${p}`)) {
      for (const m of pModels) {
        models.push({ provider: p, model: m });
      }
    }
  }

  return models;
}

function autoAssignModels(agents: Agent[], available: { provider: string; model: string }[]): Record<string, string> {
  const assignments: Record<string, string> = {};
  if (available.length === 0) return assignments;

  const modelSet = new Set(available.map((a) => a.model));
  const ranked = MODEL_RANKING.filter((m) => modelSet.has(m));

  for (const agent of agents) {
    const tier = AGENT_TIERS[agent.name] || "medium";
    let assigned = ranked[0] || available[0]?.model || "";

    if (tier === "heavy") {
      assigned = ranked[0] || available[0]?.model || "";
    } else if (tier === "medium") {
      assigned = ranked[Math.min(Math.floor(ranked.length / 3), ranked.length - 1)] || available[0]?.model || "";
    } else {
      assigned = ranked[Math.min(Math.floor(ranked.length * 2 / 3), ranked.length - 1)] || available[0]?.model || "";
    }
    assignments[agent.name] = assigned;
  }
  return assignments;
}

const translations: Record<Lang, Record<string, string>> = {
  en: {
    title: "Agents",
    daemon: "daemon",
    onDemand: "on-demand",
    enabled: "enabled",
    locked: "locked",
    model: "Model",
    autoAssign: "Auto-assign models",
    autoAssignDesc: "Automatically assign the best available model to each agent based on its role",
    save: "Save",
    saved: "✓ Saved",
    noModels: "No models available. Configure a provider in Settings first.",
    heavy: "Needs powerful model",
    medium: "Standard model",
    light: "Lightweight model sufficient",
  },
  zh: {
    title: "代理",
    daemon: "守护进程",
    onDemand: "按需",
    enabled: "已启用",
    locked: "已锁定",
    model: "模型",
    autoAssign: "自动分配模型",
    autoAssignDesc: "根据每个代理的角色自动分配最佳可用模型",
    save: "保存",
    saved: "✓ 已保存",
    noModels: "无可用模型。请先在设置中配置提供商。",
    heavy: "需要强力模型",
    medium: "标准模型",
    light: "轻量模型即可",
  },
  ja: {
    title: "エージェント",
    daemon: "デーモン",
    onDemand: "オンデマンド",
    enabled: "有効",
    locked: "ロック中",
    model: "モデル",
    autoAssign: "モデル自動割り当て",
    autoAssignDesc: "各エージェントの役割に基づいて最適なモデルを自動割り当て",
    save: "保存",
    saved: "✓ 保存済み",
    noModels: "利用可能なモデルがありません。先に設定でプロバイダーを構成してください。",
    heavy: "高性能モデルが必要",
    medium: "標準モデル",
    light: "軽量モデルで十分",
  },
};

const TIER_COLORS: Record<string, string> = {
  heavy: "text-claw-light",
  medium: "text-gold",
  light: "text-circuit-light",
};

export default function AgentsPage() {
  const { lang } = useLang();
  const t = translations[lang] || translations.en;
  const [agents, setAgents] = useState<Agent[]>([]);
  const [assignments, setAssignments] = useState<Record<string, string>>({});
  const [available, setAvailable] = useState<{ provider: string; model: string }[]>([]);
  const [saved, setSaved] = useState(false);
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);

  useEffect(() => {
    fetch(`${API}/api/agents`)
      .then((r) => r.json())
      .then((data) => {
        const agentList = data.agents || [];
        setAgents(agentList);
        const savedAssignments = localStorage.getItem("quantclaw_agent_models");
        if (savedAssignments) {
          setAssignments(JSON.parse(savedAssignments));
        }
      });

    fetch("http://localhost:11434/api/tags", { signal: AbortSignal.timeout(3000) })
      .then((r) => r.json())
      .then((data) => {
        const names = (data.models || []).map((m: { name: string }) => m.name);
        setOllamaModels(names);
        localStorage.setItem("quantclaw_ollama_models", JSON.stringify(names));
      })
      .catch(() => {});

    for (const p of ["openai", "anthropic"]) {
      fetch(`${API}/api/oauth/status/${p}`)
        .then((r) => r.json())
        .then((data) => {
          if (data.authenticated) {
            localStorage.setItem(`quantclaw_oauth_${p}`, "true");
          }
        })
        .catch(() => {});
    }
  }, []);

  useEffect(() => {
    const models = getAvailableModels();
    setAvailable(models);
    const savedAssignments = localStorage.getItem("quantclaw_agent_models");
    if (!savedAssignments && agents.length > 0 && models.length > 0) {
      const auto = autoAssignModels(agents, models);
      setAssignments(auto);
      localStorage.setItem("quantclaw_agent_models", JSON.stringify(auto));
    }
  }, [agents, ollamaModels]);

  const handleModelChange = (agentName: string, model: string) => {
    const updated = { ...assignments, [agentName]: model };
    setAssignments(updated);
    localStorage.setItem("quantclaw_agent_models", JSON.stringify(updated));
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const handleAutoAssign = () => {
    const models = getAvailableModels();
    const auto = autoAssignModels(agents, models);
    setAssignments(auto);
    localStorage.setItem("quantclaw_agent_models", JSON.stringify(auto));
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const allModels = [
    ...ollamaModels,
    ...available.map((a) => a.model),
  ].filter((m, i, arr) => arr.indexOf(m) === i);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gold" style={{ fontFamily: "var(--font-display)" }}>{t.title}</h1>
        <div className="flex items-center gap-3">
          {saved && (
            <span className="text-xs text-circuit-light font-mono text-glow-circuit">{t.saved}</span>
          )}
          <button
            onClick={handleAutoAssign}
            disabled={allModels.length === 0}
            className="px-4 py-2 rounded-lg bg-gold/10 border border-gold/30 text-gold text-xs font-medium hover:bg-gold/20 transition-all cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            style={{ fontFamily: "var(--font-display)" }}
          >
            {t.autoAssign}
          </button>
        </div>
      </div>

      {allModels.length === 0 && (
        <p className="text-sm text-muted mb-4">{t.noModels}</p>
      )}

      <div className="space-y-2">
        {agents.map((agent) => {
          const tier = AGENT_TIERS[agent.name] || "medium";
          const currentModel = assignments[agent.name] || agent.model || "";

          return (
            <div
              key={agent.name}
              className="card-cyber p-4 transition-all"
            >
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0 flex-shrink-0 w-44">
                  <div className="flex items-center gap-2">
                    <p className="font-medium text-sm text-[#a0b0cc]">{agent.name.replace("_", " ")}</p>
                    <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-circuit/10 text-circuit-light border border-circuit/20">
                      {t.enabled}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-[10px] text-muted">
                      {agent.daemon ? t.daemon : t.onDemand}
                    </span>
                    <span className={`text-[10px] ${TIER_COLORS[tier]}`}>
                      · {t[tier] || tier}
                    </span>
                  </div>
                </div>

                <div className="flex-1 min-w-0">
                  <select
                    value={currentModel}
                    onChange={(e) => handleModelChange(agent.name, e.target.value)}
                    className="w-full bg-keel/50 border border-trace rounded-lg px-3 py-2 text-xs font-mono text-[#8a9ab0] outline-none focus:border-gold/30 transition-colors cursor-pointer appearance-none"
                    style={{
                      backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M3 4.5L6 7.5L9 4.5' stroke='%234a5a7a' stroke-width='1.5' stroke-linecap='round' fill='none'/%3E%3C/svg%3E")`,
                      backgroundRepeat: "no-repeat",
                      backgroundPosition: "right 8px center",
                      paddingRight: "28px",
                    }}
                  >
                    {currentModel && !allModels.includes(currentModel) && (
                      <option value={currentModel}>{currentModel} (default)</option>
                    )}
                    {allModels.map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <p className="text-[10px] text-[#2a3a5a] mt-4 font-mono">
        {t.autoAssignDesc}
      </p>
    </div>
  );
}
