type Lang = "en" | "zh" | "ja";

interface Translations {
  // Step labels
  steps: {
    language: string;
    model: string;
    search: string;
    data: string;
    broker: string;
    watchlist: string;
    notifications: string;
    launch: string;
  };

  // Step headers
  languageStep: { title: string; subtitle: string };
  llmStep: { title: string; subtitle: string };
  searchStep: { title: string; subtitle: string };
  dataStep: { title: string; subtitle: string };
  brokerStep: { title: string; subtitle: string };
  watchlistStep: { title: string; subtitle: string };
  notificationStep: { title: string; subtitle: string };
  launchStep: { title: string; subtitle: string };

  // Data categories
  dataCategories: Record<string, string>;

  // Provider descriptions (keyed by id)
  llmDescriptions: Record<string, string>;
  searchDescriptions: Record<string, string>;
  dataDescriptions: Record<string, string>;

  // StepHeader
  stepPrefix: string;

  // Pairing
  pairWithBrowser: string;
  paired: string;
  orEnterKey: string;

  // Common UI
  apiKey: string;
  apiKeyOptional: string;
  storedLocally: string;
  skipForNow: string;
  skipUseDuckDuckGo: string;
  noKeyRequired: string;
  fallbackNote: string;
  autoUpgradeNote: string;
  sourcesEnabled: string;
  free: string;
  back: string;
  continue_: string;
  launchButton: string;
  initializingAgents: string;
  youreLive: string;
  redirecting: string;
  configured: string;
  skipped: string;
  ready: string;
  optional: string;
  saving: string;
  addCustomTicker: string;
  add: string;
  tickersSelected: string;
  changeAnytime: string;
  telegramBotToken: string;
  telegramChatId: string;
  webhookUrl: string;
  notificationLocalNote: string;
  notificationTelegramBoth: string;
  notificationSaveFailed: string;
  noNotifications: string;

  // Review labels
  reviewLanguage: string;
  reviewModel: string;
  reviewSearch: string;
  reviewData: string;
  reviewBroker: string;
  reviewWatchlist: string;
  reviewNotifications: string;

  // Broker options
  paperTrading: string;
  paperTradingDesc: string;
  alpacaDesc: string;
  ibkrDesc: string;
  secretKey: string;

  // Tags
  recommended: string;
  fast: string;
  local: string;
  selfHosted: string;
  pro: string;

  // Presets
  presetMag7: string;
  presetIndexETFs: string;
  presetBlueChips: string;
}

const translations: Record<Lang, Translations> = {
  en: {
    steps: { language: "Language", model: "Model", search: "Search", data: "Data", broker: "Broker", watchlist: "Watchlist", notifications: "Alerts", launch: "Launch" },
    languageStep: { title: "Choose your language", subtitle: "Select your preferred language for the QuantClaw interface and agent responses." },
    llmStep: { title: "Choose a model provider", subtitle: "QuantClaw uses LLMs to power its 13 trading agents. Select your provider." },
    searchStep: { title: "Search provider", subtitle: "Agents use web search for market research, news analysis, and real-time information gathering." },
    dataStep: { title: "Market data sources", subtitle: "All free sources are enabled by default. Add API keys for premium providers to unlock higher rate limits — QuantClaw will automatically route to the fastest available source." },
    brokerStep: { title: "Connect a broker", subtitle: "Start with paper trading to test strategies risk-free, or connect a live broker." },
    watchlistStep: { title: "Build your watchlist", subtitle: "Select the tickers you want QuantClaw to monitor and trade." },
    notificationStep: { title: "Alert destinations", subtitle: "Optionally connect Telegram, Discord, or Slack for urgent QuantClaw events." },
    launchStep: { title: "Ready to launch", subtitle: "Review your configuration and start QuantClaw." },
    dataCategories: { all_markets: "All Markets", stocks: "Stocks & ETFs", crypto: "Crypto", forex: "Forex", commodities: "Commodities", economic: "Economic Data", alternative: "Alternative & Sentiment", cn_stocks: "A-Shares", cn_futures: "Futures & Commodities", cn_economic: "Economic Data" },
    llmDescriptions: {
      llm_ollama: "Run models locally — Llama, Qwen, Mistral, etc. No API key needed",
      llm_openai: "GPT-4o, o1, o3 — strong reasoning and code generation",
      llm_anthropic: "Claude Opus, Sonnet, Haiku — best overall agent performance",
      llm_google: "Gemini 2.5 Pro/Flash — large context and multimodal",
      llm_deepseek: "DeepSeek V3/R1 — high performance, cost-effective",
      llm_xai: "Grok models — real-time knowledge, X/Twitter integration",
      llm_mistral: "Mistral Large/Medium — strong European provider",
      llm_groq: "LPU inference — ultra-fast response times",
      llm_openrouter: "Unified access to 200+ models from all providers",
      llm_together: "Open-source models with fast inference",
      llm_deepseek_cn: "DeepSeek V4/R1 — 5M free tokens on signup, OpenAI-compatible API",
      llm_qwen: "Qwen3.5 397B — largest Chinese open model family, free chat app",
      llm_doubao: "Seed 2.0 Pro — ByteDance's flagship, 256K context, very cost-effective",
      llm_glm: "GLM-5.1 — Tsinghua-backed, strong reasoning, 200K context",
      llm_kimi: "K2.5 — 128K context, top coding scores, automatic caching",
      llm_ernie: "ERNIE 4.5 — Baidu's 300B MoE, free consumer access",
      llm_hunyuan: "Hunyuan 2.0 — Tencent, OpenAI & Anthropic compatible APIs",
      llm_spark: "Spark Lite is free — iFlytek, strong in Chinese NLP",
      llm_minimax: "M2.7 — 200K context, strong multimodal and voice",
      llm_stepfun: "Step 3.5 Flash — 196B MoE, very affordable ($0.10/1M input)",
      llm_yi: "Yi-Lightning — bilingual Chinese/English, open-source",
      llm_baichuan: "Baichuan 4 — specialized in finance, law, medicine",
    },
    searchDescriptions: {
      search_brave: "Structured snippets with privacy focus — free tier available",
      search_tavily: "AI-optimized search with depth control and topic filtering",
      search_exa: "Neural + keyword search with content extraction and summaries",
      search_perplexity: "AI-synthesized answers with structured results",
      search_firecrawl: "Search + deep web scraping for full content extraction",
      search_gemini: "AI-synthesized answers via Google Search grounding",
      search_grok: "AI-synthesized answers with real-time X/Twitter data",
      search_kimi: "AI-synthesized answers via Moonshot web search",
      search_duckduckgo: "No API key required — privacy-first fallback",
      search_searxng: "Self-hosted meta-search — aggregates Google, Bing, and more",
    },
    dataDescriptions: {
      d_kroness: "Unified feed across stocks, crypto, forex, commodities, indices — built-in",
      d_yfinance: "Real-time prices, fundamentals, options chains — no API key needed",
      d_stooq: "Historical EOD via CSV — no registration, works with pandas",
      d_alpaca: "Real-time US stock/options data + paper trading API",
      d_finnhub: "Real-time quotes, fundamentals, ESG, insider transactions — 60 calls/min",
      d_twelvedata: "Stocks, ETFs, 100+ technical indicators — 800 calls/day",
      d_alphavantage: "Licensed Nasdaq data — prices, fundamentals, technicals — 25 calls/day",
      d_fmp: "Financial statements, ratios, DCF, earnings — 250 req/day",
      d_tiingo: "30+ years EOD history, intraday, fundamentals — ideal for backtesting",
      d_polygon: "Tick-level institutional-grade data — free EOD tier",
      d_eodhd: "EOD prices, insider trading (SEC Form 4), earnings calendars",
      d_marketstack: "70+ global exchanges, 170K+ tickers — 100 req/month",
      d_coingecko: "18K+ coins, 1K+ exchanges, OHLCV, trending — 30 calls/min",
      d_binance: "All pairs — ticker, OHLCV, order book, WebSocket streams — no key needed",
      d_ccxt: "Unified access to 100+ exchanges — open-source library",
      d_coinpaprika: "2K+ assets, no registration needed — 20K calls/month",
      d_kraken: "Ticker, OHLC, L2/L3 order books — no account needed",
      d_coinbase: "Candles, tickers, order books — US-regulated exchange",
      d_coinmarketcap: "Prices, market cap, Fear & Greed index — 10K credits/month",
      d_exchangerate: "161 currencies, daily rates — 1,500 req/month",
      d_openexchangerates: "200+ currencies, hourly updates — 1K req/month",
      d_fixer: "170+ currencies from ECB — 100 req/month (EUR base)",
      d_currencyfreaks: "Current and historical rates — 1K req/month",
      d_alphavantage_commodities: "WTI, Brent, gold, wheat, corn, coffee — same API key as stocks",
      d_oilpriceapi: "60+ energy & agricultural commodities from ICE/CME",
      d_commoditiesapi: "Gold, silver, WTI, Brent — current & historical — 100 req/month",
      d_metalsapi: "Gold, silver, platinum, palladium — 100 req/month",
      d_fred: "800K+ series — GDP, CPI, rates, employment — US Federal Reserve",
      d_worldbank: "16K+ indicators — GDP, poverty, trade for 200+ countries — no key needed",
      d_bls: "CPI, PPI, employment, wages — official US government source",
      d_treasury: "Yield curves, national debt, fiscal data — no key needed",
      d_imf: "World Economic Outlook, balance of payments — 190+ countries",
      d_ecb: "FX rates, refinancing rates, HICP inflation — European Central Bank",
      d_bis: "Cross-border banking, credit, effective exchange rates — no key needed",
      d_cftc: "Commitments of Traders — futures positioning by trader category",
      d_openinsider: "SEC Form 4 insider trades — buys, sells, net activity — no key needed",
      d_eia: "Oil, gas, electricity, coal, energy outlook — US Energy Information Admin",
      d_nasdaq: "Millions of time-series from 400+ sources — 50 calls/day",
      d_simfin: "Financial statements, ratios, derived metrics — bulk data access",
      d_sec_edgar: "All SEC filings, XBRL financials since 1993 — no key needed",
      d_apewisdom: "Reddit stock/crypto mentions from WSB, r/stocks — no key needed",
      d_finra: "Dark pool volume, daily short volume reports — public data",
      d_finnhub_alt: "Social sentiment, congressional trading, lobbying, FDA calendar",
      d_newsapi: "150K+ news sources, keyword search — 100 req/day",
      d_marketaux: "Financial news with ticker tagging — 100 req/day",
      d_akshare: "A-shares, HK stocks, futures, bonds, macro — 1000+ functions, no registration",
      d_baostock: "A-share historical prices, financial reports — completely free",
      d_tushare: "A-share daily/minute data, financials, macro — 173 interfaces",
      d_jqdata: "A-shares, ETFs, futures — professional quant data SDK",
      d_eastmoney: "A-share real-time quotes, capital flow — free via AKShare",
      d_sina: "A-share, HK stock real-time quotes — no API key",
      d_akshare_futures: "Domestic futures/options — SHFE, DCE, CZCE exchanges",
      d_akshare_macro: "China CPI/GDP/PMI, US/EU economic indicators",
    },
    stepPrefix: "Step",
    pairWithBrowser: "Sign in with browser",
    paired: "✓ Paired",
    orEnterKey: "or enter API key manually",
    apiKey: "API Key",
    apiKeyOptional: "(not required for local)",
    storedLocally: "Stored locally only.",
    skipForNow: "Skip for now →",
    skipUseDuckDuckGo: "Skip (use DuckDuckGo) →",
    noKeyRequired: "✓ No API key required — ready to use",
    fallbackNote: "Stored locally only. Falls back to DuckDuckGo if no key is provided.",
    autoUpgradeNote: "When an API key is provided, QuantClaw auto-upgrades to the paid tier and routes requests based on rate limits.",
    sourcesEnabled: "source(s) enabled",
    free: "free",
    back: "← Back",
    continue_: "Continue →",
    launchButton: "Launch QuantClaw",
    initializingAgents: "Initializing agents...",
    youreLive: "You're live",
    redirecting: "Redirecting to your dashboard...",
    configured: "✓ Ready",
    skipped: "Skipped",
    ready: "Ready",
    optional: "Optional",
    saving: "Saving...",
    addCustomTicker: "Add custom ticker...",
    add: "Add",
    tickersSelected: "ticker(s) selected",
    changeAnytime: "You can change this anytime in Settings",
    telegramBotToken: "Bot token",
    telegramChatId: "Chat ID",
    webhookUrl: "Webhook URL",
    notificationLocalNote: "Optional. Credentials are stored locally in quantclaw.yaml and never returned by the API.",
    notificationTelegramBoth: "Telegram needs both a bot token and chat ID.",
    notificationSaveFailed: "Failed to save notification settings.",
    noNotifications: "None",
    reviewLanguage: "Language",
    reviewModel: "Model Provider",
    reviewSearch: "Search Provider",
    reviewData: "Market Data",
    reviewBroker: "Broker",
    reviewWatchlist: "Watchlist",
    reviewNotifications: "Notifications",
    paperTrading: "Paper Trading",
    paperTradingDesc: "Simulated trading with virtual money — no risk, full functionality",
    alpacaDesc: "Commission-free trading API — supports stocks and crypto",
    ibkrDesc: "Professional brokerage — widest market access",
    secretKey: "Secret Key",
    recommended: "Recommended",
    fast: "Fast",
    local: "Local",
    selfHosted: "Self-hosted",
    pro: "Pro",
    presetMag7: "Mag 7",
    presetIndexETFs: "Index ETFs",
    presetBlueChips: "Blue Chips",
  },
  zh: {
    steps: { language: "语言", model: "模型", search: "搜索", data: "数据", broker: "券商", watchlist: "自选股", notifications: "通知", launch: "启动" },
    languageStep: { title: "选择语言", subtitle: "选择 QuantClaw 界面和 AI 代理回复使用的语言。" },
    llmStep: { title: "选择模型提供商", subtitle: "QuantClaw 使用大语言模型驱动 13 个交易代理，请选择您的提供商。" },
    searchStep: { title: "搜索提供商", subtitle: "代理使用网络搜索进行市场研究、新闻分析和实时信息收集。" },
    dataStep: { title: "行情数据源", subtitle: "所有免费数据源已默认启用。添加付费数据源的 API 密钥可解锁更高的请求频率 — QuantClaw 会自动切换到最快的可用数据源。" },
    brokerStep: { title: "连接券商", subtitle: "从模拟交易开始零风险测试策略，或连接实盘券商。" },
    watchlistStep: { title: "创建自选股", subtitle: "选择您希望 QuantClaw 监控和交易的股票代码。" },
    notificationStep: { title: "通知目的地", subtitle: "可选连接 Telegram、Discord 或 Slack，用于接收紧急 QuantClaw 事件。" },
    launchStep: { title: "准备启动", subtitle: "确认您的配置并启动 QuantClaw。" },
    dataCategories: { all_markets: "全市场", stocks: "股票与ETF", crypto: "加密货币", forex: "外汇", commodities: "大宗商品", economic: "经济数据", alternative: "另类数据与情绪", cn_stocks: "A股", cn_futures: "期货与大宗商品", cn_economic: "宏观经济" },
    llmDescriptions: {
      llm_ollama: "本地运行模型 — Llama、Qwen、Mistral 等，无需 API 密钥",
      llm_openai: "GPT-4o、o1、o3 — 强大的推理和代码生成能力",
      llm_anthropic: "Claude Opus、Sonnet、Haiku — 综合代理性能最佳",
      llm_google: "Gemini 2.5 Pro/Flash — 超大上下文窗口，支持多模态",
      llm_deepseek: "DeepSeek V3/R1 — 高性能，高性价比",
      llm_xai: "Grok 模型 — 实时知识，X/Twitter 集成",
      llm_mistral: "Mistral Large/Medium — 欧洲领先的模型提供商",
      llm_groq: "LPU 推理 — 超快响应速度",
      llm_openrouter: "统一访问 200+ 模型",
      llm_together: "开源模型，快速推理",
      llm_deepseek_cn: "DeepSeek V4/R1 — 注册赠送 500 万 tokens，兼容 OpenAI 接口",
      llm_qwen: "通义千问 Qwen3.5 397B — 国内最大开源模型族，免费聊天应用",
      llm_doubao: "字节跳动 Seed 2.0 Pro — 256K 上下文，极高性价比",
      llm_glm: "智谱 GLM-5.1 — 清华系，强推理能力，200K 上下文",
      llm_kimi: "月之暗面 K2.5 — 128K 上下文，代码能力顶尖，自动缓存",
      llm_ernie: "百度文心一言 ERNIE 4.5 — 300B MoE，个人用户免费",
      llm_hunyuan: "腾讯混元 2.0 — 兼容 OpenAI 和 Anthropic API 格式",
      llm_spark: "讯飞星火 Lite 版免费 — 中文 NLP 实力强劲",
      llm_minimax: "MiniMax M2.7 — 200K 上下文，多模态和语音能力强",
      llm_stepfun: "阶跃星辰 Step 3.5 Flash — 196B MoE，极低价格",
      llm_yi: "零一万物 Yi-Lightning — 中英双语优化，开源模型",
      llm_baichuan: "百川 Baichuan 4 — 金融、法律、医疗领域专精",
    },
    searchDescriptions: {
      search_brave: "结构化摘要，注重隐私 — 有免费套餐",
      search_tavily: "AI 优化搜索，支持深度控制和主题过滤",
      search_exa: "神经网络 + 关键词搜索，支持内容提取和摘要",
      search_perplexity: "AI 综合回答，结构化结果",
      search_firecrawl: "搜索 + 深度网页抓取，完整内容提取",
      search_gemini: "通过 Google 搜索 Grounding 的 AI 综合回答",
      search_grok: "AI 综合回答，实时 X/Twitter 数据",
      search_kimi: "通过月之暗面网络搜索的 AI 综合回答",
      search_duckduckgo: "无需 API 密钥 — 注重隐私的备选方案",
      search_searxng: "自托管元搜索 — 聚合 Google、Bing 等",
    },
    dataDescriptions: {
      d_kroness: "统一数据源 — 股票、加密货币、外汇、大宗商品、指数 — 内置",
      d_yfinance: "实时价格、基本面、期权链 — 无需 API 密钥",
      d_stooq: "历史收盘价 CSV 下载 — 无需注册",
      d_alpaca: "美股/期权实时数据 + 模拟交易 API",
      d_finnhub: "实时行情、基本面、ESG、内幕交易 — 60次/分钟",
      d_twelvedata: "股票、ETF、100+ 技术指标 — 800次/天",
      d_alphavantage: "纳斯达克授权数据 — 价格、基本面、技术指标 — 25次/天",
      d_fmp: "财务报表、比率、DCF、收益 — 250次/天",
      d_tiingo: "30+ 年历史数据，日内数据 — 适合回测",
      d_polygon: "Tick 级机构级数据 — 免费 EOD 层",
      d_eodhd: "收盘价、内幕交易 (SEC Form 4)、财报日历",
      d_marketstack: "70+ 全球交易所，170K+ 代码 — 100次/月",
      d_coingecko: "18K+ 币种，1K+ 交易所，OHLCV — 30次/分钟",
      d_binance: "全部交易对 — 行情、OHLCV、订单簿、WebSocket — 无需密钥",
      d_ccxt: "统一访问 100+ 交易所 — 开源库",
      d_coinpaprika: "2K+ 资产，无需注册 — 20K次/月",
      d_kraken: "行情、OHLC、L2/L3 订单簿 — 无需账号",
      d_coinbase: "K线、行情、订单簿 — 美国合规交易所",
      d_coinmarketcap: "价格、市值、恐贪指数 — 10K 积分/月",
      d_exchangerate: "161 种货币，每日汇率 — 1,500次/月",
      d_openexchangerates: "200+ 种货币，每小时更新 — 1K次/月",
      d_fixer: "170+ 种货币（ECB 数据）— 100次/月",
      d_currencyfreaks: "实时和历史汇率 — 1K次/月",
      d_alphavantage_commodities: "WTI、布伦特、黄金、小麦、玉米、咖啡 — 与股票同一密钥",
      d_oilpriceapi: "60+ 能源和农产品价格（ICE/CME）",
      d_commoditiesapi: "黄金、白银、WTI、布伦特 — 100次/月",
      d_metalsapi: "黄金、白银、铂金、钯金 — 100次/月",
      d_fred: "80万+ 数据序列 — GDP、CPI、利率 — 美联储",
      d_worldbank: "1.6万+ 指标 — GDP、贫困、贸易 — 200+ 国家 — 无需密钥",
      d_bls: "CPI、PPI、就业、工资 — 美国政府官方数据源",
      d_treasury: "收益率曲线、国债、财政数据 — 无需密钥",
      d_imf: "世界经济展望、国际收支 — 190+ 国家",
      d_ecb: "汇率、再融资利率、HICP 通胀 — 欧洲央行",
      d_bis: "跨境银行、信贷、有效汇率 — 无需密钥",
      d_cftc: "交易者持仓报告 — 按交易者类别的期货持仓",
      d_openinsider: "SEC 表格4 内部人交易 — 买入、卖出、净活动 — 无需密钥",
      d_eia: "石油、天然气、电力、煤炭 — 美国能源信息署",
      d_nasdaq: "数百万时间序列 — 400+ 数据源 — 50次/天",
      d_simfin: "财务报表、比率、衍生指标 — 批量数据访问",
      d_sec_edgar: "全部 SEC 文件、XBRL 财务数据 — 无需密钥",
      d_apewisdom: "Reddit WSB/r/stocks 股票/加密货币提及 — 无需密钥",
      d_finra: "暗池交易量、每日做空量报告 — 公开数据",
      d_finnhub_alt: "社交情绪、国会交易、游说、FDA 日历",
      d_newsapi: "15万+ 新闻源，关键词搜索 — 100次/天",
      d_marketaux: "金融新闻，按股票代码标签 — 100次/天",
      d_akshare: "A股/港股/期货/债券/宏观 — 1000+ 接口，无需注册",
      d_baostock: "A股历史行情、财务报表 — 完全免费，无需注册",
      d_tushare: "A股日/分钟线、财务数据、宏观指标 — 173 个接口",
      d_jqdata: "A股/ETF/期货 — 专业量化数据 SDK",
      d_eastmoney: "A股实时行情、资金流向 — 通过 AKShare 免费获取",
      d_sina: "A股/港股实时行情 — 无需 API 密钥",
      d_akshare_futures: "国内期货/期权行情 — 上期所/大商所/郑商所",
      d_akshare_macro: "中国 CPI/GDP/PMI、中美欧经济指标",
    },
    stepPrefix: "步骤",
    pairWithBrowser: "通过浏览器登录授权",
    paired: "✓ 已配对",
    orEnterKey: "或手动输入 API 密钥",
    apiKey: "API 密钥",
    apiKeyOptional: "（本地运行无需密钥）",
    storedLocally: "仅存储在本地。",
    skipForNow: "暂时跳过 →",
    skipUseDuckDuckGo: "跳过（使用 DuckDuckGo）→",
    noKeyRequired: "✓ 无需 API 密钥 — 即可使用",
    fallbackNote: "仅存储在本地。未提供密钥时将使用 DuckDuckGo 作为备选。",
    autoUpgradeNote: "提供 API 密钥后，QuantClaw 会自动切换到付费层级，并根据请求频率限制智能路由。",
    sourcesEnabled: "个数据源已启用",
    free: "免费",
    back: "← 返回",
    continue_: "继续 →",
    launchButton: "启动 QuantClaw",
    initializingAgents: "正在初始化代理...",
    youreLive: "已上线",
    redirecting: "正在跳转到仪表盘...",
    configured: "✓ 就绪",
    skipped: "已跳过",
    ready: "就绪",
    optional: "可选",
    saving: "保存中...",
    addCustomTicker: "添加自定义代码...",
    add: "添加",
    tickersSelected: "个代码已选择",
    changeAnytime: "您可以随时在设置中更改",
    telegramBotToken: "机器人令牌",
    telegramChatId: "聊天 ID",
    webhookUrl: "Webhook URL",
    notificationLocalNote: "可选。凭据保存在本地 quantclaw.yaml 中，API 不会返回这些值。",
    notificationTelegramBoth: "Telegram 需要机器人令牌和聊天 ID。",
    notificationSaveFailed: "保存通知设置失败。",
    noNotifications: "无",
    reviewLanguage: "语言",
    reviewModel: "模型提供商",
    reviewSearch: "搜索提供商",
    reviewData: "行情数据",
    reviewBroker: "券商",
    reviewWatchlist: "自选股",
    reviewNotifications: "通知",
    paperTrading: "模拟交易",
    paperTradingDesc: "使用虚拟资金的模拟交易 — 零风险，完整功能",
    alpacaDesc: "免佣金交易 API — 支持股票和加密货币",
    ibkrDesc: "专业券商 — 最广泛的市场覆盖",
    secretKey: "密钥",
    recommended: "推荐",
    fast: "快速",
    local: "本地",
    selfHosted: "自托管",
    pro: "专业版",
    presetMag7: "七巨头",
    presetIndexETFs: "指数 ETF",
    presetBlueChips: "蓝筹股",
  },
  ja: {
    steps: { language: "言語", model: "モデル", search: "検索", data: "データ", broker: "ブローカー", watchlist: "ウォッチリスト", notifications: "通知", launch: "起動" },
    languageStep: { title: "言語を選択", subtitle: "QuantClaw のインターフェースと AI エージェントの応答に使用する言語を選択してください。" },
    llmStep: { title: "モデルプロバイダーを選択", subtitle: "QuantClaw は 13 の取引エージェントに大規模言語モデルを使用します。プロバイダーを選択してください。" },
    searchStep: { title: "検索プロバイダー", subtitle: "エージェントはウェブ検索を使って市場調査、ニュース分析、リアルタイム情報収集を行います。" },
    dataStep: { title: "市場データソース", subtitle: "無料のデータソースはすべてデフォルトで有効です。有料プロバイダーの API キーを追加すると、より高いレート制限が解除されます。QuantClaw は最速のソースに自動ルーティングします。" },
    brokerStep: { title: "ブローカーを接続", subtitle: "ペーパートレードでリスクなく戦略をテストするか、実際のブローカーに接続します。" },
    watchlistStep: { title: "ウォッチリストを作成", subtitle: "QuantClaw で監視・取引したいティッカーを選択してください。" },
    notificationStep: { title: "通知先", subtitle: "Telegram、Discord、Slack を任意で接続し、重要な QuantClaw イベントを受け取れます。" },
    launchStep: { title: "起動準備完了", subtitle: "設定を確認して QuantClaw を起動します。" },
    dataCategories: { all_markets: "全市場", stocks: "株式・ETF", crypto: "暗号通貨", forex: "外国為替", commodities: "コモディティ", economic: "経済データ", alternative: "オルタナティブ・センチメント", cn_stocks: "A株", cn_futures: "先物・コモディティ", cn_economic: "経済データ" },
    llmDescriptions: {
      llm_ollama: "モデルをローカルで実行 — Llama、Qwen、Mistral など。API キー不要",
      llm_openai: "GPT-4o、o1、o3 — 強力な推論とコード生成",
      llm_anthropic: "Claude Opus、Sonnet、Haiku — 総合的なエージェント性能が最高",
      llm_google: "Gemini 2.5 Pro/Flash — 大規模コンテキスト、マルチモーダル対応",
      llm_deepseek: "DeepSeek V3/R1 — 高性能、コスト効率が高い",
      llm_xai: "Grok モデル — リアルタイム知識、X/Twitter 統合",
      llm_mistral: "Mistral Large/Medium — 欧州の主要プロバイダー",
      llm_groq: "LPU 推論 — 超高速レスポンス",
      llm_openrouter: "200以上のモデルへの統合アクセス",
      llm_together: "オープンソースモデル、高速推論",
      llm_deepseek_cn: "DeepSeek V4/R1 — 登録で500万トークン無料、OpenAI互換API",
      llm_qwen: "Qwen3.5 397B — 中国最大のオープンモデル、無料チャットアプリ",
      llm_doubao: "Seed 2.0 Pro — ByteDance、256Kコンテキスト、非常にコスト効率的",
      llm_glm: "GLM-5.1 — 清華大学系、強力な推論、200Kコンテキスト",
      llm_kimi: "K2.5 — 128Kコンテキスト、コーディング最高スコア",
      llm_ernie: "ERNIE 4.5 — Baidu、300B MoE、個人利用無料",
      llm_hunyuan: "Hunyuan 2.0 — Tencent、OpenAI & Anthropic互換API",
      llm_spark: "Spark Lite無料 — iFlytek、中国語NLPに強い",
      llm_minimax: "M2.7 — 200Kコンテキスト、マルチモーダル・音声",
      llm_stepfun: "Step 3.5 Flash — 196B MoE、非常に手頃（$0.10/1M入力）",
      llm_yi: "Yi-Lightning — 中英バイリンガル、オープンソース",
      llm_baichuan: "Baichuan 4 — 金融・法律・医療に特化",
    },
    searchDescriptions: {
      search_brave: "構造化スニペット、プライバシー重視 — 無料プランあり",
      search_tavily: "AI最適化検索、深度制御とトピックフィルタリング",
      search_exa: "ニューラル + キーワード検索、コンテンツ抽出と要約",
      search_perplexity: "AI統合回答、構造化された結果",
      search_firecrawl: "検索 + ディープウェブスクレイピング、完全なコンテンツ抽出",
      search_gemini: "Google検索グラウンディングによるAI統合回答",
      search_grok: "リアルタイムX/TwitterデータによるAI統合回答",
      search_kimi: "Moonshot ウェブ検索によるAI統合回答",
      search_duckduckgo: "APIキー不要 — プライバシー重視のフォールバック",
      search_searxng: "セルフホスト型メタ検索 — Google、Bingなどを集約",
    },
    dataDescriptions: {
      d_kroness: "統合フィード — 株式、暗号通貨、外国為替、コモディティ、指数 — 内蔵",
      d_yfinance: "リアルタイム価格、ファンダメンタル、オプションチェーン — キー不要",
      d_stooq: "EOD履歴CSV — 登録不要、pandas対応",
      d_alpaca: "米国株/オプションリアルタイムデータ + ペーパートレードAPI",
      d_finnhub: "リアルタイム相場、ファンダメンタル、ESG、インサイダー — 60回/分",
      d_twelvedata: "株式、ETF、100+テクニカル指標 — 800回/日",
      d_alphavantage: "Nasdaq認定データ — 価格、ファンダメンタル — 25回/日",
      d_fmp: "財務諸表、比率、DCF、収益 — 250回/日",
      d_tiingo: "30年以上のEOD履歴、日中データ — バックテストに最適",
      d_polygon: "ティックレベルの機関投資家向けデータ — 無料EOD層",
      d_eodhd: "EOD価格、インサイダー取引、決算カレンダー",
      d_marketstack: "70+グローバル取引所、170K+ティッカー — 100回/月",
      d_coingecko: "18K+コイン、1K+取引所、OHLCV — 30回/分",
      d_binance: "全ペア — ティッカー、OHLCV、板情報、WebSocket — キー不要",
      d_ccxt: "100+取引所への統合アクセス — オープンソースライブラリ",
      d_coinpaprika: "2K+資産、登録不要 — 20K回/月",
      d_kraken: "ティッカー、OHLC、L2/L3板情報 — アカウント不要",
      d_coinbase: "ローソク足、ティッカー、板情報 — 米国規制取引所",
      d_coinmarketcap: "価格、時価総額、恐怖・強欲指数 — 10Kクレジット/月",
      d_exchangerate: "161通貨、日次レート — 1,500回/月",
      d_openexchangerates: "200+通貨、毎時更新 — 1K回/月",
      d_fixer: "170+通貨（ECB）— 100回/月",
      d_currencyfreaks: "現在・過去のレート — 1K回/月",
      d_alphavantage_commodities: "WTI、ブレント、金、小麦、コーン、コーヒー",
      d_oilpriceapi: "60+エネルギー・農産物商品（ICE/CME）",
      d_commoditiesapi: "金、銀、WTI、ブレント — 100回/月",
      d_metalsapi: "金、銀、プラチナ、パラジウム — 100回/月",
      d_fred: "80万+シリーズ — GDP、CPI、金利 — 米連邦準備制度",
      d_worldbank: "1.6万+指標 — GDP、貧困、貿易 — 200+カ国 — キー不要",
      d_bls: "CPI、PPI、雇用、賃金 — 米国政府公式データソース",
      d_treasury: "イールドカーブ、国債、財政データ — キー不要",
      d_imf: "世界経済見通し、国際収支 — 190+カ国",
      d_ecb: "為替レート、リファイナンス金利、HICPインフレ — 欧州中央銀行",
      d_bis: "クロスボーダーバンキング、信用、実効為替レート — キー不要",
      d_cftc: "COTレポート — トレーダーカテゴリー別の先物ポジション",
      d_openinsider: "SEC Form 4 インサイダー取引 — 売買・純活動 — キー不要",
      d_eia: "石油、天然ガス、電力、石炭 — 米エネルギー情報局",
      d_nasdaq: "数百万の時系列 — 400+ソース — 50回/日",
      d_simfin: "財務諸表、比率、導出指標 — バルクデータアクセス",
      d_sec_edgar: "全SEC提出書類、XBRLデータ — キー不要",
      d_apewisdom: "Reddit WSB/r/stocks の株式・暗号通貨言及 — キー不要",
      d_finra: "ダークプール取引量、日次空売り量 — 公開データ",
      d_finnhub_alt: "ソーシャルセンチメント、議会取引、ロビー活動",
      d_newsapi: "15万+ニュースソース、キーワード検索 — 100回/日",
      d_marketaux: "金融ニュース、ティッカータグ付き — 100回/日",
      d_akshare: "A株/香港株/先物/債券/マクロ — 1000+関数、登録不要",
      d_baostock: "A株履歴価格、財務諸表 — 完全無料",
      d_tushare: "A株日/分足データ、財務、マクロ — 173インターフェース",
      d_jqdata: "A株/ETF/先物 — プロフェッショナルクオンツデータSDK",
      d_eastmoney: "A株リアルタイム相場、資金フロー — AKShare経由で無料",
      d_sina: "A株/香港株リアルタイム相場 — APIキー不要",
      d_akshare_futures: "国内先物/オプション — 上海/大連/鄭州取引所",
      d_akshare_macro: "中国CPI/GDP/PMI、米欧経済指標",
    },
    stepPrefix: "ステップ",
    pairWithBrowser: "ブラウザでサインイン",
    paired: "✓ ペアリング済み",
    orEnterKey: "または API キーを手動入力",
    apiKey: "API キー",
    apiKeyOptional: "（ローカルでは不要）",
    storedLocally: "ローカルにのみ保存されます。",
    skipForNow: "今はスキップ →",
    skipUseDuckDuckGo: "スキップ（DuckDuckGo を使用）→",
    noKeyRequired: "✓ API キー不要 — すぐに使用可能",
    fallbackNote: "ローカルにのみ保存。キーが未設定の場合は DuckDuckGo にフォールバックします。",
    autoUpgradeNote: "API キーが提供されると、QuantClaw は自動的に有料プランに切り替え、レート制限に基づいてリクエストをルーティングします。",
    sourcesEnabled: "個のソースが有効",
    free: "無料",
    back: "← 戻る",
    continue_: "続ける →",
    launchButton: "QuantClaw を起動",
    initializingAgents: "エージェントを初期化中...",
    youreLive: "稼働開始",
    redirecting: "ダッシュボードに移動中...",
    configured: "✓ 準備完了",
    skipped: "スキップ済み",
    ready: "準備完了",
    optional: "任意",
    saving: "保存中...",
    addCustomTicker: "カスタムティッカーを追加...",
    add: "追加",
    tickersSelected: "個のティッカーを選択",
    changeAnytime: "設定からいつでも変更できます",
    telegramBotToken: "Bot トークン",
    telegramChatId: "チャット ID",
    webhookUrl: "Webhook URL",
    notificationLocalNote: "任意です。認証情報はローカルの quantclaw.yaml に保存され、API から返されることはありません。",
    notificationTelegramBoth: "Telegram には Bot トークンとチャット ID の両方が必要です。",
    notificationSaveFailed: "通知設定の保存に失敗しました。",
    noNotifications: "なし",
    reviewLanguage: "言語",
    reviewModel: "モデルプロバイダー",
    reviewSearch: "検索プロバイダー",
    reviewData: "市場データ",
    reviewBroker: "ブローカー",
    reviewWatchlist: "ウォッチリスト",
    reviewNotifications: "通知",
    paperTrading: "ペーパートレード",
    paperTradingDesc: "仮想資金でのシミュレーション取引 — リスクなし、全機能利用可能",
    alpacaDesc: "手数料無料の取引 API — 株式と暗号通貨に対応",
    ibkrDesc: "プロフェッショナルブローカー — 最も幅広い市場アクセス",
    secretKey: "シークレットキー",
    recommended: "おすすめ",
    fast: "高速",
    local: "ローカル",
    selfHosted: "セルフホスト",
    pro: "プロ",
    presetMag7: "マグ7",
    presetIndexETFs: "指数 ETF",
    presetBlueChips: "優良株",
  },
};

export function useTranslations(lang: string): Translations {
  return translations[(lang as Lang)] || translations.en;
}

export function translateTag(tag: string, t: Translations): string {
  const map: Record<string, string> = {
    "Recommended": t.recommended,
    "Free": t.free,
    "Fast": t.fast,
    "Local": t.local,
    "Self-hosted": t.selfHosted,
    "Pro": t.pro,
  };
  return map[tag] || tag;
}
