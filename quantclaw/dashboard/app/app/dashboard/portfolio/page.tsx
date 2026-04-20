"use client";
import { useLang } from "../../lang-context";

const translations = {
  en: {
    title: "Portfolio",
    noPositions: "No active positions",
    hint: "Start paper trading to see your portfolio here",
  },
  zh: {
    title: "投资组合",
    noPositions: "暂无持仓",
    hint: "开始模拟交易以在此处查看您的投资组合",
  },
  ja: {
    title: "ポートフォリオ",
    noPositions: "アクティブなポジションはありません",
    hint: "ペーパートレードを開始して、ここでポートフォリオを確認しましょう",
  },
} as const;

export default function PortfolioPage() {
  const { lang } = useLang();
  const t = translations[lang] || translations.en;

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6 text-gold" style={{ fontFamily: "var(--font-display)" }}>{t.title}</h1>
      <div className="card-cyber p-8 text-center text-muted">
        <p className="text-lg mb-2">{t.noPositions}</p>
        <p className="text-sm">{t.hint}</p>
      </div>
    </div>
  );
}
