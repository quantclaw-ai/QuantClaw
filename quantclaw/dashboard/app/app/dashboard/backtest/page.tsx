"use client";
import { useLang } from "../../lang-context";

const translations = {
  en: {
    title: "Backtest",
    heading: "Run your first backtest",
    description: "Select a strategy template and test it against historical data",
    button: "Choose Strategy",
  },
  zh: {
    title: "回测",
    heading: "运行你的第一次回测",
    description: "选择一个策略模板并使用历史数据进行测试",
    button: "选择策略",
  },
  ja: {
    title: "バックテスト",
    heading: "最初のバックテストを実行",
    description: "戦略テンプレートを選択し、過去のデータでテストします",
    button: "戦略を選択",
  },
} as const;

export default function BacktestPage() {
  const { lang } = useLang();
  const t = translations[lang] || translations.en;

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6 text-gold" style={{ fontFamily: "var(--font-display)" }}>{t.title}</h1>
      <div className="card-cyber p-8 text-center text-muted">
        <p className="text-lg mb-2">{t.heading}</p>
        <p className="text-sm mb-4">{t.description}</p>
        <button
          className="px-6 py-2 bg-gold text-void rounded-lg font-semibold hover:bg-gold-light transition-all hover:shadow-lg hover:shadow-gold/20"
          style={{ fontFamily: "var(--font-display)" }}
        >
          {t.button}
        </button>
      </div>
    </div>
  );
}
