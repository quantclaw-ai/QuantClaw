"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useLang } from "./lang-context";

const API = "http://localhost:24120";

type Lang = "en" | "zh" | "ja";

const welcomeI18n: Record<Lang, { subtitle: string; tagline: string; divider: string; loading: string }> = {
  en: { subtitle: "Open-source quant trading superagent harness", tagline: "AUTONOMOUS QUANT, UNLOCKED", divider: "Select language", loading: "Loading..." },
  zh: { subtitle: "开源量化交易超级代理引擎", tagline: "自主量化交易,一键解锁", divider: "选择语言", loading: "加载中..." },
  ja: { subtitle: "オープンソースのクオンツ取引スーパーエージェントハーネス", tagline: "自律型クオンツを解放", divider: "言語を選択", loading: "読み込み中..." },
};

const LANGUAGES = [
  { code: "en" as Lang, flag: "🇺🇸", native: "English" },
  { code: "zh" as Lang, flag: "🇨🇳", native: "简体中文" },
  { code: "ja" as Lang, flag: "🇯🇵", native: "日本語" },
];

export default function WelcomePage() {
  const { lang: contextLang, setLang: setContextLang } = useLang();
  const [lang] = useState<Lang>(contextLang as Lang || "en");
  const [checkingOnboarding, setCheckingOnboarding] = useState(true);
  const router = useRouter();
  const wt = welcomeI18n[lang];

  useEffect(() => {
    // If onboarding is already done, skip this screen entirely.
    (async () => {
      try {
        const resp = await fetch(`${API}/api/welcome`);
        const data = await resp.json();
        if (data.onboarded) {
          router.replace("/dashboard");
          return;
        }
      } catch {
        // Backend unreachable — show welcome screen.
      }
      const keys = Object.keys(localStorage).filter(k => k.startsWith("quantclaw_"));
      for (const key of keys) {
        localStorage.removeItem(key);
      }
      setCheckingOnboarding(false);
    })();
  }, [router]);

  const handleSelectLang = (code: Lang) => {
    setContextLang(code);
    router.push(`/onboarding?lang=${code}`);
  };

  if (checkingOnboarding) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-circuit text-sm font-mono tracking-wider animate-pulse text-glow-circuit">
          {wt.loading.toUpperCase()}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-4 relative overflow-hidden">
      {/* Full-bleed crab background */}
      <div className="absolute inset-0 pointer-events-none flex items-start justify-center">
        <img
          src="/mascot.png"
          alt=""
          className="w-auto max-w-none opacity-40"
          style={{
            height: "85vh",
            marginTop: "-5vh",
            maskImage: "radial-gradient(ellipse 50% 55% at 50% 40%, black 30%, transparent 80%)",
            WebkitMaskImage: "radial-gradient(ellipse 50% 55% at 50% 40%, black 30%, transparent 80%)",
          }}
        />
      </div>
      <div className="absolute inset-0 pointer-events-none" style={{
        background: "linear-gradient(180deg, rgba(5,9,17,0.3) 0%, rgba(5,9,17,0.5) 35%, rgba(5,9,17,0.85) 55%, rgba(5,9,17,0.97) 75%)",
      }} />

      <div className="max-w-4xl w-full relative z-10">
        <div className="text-center mb-10 animate-fade-up" style={{ marginTop: "38vh" }}>
          <h1
            className="text-7xl font-extrabold tracking-tight mb-3"
            style={{ fontFamily: "var(--font-display)" }}
          >
            <span className="text-gold text-glow-gold">Quant</span>
            <span className="text-[#5a6a88]">Claw</span>
          </h1>
          <p className="text-[#3a4e6e] text-base font-light tracking-wide" style={{ fontFamily: "var(--font-body)" }}>
            {wt.subtitle}
          </p>
          <p className="text-circuit-dim text-[10px] mt-2 font-mono tracking-[0.3em] uppercase" style={{ opacity: 0.4 }}>
            {wt.tagline}
          </p>
        </div>

        <div className="flex items-center gap-6 mb-6 animate-fade-up" style={{ animationDelay: "0.1s" }}>
          <div className="flex-1 h-px" style={{ background: "linear-gradient(90deg, transparent, rgba(14,107,128,0.15))" }} />
          <span className="text-[10px] text-[#2a3e5a] font-mono tracking-[0.25em] uppercase">
            {wt.divider}
          </span>
          <div className="flex-1 h-px" style={{ background: "linear-gradient(270deg, transparent, rgba(14,107,128,0.15))" }} />
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-12">
          {LANGUAGES.map((l, i) => (
            <button
              key={l.code}
              onClick={() => handleSelectLang(l.code)}
              className="group p-8 rounded-lg border border-[#0e1e35] bg-[#050911]/70 backdrop-blur-sm text-center transition-all duration-300 animate-scale-in cursor-pointer hover:border-circuit/30 hover:bg-[#0a1020]/80"
              style={{ animationDelay: `${0.15 + i * 0.08}s` }}
            >
              <div className="text-5xl mb-4">{l.flag}</div>
              <h3 className="text-lg font-semibold text-[#4a5e80] group-hover:text-circuit-light transition-colors" style={{ fontFamily: "var(--font-display)" }}>
                {l.native}
              </h3>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
