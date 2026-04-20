"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLang } from "../lang-context";

const API = "http://localhost:24120";

interface NavItem {
  href: string;
  icon: string;
  en: string;
  zh: string;
  ja: string;
}

const navItems: NavItem[] = [
  { href: "/dashboard", icon: "◉", en: "Home", zh: "首页", ja: "ホーム" },
  { href: "/dashboard/portfolio", icon: "◫", en: "Portfolio", zh: "投资组合", ja: "ポートフォリオ" },
  { href: "/dashboard/strategies", icon: "◈", en: "Strategies", zh: "策略", ja: "戦略" },
  { href: "/dashboard/backtest", icon: "▶", en: "Backtest", zh: "回测", ja: "バックテスト" },
  { href: "/dashboard/agents", icon: "⚙", en: "Agents", zh: "代理", ja: "エージェント" },
  { href: "/dashboard/logs", icon: "▤", en: "Logs", zh: "日志", ja: "ログ" },
  { href: "/dashboard/risk", icon: "⚠", en: "Risk", zh: "风控", ja: "リスク" },
  { href: "/dashboard/learn", icon: "📖", en: "Learn", zh: "学习", ja: "学習" },
  { href: "/dashboard/settings", icon: "⚙", en: "Settings", zh: "设置", ja: "設定" },
];

const subtitles: Record<string, string> = {
  en: "Quant Trading Harness",
  zh: "量化交易引擎",
  ja: "クオンツ取引ハーネス",
};

function LLMBanner() {
  const [show, setShow] = useState(false);
  const [message, setMessage] = useState("No LLM provider detected.");

  useEffect(() => {
    let cancelled = false;

    async function updateBanner() {
      const provider = localStorage.getItem("quantclaw_provider") || "ollama";
      const hasSavedKey = !!localStorage.getItem(`quantclaw_key_${provider}`);

      if (provider === "ollama") {
        try {
          const response = await fetch("http://localhost:11434/api/tags", {
            signal: AbortSignal.timeout(3000),
          });
          const data = await response.json();
          const hasModels = Array.isArray(data.models) && data.models.length > 0;
          if (!cancelled) {
            setShow(!hasModels);
            setMessage(
              hasModels
                ? ""
                : "Ollama is selected, but no local model provider is available."
            );
          }
          return;
        } catch {
          if (!cancelled) {
            setShow(true);
            setMessage("Ollama is selected, but Ollama is not running.");
          }
          return;
        }
      }

      if (hasSavedKey) {
        if (!cancelled) {
          setShow(false);
        }
        return;
      }

      try {
        const response = await fetch(`${API}/api/llm/provider-status/${provider}`, {
          signal: AbortSignal.timeout(3000),
        });
        const data = await response.json();
        if (data?.available) {
          if (!cancelled) {
            setShow(false);
          }
          return;
        }
      } catch {
        // Fall through to the warning banner below.
      }

      if (!cancelled) {
        setShow(true);
        setMessage(
          `The selected ${provider} provider is not configured in this browser yet.`
        );
      }
    }

    void updateBanner();

    const intervalId = window.setInterval(() => {
      void updateBanner();
    }, 5000);

    window.addEventListener("storage", updateBanner);
    window.addEventListener("focus", updateBanner);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
      window.removeEventListener("storage", updateBanner);
      window.removeEventListener("focus", updateBanner);
    };
  }, []);

  if (!show) return null;
  return (
    <div style={{
      background: "linear-gradient(90deg, rgba(139,26,37,0.5), rgba(139,26,37,0.2))",
      color: "#ff8a95", padding: "10px 16px",
      fontSize: 13, textAlign: "center",
      borderBottom: "1px solid rgba(220,53,69,0.2)",
    }}>
      {message} Open Settings to save an API key, connect your provider, or switch to <a href="https://ollama.com" target="_blank" rel="noreferrer"
        style={{color: "#fca5a5", textDecoration: "underline"}}>Ollama</a>.
    </div>
  );
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { lang } = useLang();

  return (
    <div className="min-h-screen flex">
      {/* Sidebar — dense circuit board panel */}
      <nav className="w-60 bg-hull/80 border-r border-trace p-5 flex flex-col relative overflow-hidden">
        {/* Circuit traces in sidebar */}
        <div className="absolute inset-0 pointer-events-none circuit-dense opacity-50" />

        {/* Right edge — glowing trace */}
        <div className="absolute top-0 right-0 bottom-0 w-px" style={{
          background: "linear-gradient(180deg, transparent, rgba(14,107,128,0.25) 30%, rgba(212,165,23,0.12) 60%, transparent 100%)",
        }} />

        {/* Logo area */}
        <Link href="/dashboard" className="mb-7 relative z-10">
          <div className="relative crab-nest flex items-center gap-3 mb-2">
            <img
              src="/mascot.png"
              alt="QuantClaw"
              className="w-9 h-9 object-contain crab-sidebar rounded-sm"
            />
            <h1
              className="text-2xl font-bold tracking-tight"
              style={{ fontFamily: "var(--font-display)" }}
            >
              <span className="text-gold text-glow-gold">Q</span>
              <span className="text-[#8a9ab8]">uantClaw</span>
            </h1>
          </div>
          <div className="trace-line mb-1" />
          <p className="text-[10px] text-muted mt-2 tracking-wide font-mono uppercase">
            {subtitles[lang] || subtitles.en}
          </p>
        </Link>

        {/* Nav */}
        <div className="space-y-0.5 flex-1 relative z-10">
          {navItems.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 px-3 py-2 rounded-md text-[14px] transition-all duration-200 ${
                  isActive
                    ? "bg-circuit/8 text-circuit-light border-l-2 border-circuit-light glow-circuit"
                    : "text-[#3e5070] hover:text-[#7a90b0] hover:bg-keel/30 border-l-2 border-transparent"
                }`}
              >
                <span className={`text-xs ${isActive ? "text-glow-circuit" : ""}`}>{item.icon}</span>
                <span style={{ fontFamily: "var(--font-body)" }}>
                  {item[lang as keyof NavItem] as string || item.en}
                </span>
              </Link>
            );
          })}
        </div>

        <div className="text-[10px] text-[#1a2a45] mt-4 pt-3 border-t border-trace relative z-10 font-mono tracking-wider">
          QUANTCLAW v0.1.0
        </div>
      </nav>

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-auto relative">
        {/* Scanlines */}
        <div className="absolute inset-0 scanlines z-10" />
        {/* Left edge data trace */}
        <div className="absolute top-0 left-0 bottom-0 trace-line-v z-0" />
        <LLMBanner />
        <main className="flex-1 p-6 overflow-auto relative z-0">
          {children}
        </main>
      </div>
    </div>
  );
}
