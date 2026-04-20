"use client";
import { useState, useRef, useEffect, useCallback } from "react";
import { useLang } from "../../lang-context";
import type { FloorAgent } from "./types";
import { STATIONS, getStationByName, getStationDisplayName } from "./stations";

const API = "http://localhost:24120";

type Lang = "en" | "zh" | "ja";

interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  agent?: string;
  timestamp: Date;
  status?: "streaming" | "done" | "error";
}

interface ProviderOption {
  id: string;
  name: string;
  models: string[];
  local?: boolean;
}

const MODEL_PROVIDERS: ProviderOption[] = [
  { id: "ollama", name: "Ollama", models: [], local: true },
  { id: "openai", name: "OpenAI", models: ["gpt-5.4", "gpt-5.4-mini", "gpt-5.3-codex"] },
  { id: "anthropic", name: "Anthropic", models: ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001", "claude-sonnet-4-5-20250929", "claude-opus-4-5-20251101"] },
  { id: "google", name: "Google Gemini", models: ["gemini-3.1-pro-preview", "gemini-3-flash-preview", "gemini-3.1-flash-lite-preview", "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-flash-image"] },
  { id: "deepseek", name: "DeepSeek", models: ["deepseek-chat", "deepseek-reasoner"] },
  { id: "xai", name: "xAI", models: ["grok-4.20-0309-reasoning", "grok-4.20-0309-non-reasoning", "grok-4-1-fast-reasoning", "grok-4-1-fast-non-reasoning"] },
  { id: "mistral", name: "Mistral", models: ["mistral-large-latest", "mistral-medium-latest", "mistral-small-latest", "codestral-2501", "devstral-2-25-12"] },
  { id: "groq", name: "Groq", models: ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3-32b"] },
  { id: "openrouter", name: "OpenRouter", models: ["openai/gpt-5.4", "anthropic/claude-opus-4-6", "anthropic/claude-sonnet-4-6", "google/gemini-3.1-pro-preview", "deepseek/deepseek-chat"] },
  { id: "together", name: "Together AI", models: ["meta-llama/Llama-3.3-70B-Instruct-Turbo", "deepseek-ai/DeepSeek-V3", "Qwen/Qwen2.5-72B-Instruct-Turbo"] },
];

const AGENT_COLORS: Record<string, string> = {
  scheduler: "#f59e0b",
  ingestor: "#3b82f6",
  validator: "#14b8a6",
  miner: "#ef4444",
  researcher: "#06b6d4",
  executor: "#22c55e",
  reporter: "#f97316",
  trainer: "#ec4899",
  compliance: "#6366f1",
  debugger: "#eab308",
  sentinel: "#f43f5e",
  risk_monitor: "#a855f7",
};

const chatI18n: Record<Lang, {
  session: string;
  agentsOnline: string;
  systemMsg: string;
  greeting: string;
  processing: string;
  placeholder: string;
  routeNote: string;
  talkingTo: string;
  mentionHint: string;
  clearHistory: string;
  clearHistoryConfirm: string;
  clearHistoryDone: string;
  responses: Record<string, string>;
}> = {
  en: {
    session: "Session",
    agentsOnline: "agents online",
    systemMsg: "Session initialized. Connected to QuantClaw orchestrator.",
    greeting: "Welcome back. All systems nominal.\n\nI can help you run backtests, analyze signals, manage your portfolio, or explore strategy templates. What would you like to do?",
    processing: "processing...",
    placeholder: "Message QuantClaw... (type @ to mention an agent)",
    routeNote: "Messages are routed to the appropriate agent automatically",
    talkingTo: "Talking to",
    mentionHint: "Type @ to mention an agent",
    clearHistory: "Clear history",
    clearHistoryConfirm: "Reset every agent's workings and start a fresh campaign?\n\nThis deletes the chat, campaign state, generated strategies, trained models, and allocator decisions. Ingested market data and your login are preserved.",
    clearHistoryDone: "Reset complete. Fresh campaign ready.",
    responses: {
      validator: "I'll set up that backtest for you. Here's what I'll configure:\n\n- Strategy: Momentum (12-month lookback)\n- Universe: SPY\n- Period: 2024-04-01 to 2026-04-01\n- Initial capital: $100,000\n\nThis will run the in-sample backtest + a held-out validation pass.",
      risk_monitor: "Running risk analysis on your current positions...\n\n- Current drawdown: 0.0% (limit: -10%)\n- Max position size: 0% / 5% limit\n- Portfolio beta: 0.00\n- Value at Risk (95%): $0.00\n\nAll risk parameters are within bounds.",
      ingestor: "Scanning for signals across your watchlist...\n\nI'll pull the latest price data, run the signal pipeline, and report findings.",
      reporter: "Here's your current portfolio summary:\n\n- Equity: $100,000\n- Cash: $100,000\n- Open positions: 0\n- Daily P&L: $0.00\n\nNo active positions.",
      executor: "Execution requires a connected broker. Currently no broker plugin is active.",
      researcher: "I'll research that for you. Analyzing recent market data, academic papers, and factor performance.",
      trainer: "To train an ML model, I'll need a target variable, feature set, and training period. Would you like a pre-configured template?",
      debugger: "I'll investigate that. Checking logs and tracing the issue.\n\nRunning diagnostics...",
      scheduler: "I can help with that. Let me route this to the right agent and coordinate the workflow.",
      compliance: "Running compliance check against your configured rule set...",
      sentinel: "Monitoring system health and alerting thresholds. All watchpoints nominal.",
      miner: "Starting pattern mining across your configured data sources...",
    },
  },
  zh: {
    session: "会话",
    agentsOnline: "个代理在线",
    systemMsg: "会话已初始化，已连接 QuantClaw 调度器。",
    greeting: "欢迎回来。系统运行正常。\n\n我可以帮你运行回测、分析信号、管理投资组合或浏览策略模板。你想做什么？",
    processing: "处理中...",
    placeholder: "向 QuantClaw 发送消息... (输入 @ 提及代理)",
    routeNote: "消息会自动路由到对应的代理",
    talkingTo: "正在对话",
    mentionHint: "输入 @ 提及代理",
    clearHistory: "清除记录",
    clearHistoryConfirm: "重置所有代理的工作记录,开启新的活动?\n\n这将删除聊天、活动状态、生成的策略、训练的模型和分配决策。已采集的市场数据和登录状态会保留。",
    clearHistoryDone: "重置完成,新活动已就绪。",
    responses: {
      validator: "我将为你设置回测。配置如下：\n\n- 策略：动量（12个月回看期）\n- 标的：SPY\n- 初始资金：$100,000\n\n将跑样本内回测 + 持出法校验。",
      risk_monitor: "正在对你的当前持仓进行风险分析...\n\n- 当前回撤：0.0%\n- 最大持仓比例：0% / 5% 限制\n\n所有风险参数均在正常范围内。",
      ingestor: "正在扫描自选股中的信号...",
      reporter: "以下是你的投资组合摘要：\n\n- 净值：$100,000\n- 现金：$100,000\n- 持仓数：0",
      executor: "执行交易需要连接券商。当前没有激活的券商插件。",
      researcher: "我来帮你研究。",
      trainer: "训练 ML 模型需要目标变量、特征集和训练期。你想使用预配置模板吗？",
      debugger: "我来排查这个问题。正在运行系统诊断...",
      scheduler: "我可以帮你处理。让我将任务路由到合适的代理。",
      compliance: "正在运行合规检查...",
      sentinel: "正在监控系统健康状态和告警阈值。所有监控点正常。",
      miner: "正在对你配置的数据源进行模式挖掘...",
    },
  },
  ja: {
    session: "セッション",
    agentsOnline: "エージェントがオンライン",
    systemMsg: "セッション初期化完了。QuantClaw オーケストレーターに接続しました。",
    greeting: "お帰りなさい。全システム正常稼働中。\n\nバックテストの実行、シグナル分析、ポートフォリオ管理をお手伝いできます。何をしましょうか？",
    processing: "処理中...",
    placeholder: "QuantClaw にメッセージを送信... (@でエージェントを指定)",
    routeNote: "メッセージは適切なエージェントに自動ルーティングされます",
    talkingTo: "対話中",
    mentionHint: "@でエージェントを指定",
    clearHistory: "履歴を消去",
    clearHistoryConfirm: "すべてのエージェントの作業をリセットして新しいキャンペーンを開始しますか?\n\nチャット、キャンペーン状態、生成された戦略、トレーニング済みモデル、アロケーション決定が削除されます。取得済みの市場データとログインは保持されます。",
    clearHistoryDone: "リセット完了。新しいキャンペーンの準備ができました。",
    responses: {
      validator: "バックテストを設定します。\n\n- 戦略：モメンタム（12ヶ月ルックバック）\n- ユニバース：SPY\n- 初期資金：$100,000\n\nインサンプル + ホールドアウト検証を走らせます。",
      risk_monitor: "リスク分析を実行中...\n\n- 現在のドローダウン：0.0%\n- VaR (95%)：$0.00\n\nすべて正常範囲内です。",
      ingestor: "ウォッチリスト全体のシグナルをスキャン中...",
      reporter: "ポートフォリオの概要：\n\n- 評価額：$100,000\n- 現金：$100,000\n- ポジション数：0",
      executor: "取引執行にはブローカー接続が必要です。",
      researcher: "調査します。最近の市場データを分析します。",
      trainer: "MLモデルの学習に必要なものを確認します。テンプレートを使いますか？",
      debugger: "調査します。ログを確認中...",
      scheduler: "お手伝いします。適切なエージェントにルーティングします。",
      compliance: "コンプライアンスチェックを実行中...",
      sentinel: "システム健全性を監視中。すべて正常です。",
      miner: "パターンマイニングを開始中...",
    },
  },
};

function formatTime(date: Date): string {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function AgentBadge({ name }: { name: string }) {
  const color = AGENT_COLORS[name] || "#6b7280";
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-mono font-medium uppercase tracking-wider"
      style={{ backgroundColor: `${color}15`, color, border: `1px solid ${color}30` }}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} />
      {name.replace("_", " ")}
    </span>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 px-1 py-2">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-1.5 h-1.5 rounded-full bg-gold/60"
          style={{
            animation: "typing-dot 1.4s ease-in-out infinite",
            animationDelay: `${i * 0.2}s`,
          }}
        />
      ))}
    </div>
  );
}

function createBootstrapMessages(t: (typeof chatI18n)[Lang]): Message[] {
  return [
    {
      id: "welcome",
      role: "system",
      content: t.systemMsg,
      timestamp: new Date(),
      status: "done",
    },
    {
      id: "greeting",
      role: "assistant",
      agent: "scheduler",
      content: t.greeting,
      timestamp: new Date(),
      status: "done",
    },
  ];
}

function isBootstrapMessage(message: Message): boolean {
  return message.id === "welcome" || message.id === "greeting";
}

function isSimpleQuery(message: string): boolean {
  const lower = message.toLowerCase();
  // Questions that should be answered directly without orchestration
  const queryPatterns = [
    /^(what|which|who|where|when|how)\s/i,
    /model/i,
    /help/i,
    /status/i,
    /available/i,
    /can\s(i|you)/i,
    /version/i,
    /explain/i,
    /tell\s(me|us)/i,
  ];

  // Check if message is a simple question
  if (queryPatterns.some(p => p.test(lower))) {
    // But exclude workflow commands disguised as questions
    const workflows = ["backtest", "trade", "execute", "run", "start", "launch"];
    if (!workflows.some(w => lower.includes(w))) {
      return true;
    }
  }

  return false;
}

function routeToAgent(message: string): string {
  const lower = message.toLowerCase();
  if (lower.includes("backtest") || lower.includes("validate") || lower.includes("回测") || lower.includes("校验") || lower.includes("バックテスト") || lower.includes("バリデート")) return "validator";
  if (lower.includes("risk") || lower.includes("风险") || lower.includes("风控") || lower.includes("リスク")) return "risk_monitor";
  if (lower.includes("signal") || lower.includes("信号") || lower.includes("シグナル") || lower.includes("ingest") || lower.includes("采集")) return "ingestor";
  if (lower.includes("portfolio") || lower.includes("投资组合") || lower.includes("持仓") || lower.includes("ポートフォリオ")) return "reporter";
  if (lower.includes("execute") || lower.includes("buy") || lower.includes("sell") || lower.includes("买") || lower.includes("卖")) return "executor";
  if (lower.includes("research") || lower.includes("研究") || lower.includes("调查")) return "researcher";
  if (lower.includes("train") || lower.includes("训练") || lower.includes("学習")) return "trainer";
  if (lower.includes("debug") || lower.includes("调试") || lower.includes("デバッグ")) return "debugger";
  if (lower.includes("compliance") || lower.includes("合规")) return "compliance";
  return "scheduler";
}

interface ChatPanelProps {
  agents: FloorAgent[];
  selectedAgent: string | null;
  onAgentSelect: (name: string) => void;
}

export function ChatPanel({ agents, selectedAgent, onAgentSelect }: ChatPanelProps) {
  const { lang } = useLang();
  const t = chatI18n[lang as Lang] || chatI18n.en;

  const [messages, setMessages] = useState<Message[]>(() => {
    if (typeof window !== "undefined") {
      try {
        const saved = localStorage.getItem("quantclaw_chat_history");
        if (saved) {
          const parsed = JSON.parse(saved) as Message[];
          return parsed.map((m) => ({ ...m, timestamp: new Date(m.timestamp) }));
        }
      } catch { /* ignore corrupt data */ }
      return createBootstrapMessages(t);
    }
    return createBootstrapMessages(t);
  });
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [isOrchestrating, setIsOrchestrating] = useState(false);
  const [targetAgent, setTargetAgent] = useState("scheduler");
  const [showMentionDropdown, setShowMentionDropdown] = useState(false);
  const [mentionFilter, setMentionFilter] = useState("");
  const [activeProvider, setActiveProvider] = useState(() => {
    if (typeof window === "undefined") return "ollama";
    return localStorage.getItem("quantclaw_provider") || "ollama";
  });
  const [selectedModel, setSelectedModel] = useState(() => {
    if (typeof window === "undefined") return "";
    const savedProvider = localStorage.getItem("quantclaw_provider") || "ollama";
    const savedModel = localStorage.getItem("quantclaw_model") || "";
    const providerDef = MODEL_PROVIDERS.find((p) => p.id === savedProvider);
    const validModels = providerDef?.models || [];
    if (savedModel && (savedProvider === "ollama" || validModels.includes(savedModel))) {
      return savedModel;
    }
    return validModels[0] || "";
  });
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [showModelPicker, setShowModelPicker] = useState(false);
  const [fontSize, setFontSize] = useState(() => {
    if (typeof window !== "undefined") {
      return parseInt(localStorage.getItem("quantclaw_chat_fontsize") || "16", 10);
    }
    return 16;
  });

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Detect locally available Ollama models.
  useEffect(() => {
    fetch("http://localhost:11434/api/tags", { signal: AbortSignal.timeout(3000) })
      .then((r) => r.json())
      .then((data) => {
        const names = (data.models || []).map((m: { name: string }) => m.name);
        setOllamaModels(names);
      })
      .catch(() => {});
  }, []);

  // Persist messages to localStorage
  useEffect(() => {
    try {
      localStorage.setItem("quantclaw_chat_history", JSON.stringify(messages));
    } catch { /* storage full or unavailable */ }
  }, [messages]);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Subscribe to WebSocket for chat.narrative and orchestration.cycle_complete events
  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;

    function connect() {
      if (closed) return;
      try {
        ws = new WebSocket("ws://localhost:24120/ws/events");
        ws.onmessage = (e) => {
          try {
            const event = JSON.parse(e.data);
            if (event.type === "chat.narrative" && event.payload?.message) {
              setMessages((prev) => [...prev, {
                id: `narrative-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
                role: "assistant" as const,
                content: event.payload.message,
                agent: event.payload.role || "scheduler",
                timestamp: new Date(),
                status: "done" as const,
              }]);
            }
            if (event.type === "orchestration.cycle_complete") {
              setIsOrchestrating(false);
            }
          } catch { /* ignore malformed events */ }
        };
        ws.onclose = () => {
          ws = null;
          if (!closed) setTimeout(connect, 2000);
        };
      } catch {
        if (!closed) setTimeout(connect, 2000);
      }
    }

    connect();
    return () => {
      closed = true;
      if (ws) ws.close();
    };
  }, []);

  const sendMessage = useCallback(
    async (text?: string) => {
      const content = text || input.trim();
      if (!content || isStreaming) return;

      // Strip @mention prefix for display but use for routing
      const mentionMatch = content.match(/^@(\w+)\s*/);
      const displayContent = mentionMatch ? content.slice(mentionMatch[0].length) : content;
      const routeTarget = mentionMatch ? mentionMatch[1] : (selectedAgent || targetAgent);

      const userMsg: Message = {
        id: `user-${Date.now()}`,
        role: "user",
        content: displayContent || content,
        timestamp: new Date(),
        status: "done",
      };

      setMessages((prev) => [...prev, userMsg]);
      setInput("");

      // Check if this is a simple info query (should not trigger orchestration)
      if (isSimpleQuery(displayContent)) {
        setIsStreaming(true);
        try {
          // Call backend with query_only flag to get LLM response without orchestration
          const res = await fetch(`${API}/api/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              message: displayContent,
              lang,
              history: messages
                .filter((m) => m.role !== "system" && !isBootstrapMessage(m))
                .slice(-5)
                .map((m) => ({ role: m.role, content: m.content })),
              query_only: true, // Flag for backend: answer with LLM, don't trigger orchestration
              model: selectedModel,
              provider: activeProvider,
              api_key: localStorage.getItem(`quantclaw_key_${activeProvider}`) || "",
              agent_models: JSON.parse(localStorage.getItem("quantclaw_agent_models") || "{}"),
            }),
          });
          const data = await res.json();
          const assistantMsg: Message = {
            id: `assistant-${Date.now()}`,
            role: "assistant",
            agent: "scheduler",
            content: data.response || data.error || "Let me help with that.",
            timestamp: new Date(),
            status: data.error ? "error" : "done",
          };
          setMessages((prev) => [...prev, assistantMsg]);
        } catch (e) {
          setMessages((prev) => [...prev, {
            id: `assistant-${Date.now()}`,
            role: "assistant",
            agent: "scheduler",
            content: "I couldn't reach the backend to answer that. Try again or ask about a trading task.",
            timestamp: new Date(),
            status: "error",
          }]);
        }
        setIsStreaming(false);
        return;
      }

      setIsStreaming(true);

      const history = messages
        .filter((m) => m.role !== "system" && !isBootstrapMessage(m))
        .slice(-10)
        .map((m) => ({ role: m.role, content: m.content }));

      try {
        const res = await fetch(`${API}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: content,
            lang,
            history,
            agent: routeTarget,
            mention: !!mentionMatch,
            model: selectedModel,
            provider: activeProvider,
            api_key: localStorage.getItem(`quantclaw_key_${activeProvider}`) || "",
            agent_models: JSON.parse(localStorage.getItem("quantclaw_agent_models") || "{}"),
          }),
        });
        const data = await res.json();

        if (data.status === "orchestrating") {
          setIsOrchestrating(true);
          setMessages((prev) => [...prev, {
            id: `orchestrating-${Date.now()}`,
            role: "assistant",
            agent: data.agent || "scheduler",
            content: "Planning...",
            timestamp: new Date(),
            status: "streaming",
          }]);
          setIsStreaming(false);
          return;
        }

        const assistantMsg: Message = {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          agent: data.agent || routeTarget,
          content: data.error || data.response || t.responses[routeTarget] || t.responses.scheduler,
          timestamp: new Date(),
          status: data.error ? "error" : "done",
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } catch {
        const assignedAgent = mentionMatch ? routeTarget : routeToAgent(content);
        const assistantMsg: Message = {
          id: `assistant-${Date.now()}`,
          role: "assistant",
          agent: assignedAgent,
          content: t.responses[assignedAgent] || t.responses.scheduler,
          timestamp: new Date(),
          status: "done",
        };
        setMessages((prev) => [...prev, assistantMsg]);
      }
      setIsStreaming(false);
    },
    [input, isStreaming, messages, lang, selectedModel, activeProvider, selectedAgent, targetAgent, t.responses],
  );

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setInput(value);

    // Detect @mention
    const cursorPos = e.target.selectionStart;
    const textBeforeCursor = value.slice(0, cursorPos);
    const mentionMatch = textBeforeCursor.match(/@(\w*)$/);

    if (mentionMatch) {
      setShowMentionDropdown(true);
      setMentionFilter(mentionMatch[1].toLowerCase());
    } else {
      setShowMentionDropdown(false);
      setMentionFilter("");
    }
  };

  const insertMention = (agentName: string) => {
    const cursorPos = inputRef.current?.selectionStart || 0;
    const textBeforeCursor = input.slice(0, cursorPos);
    const textAfterCursor = input.slice(cursorPos);
    const beforeMention = textBeforeCursor.replace(/@\w*$/, "");
    const newInput = `${beforeMention}@${agentName} ${textAfterCursor}`;

    setInput(newInput);
    setTargetAgent(agentName);
    onAgentSelect(agentName);
    setShowMentionDropdown(false);
    setMentionFilter("");

    // Focus back to input
    setTimeout(() => {
      inputRef.current?.focus();
    }, 0);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (showMentionDropdown) {
        // If dropdown is open, close it
        setShowMentionDropdown(false);
        return;
      }
      sendMessage();
    }
    if (e.key === "Escape") {
      setShowMentionDropdown(false);
    }
  };

  const switchProvider = (providerId: string) => {
    setActiveProvider(providerId);
    localStorage.setItem("quantclaw_provider", providerId);
    const p = MODEL_PROVIDERS.find((mp) => mp.id === providerId);
    const models = providerId === "ollama" ? ollamaModels : (p?.models || []);
    if (models.length > 0) {
      setSelectedModel(models[0]);
      localStorage.setItem("quantclaw_model", models[0]);
    }
    setShowModelPicker(false);
  };

  const switchModel = (model: string) => {
    setSelectedModel(model);
    localStorage.setItem("quantclaw_model", model);
    setShowModelPicker(false);
  };

  const clearChat = async () => {
    if (!window.confirm(t.clearHistoryConfirm)) {
      return;
    }
    // Hit the backend reset first so every agent's durable state is wiped
    // before we reset the UI. If the backend is unreachable, still clear
    // the UI so the user isn't stuck — but tell them.
    let backendOk = false;
    try {
      const resp = await fetch(`${API}/api/reset`, { method: "POST" });
      backendOk = resp.ok;
    } catch {
      backendOk = false;
    }
    // Clear every piece of UI state that could carry campaign memory forward.
    localStorage.removeItem("quantclaw_chat_history");
    for (const key of Object.keys(localStorage)) {
      if (key.startsWith("quantclaw_")
          && key !== "quantclaw_floor_mode"
          && key !== "quantclaw_model"
          && key !== "quantclaw_chat_width"
          && key !== "quantclaw_agent_models"
          && key !== "quantclaw_ollama_models") {
        localStorage.removeItem(key);
      }
    }
    const fresh = createBootstrapMessages(t);
    if (backendOk) {
      fresh.push({
        id: `reset-${Date.now()}`,
        role: "system",
        agent: "scheduler",
        content: t.clearHistoryDone,
        timestamp: new Date(),
      });
    }
    setMessages(fresh);
    setShowMentionDropdown(false);
    setMentionFilter("");
    setInput("");
    setTimeout(() => {
      inputRef.current?.focus();
    }, 0);
  };

  const currentModels = activeProvider === "ollama"
    ? ollamaModels
    : (MODEL_PROVIDERS.find((p) => p.id === activeProvider)?.models || []);

  const enabledAgents = agents.filter((a) => a.enabled);
  const effectiveTargetAgent = selectedAgent || targetAgent;
  const targetStation = getStationByName(effectiveTargetAgent);
  const targetDisplayName = targetStation
    ? getStationDisplayName(targetStation, lang)
    : effectiveTargetAgent;
  const targetColor = AGENT_COLORS[effectiveTargetAgent] || "#f59e0b";

  // Filter agents for mention dropdown
  const mentionAgents = STATIONS.filter((s) =>
    s.name.toLowerCase().includes(mentionFilter)
  );
  const hasConversationHistory = messages.some((message) => !isBootstrapMessage(message));

  return (
    <div className="flex flex-col h-full bg-void border-l border-trace">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-trace/60 bg-gradient-to-r from-void to-void/80">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span
              className="w-2.5 h-2.5 rounded-full animate-pulse"
              style={{ backgroundColor: targetColor }}
            />
            <span className="text-sm font-mono text-[#6a7a9a] tracking-wider">
              {t.talkingTo}
            </span>
            <span
              className="text-sm font-semibold"
              style={{ color: targetColor }}
            >
              {targetDisplayName}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
        {/* Font size controls */}
        <div className="flex items-center gap-1 border border-trace/30 rounded-lg px-1 py-0.5 bg-void/40">
          <button
            onClick={() => {
              const n = Math.max(10, fontSize - 2);
              setFontSize(n);
              localStorage.setItem("quantclaw_chat_fontsize", String(n));
            }}
            className="w-6 h-6 flex items-center justify-center text-[#6a7a9a] hover:text-gold text-xs cursor-pointer rounded transition-colors"
          >
            −
          </button>
          <span className="text-[10px] text-[#6a7a9a] font-mono w-5 text-center border-l border-r border-trace/20 px-1">{fontSize}</span>
          <button
            onClick={() => {
              const n = Math.min(24, fontSize + 2);
              setFontSize(n);
              localStorage.setItem("quantclaw_chat_fontsize", String(n));
            }}
            className="w-6 h-6 flex items-center justify-center text-[#6a7a9a] hover:text-gold text-xs cursor-pointer rounded transition-colors"
          >
            +
          </button>
        </div>

        {/* Provider / Model selector */}
        <div className="relative">
          <button
            onClick={() => setShowModelPicker(!showModelPicker)}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-trace/30 hover:border-trace/60 bg-void/40 transition-all cursor-pointer text-xs"
          >
            <span className="text-[#6a7a9a] font-mono">
              {MODEL_PROVIDERS.find((p) => p.id === activeProvider)?.name || activeProvider}
            </span>
            <span className="text-[#2a3a5a] text-[9px]">·</span>
            <span className="text-gold font-mono text-[10px]">
              {selectedModel?.split("/").pop()?.slice(0, 12) || "\u2014"}
            </span>
            <svg
              className={`w-2.5 h-2.5 text-[#6a7a9a] transition-transform ${showModelPicker ? "rotate-180" : ""}`}
              viewBox="0 0 12 12"
              fill="none"
            >
              <path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </button>

          {showModelPicker && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setShowModelPicker(false)} />
              <div className="absolute right-0 top-full mt-1.5 z-50 w-64 bg-hull border border-trace/40 rounded-lg shadow-2xl shadow-black/60 overflow-hidden">
                {/* Providers */}
                <div className="p-2.5 border-b border-trace/30 bg-void/40">
                  <p className="text-[9px] font-mono text-[#6a7a9a] uppercase tracking-wider px-1.5 py-0.5">Provider</p>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {MODEL_PROVIDERS.map((p) => (
                      <button
                        key={p.id}
                        onClick={() => switchProvider(p.id)}
                        className={`px-2 py-0.5 rounded text-[10px] transition-all cursor-pointer ${
                          activeProvider === p.id
                            ? "bg-gold/20 text-gold border border-gold/40"
                            : "text-[#6a7a9a] hover:text-[#a0b0cc] border border-trace/20 hover:border-trace/40"
                        }`}
                      >
                        {p.name}
                      </button>
                    ))}
                  </div>
                </div>
                {/* Models */}
                <div className="p-2.5 max-h-40 overflow-y-auto">
                  <p className="text-[9px] font-mono text-[#6a7a9a] uppercase tracking-wider px-1.5 py-0.5">Model</p>
                  {currentModels.length > 0 ? (
                    <div className="space-y-0.5 mt-1">
                      {currentModels.map((m) => (
                        <button
                          key={m}
                          onClick={() => switchModel(m)}
                          className={`w-full text-left px-2 py-1 rounded text-[10px] font-mono transition-all cursor-pointer truncate ${
                            selectedModel === m
                              ? "bg-gold/15 text-gold"
                              : "text-[#6a7a9a] hover:bg-keel/40 hover:text-[#a0b0cc]"
                          }`}
                          title={m}
                        >
                          {m}
                        </button>
                      ))}
                    </div>
                  ) : (
                    <p className="text-[10px] text-[#6a7a9a] px-2 py-1.5 mt-1">
                      {activeProvider === "ollama"
                        ? (lang === "zh" ? "未检测到模型" : lang === "ja" ? "モデルが見つかりません" : "No models")
                        : (lang === "zh" ? "需配置 API" : lang === "ja" ? "APIキー設定" : "Configure API")}
                    </p>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-1" style={{ fontSize: `${fontSize}px` }}>
        {messages.map((msg) => (
          <div key={msg.id} className="animate-fade-up">
            {msg.role === "system" ? (
              <div className="flex items-center gap-2 py-2 my-2">
                <div className="flex-1 h-px bg-keel/50" />
                <span className="text-[10px] font-mono text-[#2a3a5a] tracking-wider uppercase">
                  {msg.content}
                </span>
                <div className="flex-1 h-px bg-keel/50" />
              </div>
            ) : msg.role === "user" ? (
              <div className="flex justify-end mb-3">
                <div className="max-w-[85%]">
                  <div className="bg-gold/10 border border-gold/20 rounded-2xl rounded-br-sm px-4 py-3">
                    <p className="text-[#a0b0cc] leading-relaxed whitespace-pre-wrap" style={{ fontSize: "inherit" }}>
                      {msg.content}
                    </p>
                  </div>
                  <p className="text-[10px] text-[#1a2a4a] mt-1 text-right font-mono">
                    {formatTime(msg.timestamp)}
                  </p>
                </div>
              </div>
            ) : (
              <div className="mb-4">
                <div className="flex items-center gap-2 mb-1.5">
                  {msg.agent && <AgentBadge name={msg.agent} />}
                  <span className="text-[10px] text-[#1a2a4a] font-mono">
                    {formatTime(msg.timestamp)}
                  </span>
                </div>
                <div className="max-w-[95%] pl-0.5">
                  <p className="text-[#8a9ab0] leading-relaxed whitespace-pre-wrap" style={{ fontSize: "inherit" }}>
                    {msg.content}
                  </p>
                </div>
              </div>
            )}
          </div>
        ))}

        {isStreaming && (
          <div className="mb-4 animate-fade-up">
            <div className="flex items-center gap-2 mb-1.5">
              <span className="text-[10px] font-mono text-[#2a3a5a] tracking-wider">
                {t.processing}
              </span>
            </div>
            <TypingIndicator />
          </div>
        )}

        {isOrchestrating && !isStreaming && (
          <div className="mb-4 animate-fade-up">
            <div className="flex items-center gap-2 mb-1.5">
              <AgentBadge name="scheduler" />
              <span className="text-[10px] font-mono text-gold/60 tracking-wider">
                orchestrating...
              </span>
            </div>
            <TypingIndicator />
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="px-4 pb-4 pt-2">
        <div className="relative">
          <div className="mb-2 flex items-center justify-end">
            <button
              onClick={clearChat}
              disabled={!hasConversationHistory}
              className={`inline-flex items-center gap-2 rounded-xl border px-3 py-1.5 text-[11px] font-mono transition-all ${
                hasConversationHistory
                  ? "border-claw/20 bg-claw/8 text-claw-light hover:border-claw-light/35 hover:bg-claw/12 cursor-pointer"
                  : "border-trace bg-hull/40 text-[#2a3a5a] cursor-not-allowed"
              }`}
              title={t.clearHistory}
              aria-label={t.clearHistory}
            >
              <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path
                  d="M3.5 4.5H12.5M6.5 7V11M9.5 7V11M5.5 2.5H10.5M5 4.5L5.4 12.1C5.46 13.2 6.37 14 7.48 14H8.52C9.63 14 10.54 13.2 10.6 12.1L11 4.5"
                  stroke="currentColor"
                  strokeWidth="1.25"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              {t.clearHistory}
            </button>
          </div>

          {/* @mention dropdown */}
          {showMentionDropdown && (
            <div className="absolute bottom-full mb-2 left-0 right-0 bg-hull border border-trace rounded-xl shadow-2xl shadow-black/50 max-h-64 overflow-y-auto z-50">
              <p className="text-[10px] font-mono text-[#2a3a5a] uppercase tracking-wider px-3 pt-2 pb-1">
                {t.mentionHint}
              </p>
              {mentionAgents.map((station) => {
                const floorAgent = agents.find((a) => a.name === station.name);
                const isLocked = floorAgent?.locked ?? false;
                const isEnabled = floorAgent?.enabled ?? true;
                const state = floorAgent?.state ?? "idle";
                const color = AGENT_COLORS[station.name] || "#6b7280";
                const displayName = getStationDisplayName(station, lang);

                return (
                  <button
                    key={station.name}
                    onClick={() => {
                      if (!isLocked) {
                        insertMention(station.name);
                      }
                    }}
                    disabled={isLocked}
                    className={`w-full flex items-center gap-3 px-3 py-2 text-left transition-all ${
                      isLocked
                        ? "opacity-40 cursor-not-allowed"
                        : "hover:bg-keel/50 cursor-pointer"
                    }`}
                  >
                    <span
                      className="w-2 h-2 rounded-full flex-shrink-0"
                      style={{
                        backgroundColor: isLocked ? "#4b5563" : color,
                        opacity: isEnabled ? 1 : 0.4,
                      }}
                    />
                    <div className="flex-1 min-w-0">
                      <span
                        className="text-xs font-medium"
                        style={{ color: isLocked ? "#6b7280" : color }}
                      >
                        {displayName}
                      </span>
                      <span className="text-[10px] text-[#2a3a5a] ml-2 font-mono">
                        @{station.name}
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      {isLocked ? (
                        <svg className="w-3 h-3 text-[#2a3a5a]" viewBox="0 0 16 16" fill="currentColor">
                          <path d="M8 1a4 4 0 0 0-4 4v2H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V8a1 1 0 0 0-1-1h-1V5a4 4 0 0 0-4-4zm2 6H6V5a2 2 0 1 1 4 0v2z" />
                        </svg>
                      ) : (
                        <span
                          className="text-[9px] font-mono uppercase tracking-wider px-1.5 py-0.5 rounded"
                          style={{
                            color: state === "busy" ? "#f59e0b" : "#6b7280",
                            backgroundColor: state === "busy" ? "#f59e0b15" : "#6b728015",
                          }}
                        >
                          {state}
                        </span>
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
          )}

          <div className="relative flex items-end bg-hull/60 border border-trace rounded-2xl focus-within:border-gold/30 transition-colors">
            <textarea
              ref={inputRef}
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder={t.placeholder}
              rows={1}
              className="flex-1 bg-transparent text-[#a0b0cc] placeholder-gray-600 px-4 py-3.5 resize-none outline-none max-h-32"
              style={{ fontSize: `${fontSize}px` }}
            />
            {(isOrchestrating || isStreaming) && !input.trim() ? (
              <button
                onClick={async () => {
                  try {
                    await fetch(`${API}/api/orchestration/stop`, { method: "POST" });
                  } catch { /* ignore network errors */ }
                  setIsOrchestrating(false);
                  setIsStreaming(false);
                  setMessages((prev) => [...prev, {
                    id: `stop-${Date.now()}`,
                    role: "assistant" as const,
                    content: "Workflow stopped.",
                    agent: "scheduler",
                    timestamp: new Date(),
                    status: "done" as const,
                  }]);
                }}
                className="mr-2 mb-2 p-2 rounded-xl bg-claw/15 border border-claw/40 text-claw hover:bg-claw/25 hover:text-claw-light cursor-pointer transition-all duration-200"
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <rect x="3" y="3" width="10" height="10" rx="1.5" fill="currentColor"/>
                </svg>
              </button>
            ) : (
              <button
                onClick={() => sendMessage()}
                disabled={!input.trim() || isStreaming}
                className={`mr-2 mb-2 p-2 rounded-xl transition-all duration-200 ${
                  input.trim() && !isStreaming
                    ? "bg-gold text-void hover:bg-gold-light cursor-pointer"
                    : "bg-keel/50 text-[#2a3a5a] cursor-not-allowed"
                }`}
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M3 13L13 8L3 3V7L9 8L3 9V13Z" fill="currentColor" />
                </svg>
              </button>
            )}
          </div>
        </div>
        <p className="text-[10px] text-[#1a2a4a] mt-2 text-center font-mono">
          {t.routeNote}
        </p>
      </div>

      <style jsx>{`
        @keyframes typing-dot {
          0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
          30% { transform: translateY(-4px); opacity: 1; }
        }
      `}</style>
    </div>
  );
}
