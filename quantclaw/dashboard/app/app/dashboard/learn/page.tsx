"use client";
import { useState } from "react";
import { useLang } from "../../lang-context";

interface TopicTranslation {
  title: string;
  level: string;
  description: string;
  content?: {
    sections: Array<{
      heading: string;
      text: string;
    }>;
    keyPoints: string[];
  };
}

const topicsTranslations: Record<string, { en: TopicTranslation; zh: TopicTranslation; ja: TopicTranslation }> = {
  stock: {
    en: {
      title: "What is a Stock?",
      level: "Observer",
      description: "Understanding equities, shares, and market basics",
      content: {
        sections: [
          {
            heading: "Definition",
            text: "A stock represents fractional ownership in a company. When you buy stock, you become a shareholder with a claim on the company's assets and earnings.",
          },
          {
            heading: "How Stocks Work",
            text: "Companies issue stocks to raise capital. Stockholders profit through dividend payments and stock price appreciation. Stock price reflects market sentiment about the company's future earnings potential.",
          },
          {
            heading: "Market Mechanics",
            text: "Stocks trade on exchanges (NYSE, NASDAQ, etc.) where buyers and sellers meet. Prices fluctuate based on supply and demand, company performance, economic conditions, and investor sentiment.",
          },
        ],
        keyPoints: [
          "Stocks = fractional company ownership",
          "Shareholders have claims on profits and assets",
          "Prices driven by earnings expectations and market sentiment",
          "Dividends provide income, price appreciation provides capital gains",
        ],
      },
    },
    zh: {
      title: "什么是股票？",
      level: "观察者",
      description: "了解股权、股份和市场基础知识",
      content: {
        sections: [
          {
            heading: "定义",
            text: "股票代表对公司的部分所有权。购买股票时，您成为股东，对公司的资产和收益有主张权。",
          },
          {
            heading: "股票如何运作",
            text: "公司发行股票以筹集资本。股东通过股息支付和股价升值获利。股价反映市场对公司未来收益潜力的预期。",
          },
          {
            heading: "市场机制",
            text: "股票在交易所交易，买卖双方在此相遇。价格根据供求关系、公司业绩、经济状况和投资者情绪波动。",
          },
        ],
        keyPoints: [
          "股票 = 部分公司所有权",
          "股东对利润和资产有主张权",
          "价格由收益预期和市场情绪驱动",
          "股息提供收入，股价升值提供资本收益",
        ],
      },
    },
    ja: {
      title: "株式とは？",
      level: "オブザーバー",
      description: "株式、シェア、市場の基礎を理解する",
      content: {
        sections: [
          {
            heading: "定義",
            text: "株式は企業の部分的な所有権を表します。株式を購入すると、企業の資産と収益に対する請求権を持つ株主になります。",
          },
          {
            heading: "株式の仕組み",
            text: "企業は資本を調達するために株式を発行します。株主は配当金と株価上昇により利益を得ます。株価は企業の将来の収益潜在力に対する市場心理を反映します。",
          },
          {
            heading: "市場メカニズム",
            text: "株式は取引所で取引され、買い手と売り手が出会います。価格は供給と需要、企業業績、経済状況、投資家心理に基づいて変動します。",
          },
        ],
        keyPoints: [
          "株式 = 企業の部分的所有権",
          "株主は利益と資産に対する請求権を持つ",
          "価格は収益予想と市場心理により駆動される",
          "配当金は収入、株価上昇は資本利得を提供",
        ],
      },
    },
  },
  backtesting: {
    en: {
      title: "What is Backtesting?",
      level: "Paper Trader",
      description: "Testing strategies on historical data",
      content: {
        sections: [
          {
            heading: "Core Concept",
            text: "Backtesting simulates trading strategy performance using historical market data. It shows how your strategy would have performed in the past, helping validate ideas before risking real capital.",
          },
          {
            heading: "The Process",
            text: "You define entry/exit rules, apply them to historical price data, and track P&L. The backtest engine replays market conditions exactly as they occurred, generating performance metrics.",
          },
          {
            heading: "Critical Considerations",
            text: "Past performance doesn't guarantee future results. Watch for overfitting (optimizing parameters to historical data), look-ahead bias (using future information), and slippage (execution costs that reduce returns).",
          },
        ],
        keyPoints: [
          "Simulate strategy on historical data before live trading",
          "Validate ideas with quantifiable metrics",
          "Avoid overfitting and look-ahead bias",
          "Account for realistic costs and execution delays",
        ],
      },
    },
    zh: {
      title: "什么是回测？",
      level: "模拟交易者",
      description: "在历史数据上测试策略",
      content: {
        sections: [
          {
            heading: "核心概念",
            text: "回测使用历史市场数据模拟交易策略的表现。它显示您的策略在过去的表现如何，帮助在使用真实资本之前验证想法。",
          },
          {
            heading: "过程",
            text: "您定义进出场规则，将它们应用于历史价格数据，并跟踪损益。回测引擎完全按照之前发生的方式重放市场条件，生成性能指标。",
          },
          {
            heading: "关键考虑",
            text: "过去的表现不能保证未来的结果。注意过拟合（将参数优化为历史数据）、前视偏差（使用未来信息）和滑点（降低回报的执行成本）。",
          },
        ],
        keyPoints: [
          "在实盘交易前在历史数据上模拟策略",
          "用可量化的指标验证想法",
          "避免过拟合和前视偏差",
          "考虑现实的成本和执行延迟",
        ],
      },
    },
    ja: {
      title: "バックテストとは？",
      level: "ペーパートレーダー",
      description: "過去のデータで戦略をテストする",
      content: {
        sections: [
          {
            heading: "コアコンセプト",
            text: "バックテストは歴史的な市場データを使用して取引戦略のパフォーマンスをシミュレートします。実資本でリスクを取る前に、戦略の検証に役立ちます。",
          },
          {
            heading: "プロセス",
            text: "エントリー/エグジットルールを定義し、履歴価格データに適用して、P&Lを追跡します。バックテストエンジンは市場条件を正確に再生し、パフォーマンスメトリクスを生成します。",
          },
          {
            heading: "重要な考慮事項",
            text: "過去のパフォーマンスは将来の結果を保証しません。オーバーフィッティング、ルックアヘッドバイアス、スリッページに注意してください。",
          },
        ],
        keyPoints: [
          "ライブトレード前に過去データで戦略をシミュレート",
          "定量的なメトリクスでアイデアを検証",
          "オーバーフィッティングとルックアヘッドバイアスを回避",
          "現実的なコストと実行遅延を考慮",
        ],
      },
    },
  },
  sharpe: {
    en: {
      title: "Sharpe Ratio Explained",
      level: "Paper Trader",
      description: "Measuring risk-adjusted returns",
      content: {
        sections: [
          {
            heading: "Definition",
            text: "The Sharpe Ratio measures excess return per unit of risk. It's calculated as (Return - Risk-Free Rate) / Standard Deviation. A higher ratio indicates better risk-adjusted performance.",
          },
          {
            heading: "Why It Matters",
            text: "Two strategies might have the same total return, but one could achieve it with much higher volatility. The Sharpe Ratio reveals which strategy is more efficient at generating returns relative to the risk taken.",
          },
          {
            heading: "Interpretation",
            text: "A Sharpe Ratio above 1.0 is generally considered good, above 2.0 excellent. However, context matters—compare strategies within the same asset class and market regime.",
          },
        ],
        keyPoints: [
          "Measures return per unit of risk taken",
          "Higher ratio = better risk-adjusted performance",
          "Sharpe > 1.0 is generally good",
          "Compare strategies in similar contexts",
        ],
      },
    },
    zh: {
      title: "夏普比率详解",
      level: "模拟交易者",
      description: "衡量风险调整后的收益",
      content: {
        sections: [
          {
            heading: "定义",
            text: "夏普比率衡量每单位风险的超额回报。计算公式为（回报 - 无风险利率）/ 标准差。比率越高，风险调整后的表现越好。",
          },
          {
            heading: "重要意义",
            text: "两个策略可能有相同的总回报，但一个可能通过更高的波动性来实现。夏普比率揭示哪个策略在相对于所承担风险的情况下更有效地生成回报。",
          },
          {
            heading: "解释",
            text: "夏普比率高于1.0通常被认为是好的，高于2.0是优秀的。但是，上下文很重要——在同一资产类别和市场制度中比较策略。",
          },
        ],
        keyPoints: [
          "衡量每单位风险承担的回报",
          "比率越高 = 风险调整后的表现越好",
          "夏普比率 > 1.0 通常是好的",
          "在相似的背景下比较策略",
        ],
      },
    },
    ja: {
      title: "シャープレシオの解説",
      level: "ペーパートレーダー",
      description: "リスク調整後リターンの測定",
      content: {
        sections: [
          {
            heading: "定義",
            text: "シャープレシオは単位リスクあたりの超過リターンを測定します。（リターン - リスクフリーレート）/ 標準偏差として計算されます。比率が高いほど、リスク調整後のパフォーマンスが向上します。",
          },
          {
            heading: "重要性",
            text: "2つの戦略は同じ総リターンを持つかもしれませんが、1つはより高いボラティリティで達成する可能性があります。シャープレシオは、取られたリスクに対する相対的なリターンでより効率的な戦略を明らかにします。",
          },
          {
            heading: "解釈",
            text: "シャープレシオが1.0を超えることは一般的に良好と見なされ、2.0を超えることは優秀です。ただし、文脈が重要です。",
          },
        ],
        keyPoints: [
          "リスク単位あたりのリターンを測定",
          "比率が高い = リスク調整後のパフォーマンスが向上",
          "シャープレシオ > 1.0 は一般的に良好",
          "同様の文脈で戦略を比較",
        ],
      },
    },
  },
  drawdown: {
    en: {
      title: "What is Drawdown?",
      level: "Paper Trader",
      description: "Understanding worst-case losses",
      content: {
        sections: [
          {
            heading: "Definition",
            text: "Drawdown is the decline from a peak to a trough in cumulative returns. Maximum Drawdown (MDD) measures the largest peak-to-trough decline during a period, representing worst-case loss.",
          },
          {
            heading: "Why It Matters",
            text: "While average returns tell you expected performance, drawdowns reveal the pain of bad periods. A strategy with high returns but severe drawdowns might be psychologically unbearable in practice.",
          },
          {
            heading: "Risk Management",
            text: "Professional traders obsess over drawdown limits. Knowing you can tolerate (or cannot tolerate) a 30% loss is crucial for position sizing and strategy selection.",
          },
        ],
        keyPoints: [
          "Drawdown = peak-to-trough decline in returns",
          "Maximum Drawdown shows worst case scenario",
          "Reveals psychological stress of the strategy",
          "Critical for position sizing and risk limits",
        ],
      },
    },
    zh: {
      title: "什么是回撤？",
      level: "模拟交易者",
      description: "了解最大亏损情况",
      content: {
        sections: [
          {
            heading: "定义",
            text: "回撤是从累积回报中的峰值到谷值的下降。最大回撤（MDD）测量期间内从峰值到谷值的最大下降，代表最坏情况下的亏损。",
          },
          {
            heading: "重要意义",
            text: "虽然平均回报告诉您预期的表现，但回撤揭示了坏时期的痛苦。一个高回报但严重回撤的策略在实践中可能在心理上无法承受。",
          },
          {
            heading: "风险管理",
            text: "专业交易者痴迷于回撤限制。知道您能否承受30%的亏损对于头寸规模和策略选择至关重要。",
          },
        ],
        keyPoints: [
          "回撤 = 回报中的峰值到谷值下降",
          "最大回撤显示最坏情况场景",
          "揭示策略的心理压力",
          "对头寸规模和风险限制至关重要",
        ],
      },
    },
    ja: {
      title: "ドローダウンとは？",
      level: "ペーパートレーダー",
      description: "最悪の損失を理解する",
      content: {
        sections: [
          {
            heading: "定義",
            text: "ドローダウンは累積リターンのピークからトラフへの低下です。最大ドローダウン（MDD）は期間中の最大ピークからトラフへの低下を測定し、最悪の場合の損失を表します。",
          },
          {
            heading: "重要性",
            text: "平均リターンは予想されるパフォーマンスを示しますが、ドローダウンは悪い期間の痛みを明らかにします。高リターンだが深刻なドローダウンを持つ戦略は、実際には心理的に耐えられないかもしれません。",
          },
          {
            heading: "リスク管理",
            text: "プロの取引業者はドローダウン制限に夢中です。30%の損失を耐えられるかどうか知ることは、ポジションサイジングと戦略選択に不可欠です。",
          },
        ],
        keyPoints: [
          "ドローダウン = リターンのピークからトラフへの低下",
          "最大ドローダウンが最悪のシナリオを示す",
          "戦略の心理的ストレスを明らかにする",
          "ポジションサイジングとリスク制限に不可欠",
        ],
      },
    },
  },
  overfitting: {
    en: {
      title: "Overfitting",
      level: "Tinkerer",
      description: "Why strategies fail in live trading",
      content: {
        sections: [
          {
            heading: "The Problem",
            text: "Overfitting occurs when you optimize strategy parameters too closely to historical data, capturing noise instead of real patterns. The strategy works perfectly on backtests but fails in live markets.",
          },
          {
            heading: "How It Happens",
            text: "With unlimited parameter choices and hindsight, you can make any backtest look good. The more parameters you tweak, the higher the probability of accidental curve-fitting rather than discovering genuine edge.",
          },
          {
            heading: "Prevention",
            text: "Use out-of-sample testing (hold back recent data), implement strict parameter limits, test on multiple market regimes, and demand simplicity—if a strategy requires 20 parameters, it's probably overfit.",
          },
        ],
        keyPoints: [
          "Strategy performs great in backtest but fails live",
          "Optimizing to noise instead of real patterns",
          "More parameters = higher overfitting risk",
          "Use out-of-sample testing and demand simplicity",
        ],
      },
    },
    zh: {
      title: "过拟合",
      level: "探索者",
      description: "策略在实盘交易中失败的原因",
      content: {
        sections: [
          {
            heading: "问题",
            text: "过拟合发生在您过于紧密地优化历史数据的策略参数时，捕获噪音而不是真实模式。该策略在回测中完美运行，但在实际市场中失败。",
          },
          {
            heading: "发生方式",
            text: "有无限的参数选择和后见之明，您可以使任何回测看起来都很好。您调整的参数越多，发生意外曲线拟合而不是发现真正优势的概率就越高。",
          },
          {
            heading: "预防",
            text: "使用样本外测试（保留最近数据），实施严格的参数限制，在多个市场制度上测试，并要求简单性——如果策略需要20个参数，它可能是过拟合的。",
          },
        ],
        keyPoints: [
          "策略在回测中表现完美但在实盘中失败",
          "优化噪音而不是真实模式",
          "参数越多 = 过拟合风险越高",
          "使用样本外测试并要求简单性",
        ],
      },
    },
    ja: {
      title: "オーバーフィッティング",
      level: "ティンカラー",
      description: "実取引で戦略が失敗する理由",
      content: {
        sections: [
          {
            heading: "問題",
            text: "オーバーフィッティングは、戦略パラメータを履歴データに過度に最適化し、実際のパターンではなくノイズをキャプチャする場合に発生します。",
          },
          {
            heading: "発生方法",
            text: "無限のパラメータ選択と事後知識があれば、あらゆるバックテストを見栄えよくすることができます。調整するパラメータが多いほど、偶発的な曲線フィッティングが発生する確率が高くなります。",
          },
          {
            heading: "予防",
            text: "サンプル外テスト（最近のデータを保持）を使用し、厳密なパラメータ制限を実装し、複数の市場制度でテストを実行します。",
          },
        ],
        keyPoints: [
          "バックテストでは完璧だが、実取引では失敗",
          "実際のパターンではなくノイズを最適化",
          "パラメータが多い = オーバーフィッティングのリスクが高い",
          "サンプル外テストと単純性を要求",
        ],
      },
    },
  },
  lookahead: {
    en: {
      title: "Look-Ahead Bias",
      level: "Tinkerer",
      description: "The most dangerous backtest mistake",
      content: {
        sections: [
          {
            heading: "Definition",
            text: "Look-ahead bias occurs when your backtest uses information that wouldn't be available at decision time. For example, using today's high to set entry prices for today's trades, when you wouldn't know the high until market close.",
          },
          {
            heading: "Why It's Dangerous",
            text: "Look-ahead bias creates the illusion of profitability. Your backtest looks fantastic, but the strategy is fundamentally impossible to execute because it depends on future information. Live trading reveals the disaster immediately.",
          },
          {
            heading: "How to Avoid It",
            text: "Be meticulous about data alignment: use only information available at decision time, shift data properly, test with realistic order execution delays, and audit your code carefully.",
          },
        ],
        keyPoints: [
          "Using future information in backtests",
          "Creates false profitability illusions",
          "Fundamental execution impossibility",
          "Audit data alignment and timing carefully",
        ],
      },
    },
    zh: {
      title: "前视偏差",
      level: "探索者",
      description: "回测中最危险的错误",
      content: {
        sections: [
          {
            heading: "定义",
            text: "前视偏差发生在您的回测使用决策时不可用的信息时。例如，使用今天的最高价格为今天的交易设置进场价格，而您在市场收盘前不会知道最高价。",
          },
          {
            heading: "为什么它很危险",
            text: "前视偏差创造了盈利的假象。您的回测看起来很棒，但该策略从根本上是不可能执行的，因为它依赖于未来信息。实盘交易立即揭示了灾难。",
          },
          {
            heading: "如何避免",
            text: "对数据对齐要精益求精：仅使用决策时可用的信息，正确移动数据，使用现实的订单执行延迟进行测试，并仔细审计您的代码。",
          },
        ],
        keyPoints: [
          "在回测中使用未来信息",
          "产生虚假盈利幻想",
          "根本上的执行不可能性",
          "仔细审计数据对齐和时序",
        ],
      },
    },
    ja: {
      title: "先読みバイアス",
      level: "ティンカラー",
      description: "バックテストで最も危険な間違い",
      content: {
        sections: [
          {
            heading: "定義",
            text: "先読みバイアスは、バックテストが意思決定時に利用できない情報を使用する場合に発生します。",
          },
          {
            heading: "危険な理由",
            text: "先読みバイアスは収益性の幻想を作成します。バックテストは素晴らしく見えますが、戦略は根本的に実行不可能です。実取引はすぐに災害を明かします。",
          },
          {
            heading: "避ける方法",
            text: "データアラインメントについて厳密になってください：決定時に利用可能な情報のみを使用し、データを適切に転換し、現実的な注文執行遅延でテストを実行します。",
          },
        ],
        keyPoints: [
          "バックテストで未来情報を使用",
          "収益性の幻想を作成",
          "根本的な実行不可能性",
          "データアラインメントとタイミングを注意深く監査",
        ],
      },
    },
  },
  factor: {
    en: {
      title: "Factor Investing",
      level: "Strategist",
      description: "Value, momentum, quality, and low-vol",
      content: {
        sections: [
          {
            heading: "Core Idea",
            text: "Rather than picking individual stocks, factor investing selects stocks based on characteristics (factors) that historically outperform. Key factors include Value (cheap stocks), Momentum (trending stocks), Quality (profitable companies), and Low Volatility (stable stocks).",
          },
          {
            heading: "Combining Factors",
            text: "Individual factors have periods of underperformance. By combining multiple factors, you reduce drawdowns and smooth returns. A portfolio might score high on Value and Quality, lowering volatility while maintaining edge.",
          },
          {
            heading: "Implementation",
            text: "Build a scoring system that rates stocks across factors, then hold the highest-scoring equities. Rebalance periodically (monthly, quarterly) to maintain factor exposures and avoid drift.",
          },
        ],
        keyPoints: [
          "Select stocks by characteristics (factors), not individual picks",
          "Historical outperformance: Value, Momentum, Quality, Low-Vol",
          "Combine factors to reduce drawdowns",
          "Systematic rebalancing maintains edge",
        ],
      },
    },
    zh: {
      title: "因子投资",
      level: "策略师",
      description: "价值、动量、质量和低波动",
      content: {
        sections: [
          {
            heading: "核心想法",
            text: "因子投资不是选择个别股票，而是根据历史上表现超群的特征（因子）来选择股票。关键因子包括价值（便宜股票）、动量（趋势股票）、质量（盈利公司）和低波动（稳定股票）。",
          },
          {
            heading: "结合因子",
            text: "个别因子有表现不足的时期。通过结合多个因子，您可以减少回撤并平滑回报。投资组合可能在价值和质量上得分很高，在保持优势的同时降低波动率。",
          },
          {
            heading: "实施",
            text: "建立一个评分系统，在因子上评估股票，然后持有得分最高的股票。定期重新平衡（月度、季度）以保持因子敞口并避免偏离。",
          },
        ],
        keyPoints: [
          "根据特征（因子）选择股票，而不是个别选择",
          "历史表现超群：价值、动量、质量、低波动",
          "结合因子以减少回撤",
          "系统性重新平衡保持优势",
        ],
      },
    },
    ja: {
      title: "ファクター投資",
      level: "ストラテジスト",
      description: "バリュー、モメンタム、クオリティ、低ボラティリティ",
      content: {
        sections: [
          {
            heading: "中心概念",
            text: "個別株を選択する代わりに、ファクター投資は歴史的に高いパフォーマンスを持つ特性（ファクター）に基づいて株を選択します。",
          },
          {
            heading: "ファクターの結合",
            text: "個々のファクターはアンダーパフォーマンスの時期があります。複数のファクターを結合することで、ドローダウンを減らし、リターンを平滑化します。",
          },
          {
            heading: "実装",
            text: "ファクター全体で株を評価するスコアリングシステムを構築し、スコアが最も高い株を保有します。定期的にリバランスしてファクターエクスポージャーを維持します。",
          },
        ],
        keyPoints: [
          "個別選択ではなくファクターによって株を選択",
          "歴史的パフォーマンス：バリュー、モメンタム、クオリティ、低ボラティリティ",
          "ファクターを結合してドローダウンを削減",
          "系統的なリバランスがエッジを維持",
        ],
      },
    },
  },
  ml: {
    en: {
      title: "Machine Learning for Finance",
      level: "Quant",
      description: "Using ML to predict returns",
      content: {
        sections: [
          {
            heading: "The Promise",
            text: "Machine learning can discover complex, non-linear relationships in market data that traditional models miss. It can integrate hundreds of features (price, volume, sentiment, fundamentals) into a predictive system.",
          },
          {
            heading: "The Reality",
            text: "Markets are adaptive. As more traders use the same ML signals, the edge decays. Data leakage is rampant (your model sees tomorrow's data today). Overfitting is the primary risk. Many 'ML' strategies are just sophisticated curve-fitting on noise.",
          },
          {
            heading: "Best Practices",
            text: "Use walk-forward validation (train on old data, test on new), hold back data for final testing, monitor model performance in live markets, and accept that your model's edge is temporary and requires continuous updating.",
          },
        ],
        keyPoints: [
          "ML discovers non-linear patterns humans miss",
          "Can integrate hundreds of features",
          "Edge decays as more traders use the signal",
          "Overfitting and data leakage are primary risks",
        ],
      },
    },
    zh: {
      title: "金融中的机器学习",
      level: "量化分析师",
      description: "使用机器学习预测收益",
      content: {
        sections: [
          {
            heading: "承诺",
            text: "机器学习可以发现传统模型遗漏的市场数据中的复杂、非线性关系。它可以将数百个特征（价格、成交量、情绪、基本面）整合到预测系统中。",
          },
          {
            heading: "现实",
            text: "市场是自适应的。当更多交易者使用相同的机器学习信号时，边界衰退。数据泄漏很普遍。过拟合是主要风险。许多'机器学习'策略只是对噪音的复杂曲线拟合。",
          },
          {
            heading: "最佳实践",
            text: "使用前进式验证（在旧数据上训练，在新数据上测试），保留数据进行最终测试，监控模型在实际市场中的表现，并接受模型的优势是暂时的，需要持续更新。",
          },
        ],
        keyPoints: [
          "机器学习发现人类遗漏的非线性模式",
          "可以整合数百个特征",
          "随着更多交易者使用信号，边界衰退",
          "过拟合和数据泄漏是主要风险",
        ],
      },
    },
    ja: {
      title: "金融のための機械学習",
      level: "クオンツ",
      description: "MLを使ったリターン予測",
      content: {
        sections: [
          {
            heading: "約束",
            text: "機械学習は、従来のモデルが逃した市場データ内の複雑で非線形の関係を発見できます。数百の機能を予測システムに統合できます。",
          },
          {
            heading: "現実",
            text: "市場は適応的です。より多くのトレーダーが同じMLシグナルを使用すると、エッジは減少します。データリークが蔓延しています。オーバーフィッティングが主なリスクです。",
          },
          {
            heading: "ベストプラクティス",
            text: "ウォークフォワード検証を使用し、最終テスト用にデータを保持し、実市場でモデルのパフォーマンスを監視し、モデルのエッジが一時的で継続的な更新が必要であることを受け入れます。",
          },
        ],
        keyPoints: [
          "MLは人間が逃した非線形パターンを発見",
          "数百の機能を統合可能",
          "より多くのトレーダーがシグナルを使用するとエッジが減少",
          "オーバーフィッティングとデータリークが主なリスク",
        ],
      },
    },
  },
  portfolio: {
    en: {
      title: "Portfolio Construction",
      level: "Architect",
      description: "Combining strategies for optimal risk",
      content: {
        sections: [
          {
            heading: "Diversification",
            text: "A single strategy carries concentration risk. By combining uncorrelated strategies, you smooth returns and reduce drawdowns. Two strategies with 50% Sharpe each become something better when combined.",
          },
          {
            heading: "Allocation Strategy",
            text: "Don't allocate equally to all strategies. Use historical correlation and Sharpe ratios to optimize weights. Strategies with higher Sharpe get larger allocations. Negative correlations are gold—they provide hedges.",
          },
          {
            heading: "Rebalancing",
            text: "Allocations drift over time. Set rebalancing frequencies (monthly, quarterly) and thresholds (rebalance if any position drifts >5% from target). Rebalancing locks in gains and maintains risk discipline.",
          },
        ],
        keyPoints: [
          "Combine uncorrelated strategies to reduce risk",
          "Allocate proportional to Sharpe ratio",
          "Negative correlations provide hedges",
          "Regular rebalancing maintains target risk",
        ],
      },
    },
    zh: {
      title: "投资组合构建",
      level: "架构师",
      description: "组合策略以优化风险",
      content: {
        sections: [
          {
            heading: "多样化",
            text: "单一策略承担集中风险。通过结合不相关的策略，您可以平滑回报并减少回撤。两个各有50% 夏普比率的策略相结合时会变成更好的东西。",
          },
          {
            heading: "配置策略",
            text: "不要平均分配给所有策略。使用历史相关性和夏普比率来优化权重。夏普比率较高的策略获得更大的配置。负相关性很宝贵——它们提供对冲。",
          },
          {
            heading: "重新平衡",
            text: "配置随时间推移而漂移。设置重新平衡频率（月度、季度）和阈值（如果任何头寸偏离目标 >5%，则重新平衡）。重新平衡锁定收益并维持风险纪律。",
          },
        ],
        keyPoints: [
          "组合不相关的策略以降低风险",
          "按夏普比率比例分配",
          "负相关性提供对冲",
          "定期重新平衡维持目标风险",
        ],
      },
    },
    ja: {
      title: "ポートフォリオ構築",
      level: "アーキテクト",
      description: "最適なリスクのための戦略の組み合わせ",
      content: {
        sections: [
          {
            heading: "多様化",
            text: "単一の戦略は集中リスクを負います。相関しない戦略を組み合わせることで、リターンを平滑化し、ドローダウンを減らします。",
          },
          {
            heading: "配置戦略",
            text: "すべての戦略に均等に配置しないでください。歴史的相関とシャープレシオを使用してウェイトを最適化します。シャープレシオが高い戦略はより大きな配置を取得します。負の相関はゴールドです。",
          },
          {
            heading: "リバランス",
            text: "配置は時間とともに漂流します。リバランス頻度（月次、四半期）としきい値を設定します。定期的なリバランスはゲインをロックし、リスク規律を維持します。",
          },
        ],
        keyPoints: [
          "相関しない戦略を組み合わせてリスクを削減",
          "シャープレシオに比例して配置",
          "負の相関はヘッジを提供",
          "定期的なリバランスがターゲットリスクを維持",
        ],
      },
    },
  },
};

const topicKeys = ["stock", "backtesting", "sharpe", "drawdown", "overfitting", "lookahead", "factor", "ml", "portfolio"] as const;

const pageTitleTranslations = {
  en: "Learn Quant Trading",
  zh: "学习量化交易",
  ja: "クオンツトレーディングを学ぶ",
} as const;

function ContentModal({
  topic,
  onClose,
}: {
  topic: TopicTranslation;
  onClose: () => void;
}) {
  if (!topic.content) return null;

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div
        className="bg-[#0a1628] border border-cyan-400/30 rounded-lg max-w-3xl w-full max-h-[85vh] overflow-y-auto relative"
        onClick={(e) => e.stopPropagation()}
        style={{
          boxShadow: "0 0 30px rgba(34, 211, 238, 0.2), inset 0 0 20px rgba(34, 211, 238, 0.05)",
        }}
      >
        {/* Animated background glow */}
        <div className="absolute inset-0 opacity-0 pointer-events-none" />

        {/* Header */}
        <div className="sticky top-0 bg-gradient-to-b from-[#0a1628] to-[#0a1628]/80 border-b border-cyan-400/20 p-6 backdrop-blur-sm">
          <div className="flex items-start justify-between">
            <div>
              <h2 className="text-3xl font-bold text-cyan-300 mb-2" style={{ fontFamily: "var(--font-display)" }}>
                {topic.title}
              </h2>
              <p className="text-cyan-400/60 text-sm">{topic.level}</p>
            </div>
            <button
              onClick={onClose}
              className="text-cyan-400/60 hover:text-cyan-300 transition-colors p-2 hover:bg-cyan-400/10 rounded"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 space-y-8">
          {topic.content.sections.map((section, idx) => (
            <div key={idx} className="space-y-3">
              <h3 className="text-lg font-semibold text-cyan-300">{section.heading}</h3>
              <p className="text-gray-300 leading-relaxed text-sm">{section.text}</p>
            </div>
          ))}

          {/* Key Points */}
          <div className="border-t border-cyan-400/20 pt-6 mt-8">
            <h3 className="text-lg font-semibold text-cyan-300 mb-4">Key Points</h3>
            <ul className="space-y-2">
              {topic.content.keyPoints.map((point, idx) => (
                <li key={idx} className="flex gap-3 text-gray-300 text-sm">
                  <span className="text-cyan-400 flex-shrink-0">→</span>
                  <span>{point}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function LearnPage() {
  const { lang } = useLang();
  const [selectedTopic, setSelectedTopic] = useState<string | null>(null);
  const pageTitle = pageTitleTranslations[lang] || pageTitleTranslations.en;

  const selectedTopicData = selectedTopic
    ? topicsTranslations[selectedTopic as keyof typeof topicsTranslations][lang] ||
      topicsTranslations[selectedTopic as keyof typeof topicsTranslations].en
    : null;

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6 text-cyan-300" style={{ fontFamily: "var(--font-display)" }}>
        {pageTitle}
      </h1>
      <div className="space-y-3">
        {topicKeys.map((key, i) => {
          const topic = topicsTranslations[key][lang] || topicsTranslations[key].en;
          return (
            <div
              key={i}
              onClick={() => setSelectedTopic(key)}
              className="group card-cyber p-4 hover:border-cyan-400/60 cursor-pointer transition-all duration-300 relative overflow-hidden"
              style={{
                boxShadow: "inset 0 0 15px rgba(34, 211, 238, 0.03)",
              }}
            >
              {/* Hover glow effect */}
              <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none"
                style={{
                  background: "radial-gradient(circle at center, rgba(34, 211, 238, 0.1) 0%, transparent 70%)",
                }}
              />

              <div className="flex items-center justify-between relative z-10">
                <div>
                  <p className="font-medium text-cyan-300 group-hover:text-cyan-200 transition-colors">{topic.title}</p>
                  <p className="text-sm text-gray-400 group-hover:text-gray-300 transition-colors">{topic.description}</p>
                </div>
                <span className="text-xs text-cyan-400 font-mono bg-cyan-400/10 px-2 py-1 rounded border border-cyan-400/20 group-hover:border-cyan-400/40 group-hover:bg-cyan-400/20 transition-all">
                  {topic.level}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Modal */}
      {selectedTopic && selectedTopicData && (
        <ContentModal topic={selectedTopicData} onClose={() => setSelectedTopic(null)} />
      )}
    </div>
  );
}
