"use client";
import { useLang } from "../../lang-context";

const translations = {
  en: {
    title: "Risk Management",
    message: "Risk monitoring available after starting live trading",
  },
  zh: {
    title: "风险管理",
    message: "开始实盘交易后可使用风险监控",
  },
  ja: {
    title: "リスク管理",
    message: "ライブトレード開始後にリスク監視が利用可能になります",
  },
} as const;

export default function RiskPage() {
  const { lang } = useLang();
  const t = translations[lang] || translations.en;

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6 text-claw" style={{ fontFamily: "var(--font-display)" }}>{t.title}</h1>
      <div className="card-cyber p-8 text-center text-muted">
        <p>{t.message}</p>
      </div>
    </div>
  );
}
