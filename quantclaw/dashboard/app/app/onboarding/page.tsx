"use client";
import { useState, useEffect } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations, translateTag } from "./i18n";
import { detectRegion } from "./geo";

const API = "http://localhost:24120";

type Step = "llm" | "search" | "data" | "broker" | "watchlist" | "launch";

interface StepConfig {
  id: Step;
  label: string;
  number: string;
}

const STEPS: StepConfig[] = [
  { id: "llm", label: "Model", number: "01" },
  { id: "search", label: "Search", number: "02" },
  { id: "data", label: "Data", number: "03" },
  { id: "broker", label: "Broker", number: "04" },
  { id: "watchlist", label: "Watchlist", number: "05" },
  { id: "launch", label: "Launch", number: "06" },
];

const LANG_NAMES: Record<string, string> = { en: "English", zh: "简体中文", ja: "日本語" };

interface Provider {
  id: string;
  name: string;
  description: string;
  tag?: string;
  free?: boolean; // true = no API key needed, auto-enabled by default
  keyUrl?: string; // URL to register and get an API key
}

interface LLMProvider extends Provider {
  pairable?: boolean; // supports browser-based OAuth pairing
}

// Global providers (accessible outside China)
const LLM_GLOBAL: LLMProvider[] = [
  { id: "ollama", name: "Ollama", description: "llm_ollama", tag: "Local", free: true },
  { id: "openai", name: "OpenAI", description: "llm_openai", tag: "Recommended", pairable: true },
  { id: "anthropic", name: "Anthropic", description: "llm_anthropic", pairable: true },
  { id: "google", name: "Google Gemini", description: "llm_google", pairable: true },
  { id: "deepseek", name: "DeepSeek", description: "llm_deepseek" },
  { id: "xai", name: "xAI", description: "llm_xai" },
  { id: "mistral", name: "Mistral", description: "llm_mistral" },
  { id: "groq", name: "Groq", description: "llm_groq" },
  { id: "openrouter", name: "OpenRouter", description: "llm_openrouter" },
  { id: "together", name: "Together AI", description: "llm_together" },
];

// China-accessible providers
const LLM_CHINA: LLMProvider[] = [
  { id: "ollama", name: "Ollama", description: "llm_ollama", tag: "Local", free: true },
  { id: "deepseek", name: "DeepSeek (深度求索)", description: "llm_deepseek_cn", tag: "Recommended" },
  { id: "qwen", name: "Qwen / 通义千问", description: "llm_qwen" },
  { id: "doubao", name: "Doubao / 豆包", description: "llm_doubao" },
  { id: "glm", name: "Zhipu GLM (智谱)", description: "llm_glm" },
  { id: "kimi", name: "Kimi / 月之暗面", description: "llm_kimi" },
  { id: "ernie", name: "ERNIE / 文心一言", description: "llm_ernie" },
  { id: "hunyuan", name: "Hunyuan / 腾讯混元", description: "llm_hunyuan" },
  { id: "spark", name: "Spark / 讯飞星火", description: "llm_spark", tag: "Free", free: true },
  { id: "minimax", name: "MiniMax (稀宇)", description: "llm_minimax" },
  { id: "stepfun", name: "StepFun / 阶跃星辰", description: "llm_stepfun" },
  { id: "yi", name: "Yi / 零一万物", description: "llm_yi" },
  { id: "baichuan", name: "Baichuan / 百川", description: "llm_baichuan" },
];

const SEARCH_PROVIDERS: Provider[] = [
  { id: "brave", name: "Brave Search", description: "search_brave", tag: "Recommended" },
  { id: "tavily", name: "Tavily", description: "search_tavily" },
  { id: "exa", name: "Exa", description: "search_exa" },
  { id: "perplexity", name: "Perplexity", description: "search_perplexity" },
  { id: "firecrawl", name: "Firecrawl", description: "search_firecrawl" },
  { id: "gemini", name: "Gemini Search", description: "search_gemini" },
  { id: "grok", name: "Grok Search", description: "search_grok" },
  { id: "kimi", name: "Kimi", description: "search_kimi" },
  { id: "duckduckgo", name: "DuckDuckGo", description: "search_duckduckgo", tag: "Free" },
  { id: "searxng", name: "SearXNG", description: "search_searxng", tag: "Self-hosted" },
];

interface DataCategory {
  id: string;
  label: string;
  providers: Provider[];
}

const DATA_GLOBAL: DataCategory[] = [
  { id: "all_markets", label: "All Markets", providers: [
    { id: "kroness", name: "Kroness", description: "d_kroness", tag: "Free", free: true },
  ]},
  { id: "stocks", label: "Stocks & ETFs", providers: [
    { id: "yfinance", name: "Yahoo Finance", description: "d_yfinance", tag: "Free", free: true },
    { id: "stooq", name: "Stooq", description: "d_stooq", tag: "Free", free: true },
    { id: "alphavantage", name: "Alpha Vantage", description: "d_alphavantage", keyUrl: "https://www.alphavantage.co/support/#api-key" },
    { id: "twelvedata", name: "Twelve Data", description: "d_twelvedata", keyUrl: "https://twelvedata.com/pricing" },
    { id: "finnhub", name: "Finnhub", description: "d_finnhub", keyUrl: "https://finnhub.io/register" },
    { id: "fmp", name: "Financial Modeling Prep", description: "d_fmp", keyUrl: "https://site.financialmodelingprep.com/developer/docs" },
    { id: "tiingo", name: "Tiingo", description: "d_tiingo", keyUrl: "https://www.tiingo.com/account/api/token" },
    { id: "simfin", name: "SimFin", description: "d_simfin", keyUrl: "https://app.simfin.com/login" },
    { id: "nasdaq", name: "Nasdaq Data Link", description: "d_nasdaq", keyUrl: "https://data.nasdaq.com/sign-up" },
    { id: "alpaca", name: "Alpaca Markets", description: "d_alpaca", keyUrl: "https://app.alpaca.markets/signup" },
    { id: "polygon", name: "Polygon.io", description: "d_polygon", tag: "Pro", keyUrl: "https://polygon.io/dashboard/signup" },
    { id: "eodhd", name: "EODHD", description: "d_eodhd", keyUrl: "https://eodhd.com/register" },
    { id: "marketstack", name: "Marketstack", description: "d_marketstack", keyUrl: "https://marketstack.com/signup/free" },
  ]},
  { id: "crypto", label: "Crypto", providers: [
    { id: "coingecko", name: "CoinGecko", description: "d_coingecko", tag: "Free", free: true },
    { id: "binance", name: "Binance", description: "d_binance", tag: "Free", free: true },
    { id: "ccxt", name: "CCXT", description: "d_ccxt", tag: "Free", free: true },
    { id: "coinpaprika", name: "CoinPaprika", description: "d_coinpaprika", tag: "Free", free: true },
    { id: "kraken", name: "Kraken", description: "d_kraken", tag: "Free", free: true },
    { id: "coinbase", name: "Coinbase", description: "d_coinbase", tag: "Free", free: true },
    { id: "coinmarketcap", name: "CoinMarketCap", description: "d_coinmarketcap", keyUrl: "https://pro.coinmarketcap.com/signup" },
  ]},
  { id: "forex", label: "Forex", providers: [
    { id: "exchangerate", name: "ExchangeRate-API", description: "d_exchangerate", tag: "Free", free: true },
    { id: "openexchangerates", name: "Open Exchange Rates", description: "d_openexchangerates", keyUrl: "https://openexchangerates.org/signup/free" },
    { id: "fixer", name: "Fixer.io", description: "d_fixer", keyUrl: "https://fixer.io/signup/free" },
    { id: "currencyfreaks", name: "CurrencyFreaks", description: "d_currencyfreaks", keyUrl: "https://currencyfreaks.com/signup" },
  ]},
  { id: "commodities", label: "Commodities", providers: [
    { id: "eia", name: "EIA (Energy)", description: "d_eia", keyUrl: "https://www.eia.gov/opendata/register.php" },
    { id: "alphavantage_commodities", name: "Alpha Vantage", description: "d_alphavantage_commodities", keyUrl: "https://www.alphavantage.co/support/#api-key" },
    { id: "oilpriceapi", name: "Oil Price API", description: "d_oilpriceapi", tag: "Free", free: true },
    { id: "commoditiesapi", name: "Commodities-API", description: "d_commoditiesapi", keyUrl: "https://commodities-api.com/signup" },
    { id: "metalsapi", name: "Metals-API", description: "d_metalsapi", keyUrl: "https://metals-api.com/signup" },
  ]},
  { id: "economic", label: "Economic Data", providers: [
    { id: "fred", name: "FRED / ALFRED", description: "d_fred", tag: "Free", free: true },
    { id: "worldbank", name: "World Bank", description: "d_worldbank", tag: "Free", free: true },
    { id: "imf", name: "IMF Data", description: "d_imf", tag: "Free", free: true },
    { id: "bls", name: "US Bureau of Labor Statistics", description: "d_bls", tag: "Free", free: true },
    { id: "treasury", name: "US Treasury", description: "d_treasury", tag: "Free", free: true },
    { id: "ecb", name: "European Central Bank", description: "d_ecb", tag: "Free", free: true },
    { id: "bis", name: "Bank for International Settlements", description: "d_bis", tag: "Free", free: true },
  ]},
  { id: "alternative", label: "Alternative & Sentiment", providers: [
    { id: "sec_edgar", name: "SEC EDGAR", description: "d_sec_edgar", tag: "Free", free: true },
    { id: "cftc", name: "CFTC Commitments of Traders", description: "d_cftc", tag: "Free", free: true },
    { id: "openinsider", name: "OpenInsider", description: "d_openinsider", tag: "Free", free: true },
    { id: "apewisdom", name: "ApeWisdom", description: "d_apewisdom", tag: "Free", free: true },
    { id: "finra", name: "FINRA ATS", description: "d_finra", tag: "Free", free: true },
    { id: "finnhub_alt", name: "Finnhub Sentiment", description: "d_finnhub_alt", keyUrl: "https://finnhub.io/register" },
    { id: "newsapi", name: "NewsAPI", description: "d_newsapi", keyUrl: "https://newsapi.org/register" },
    { id: "marketaux", name: "Marketaux", description: "d_marketaux", keyUrl: "https://www.marketaux.com/account/signup" },
  ]},
];

const DATA_CHINA: DataCategory[] = [
  { id: "all_markets", label: "All Markets", providers: [
    { id: "kroness", name: "Kroness", description: "d_kroness", tag: "Free", free: true },
  ]},
  { id: "cn_stocks", label: "A股 / A-Shares", providers: [
    { id: "akshare", name: "AKShare", description: "d_akshare", tag: "Free", free: true },
    { id: "baostock", name: "BaoStock (证券宝)", description: "d_baostock", tag: "Free", free: true },
    { id: "tushare", name: "Tushare Pro (挖地兔)", description: "d_tushare", keyUrl: "https://tushare.pro/register" },
    { id: "jqdata", name: "JoinQuant (聚宽)", description: "d_jqdata", keyUrl: "https://www.joinquant.com/user/login/index" },
    { id: "eastmoney", name: "EastMoney (东方财富)", description: "d_eastmoney", tag: "Free", free: true },
    { id: "sina_finance", name: "Sina Finance (新浪财经)", description: "d_sina", tag: "Free", free: true },
  ]},
  { id: "cn_futures", label: "期货 / Futures & Commodities", providers: [
    { id: "akshare_futures", name: "AKShare 期货", description: "d_akshare_futures", tag: "Free", free: true },
  ]},
  { id: "cn_economic", label: "宏观经济 / Economic Data", providers: [
    { id: "akshare_macro", name: "AKShare 宏观", description: "d_akshare_macro", tag: "Free", free: true },
    { id: "fred", name: "FRED", description: "d_fred", tag: "Free", free: true },
    { id: "worldbank", name: "World Bank", description: "d_worldbank", tag: "Free", free: true },
    { id: "imf", name: "IMF Data", description: "d_imf", tag: "Free", free: true },
    { id: "bis", name: "BIS Stats", description: "d_bis", tag: "Free", free: true },
  ]},
];

const POPULAR_TICKERS_CN = [
  { symbol: "600519", name: "贵州茅台" },
  { symbol: "000858", name: "五粮液" },
  { symbol: "601318", name: "中国平安" },
  { symbol: "600036", name: "招商银行" },
  { symbol: "000001", name: "平安银行" },
  { symbol: "600276", name: "恒瑞医药" },
  { symbol: "601012", name: "隆基绿能" },
  { symbol: "300750", name: "宁德时代" },
  { symbol: "002594", name: "比亚迪" },
  { symbol: "600900", name: "长江电力" },
  { symbol: "601888", name: "中国中免" },
  { symbol: "000333", name: "美的集团" },
];

const PRESET_WATCHLISTS_CN = [
  { name: "白马股", tickers: ["600519", "000858", "601318", "600036", "300750", "002594"] },
  { name: "科创50", tickers: ["688981", "688599", "688012", "688036", "688185"] },
  { name: "新能源", tickers: ["300750", "002594", "601012", "600438", "002129"] },
];

const POPULAR_TICKERS = [
  { symbol: "SPY", name: "S&P 500 ETF" },
  { symbol: "QQQ", name: "Nasdaq 100 ETF" },
  { symbol: "AAPL", name: "Apple" },
  { symbol: "MSFT", name: "Microsoft" },
  { symbol: "GOOGL", name: "Alphabet" },
  { symbol: "AMZN", name: "Amazon" },
  { symbol: "NVDA", name: "NVIDIA" },
  { symbol: "TSLA", name: "Tesla" },
  { symbol: "META", name: "Meta" },
  { symbol: "JPM", name: "JPMorgan" },
  { symbol: "V", name: "Visa" },
  { symbol: "BRK.B", name: "Berkshire" },
];

const PRESET_WATCHLISTS = [
  { name: "Mag 7", tickers: ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META"] },
  { name: "Index ETFs", tickers: ["SPY", "QQQ", "IWM", "DIA"] },
  { name: "Blue Chips", tickers: ["AAPL", "MSFT", "JPM", "V", "JNJ", "PG", "UNH"] },
];

export default function OnboardingPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const language = searchParams.get("lang") || "en";

  const [isChina, setIsChina] = useState(false);
  const [geoLoaded, setGeoLoaded] = useState(false);

  useEffect(() => {
    detectRegion().then((geo) => {
      setIsChina(geo.isChina);
      setGeoLoaded(true);
    });
  }, []);

  const LLM_PROVIDERS = isChina ? LLM_CHINA : LLM_GLOBAL;
  const DATA_CATEGORIES = isChina ? DATA_CHINA : DATA_GLOBAL;
  const TICKERS = isChina ? POPULAR_TICKERS_CN : POPULAR_TICKERS;
  const PRESETS = isChina ? PRESET_WATCHLISTS_CN : PRESET_WATCHLISTS;

  const [currentStep, setCurrentStep] = useState<Step>("llm");
  const [animating, setAnimating] = useState(false);

  // Form state
  const [llmProvider, setLlmProvider] = useState<string>("anthropic");
  const [llmKey, setLlmKey] = useState("");

  // Check if OAuth is already connected when provider changes
  useEffect(() => {
    const selectedProvider = LLM_PROVIDERS.find((p) => p.id === llmProvider);
    if (selectedProvider?.pairable) {
      fetch(`${API}/api/oauth/status/${llmProvider}`)
        .then((r) => r.json())
        .then((s) => {
          if (s.authenticated) {
            setLlmKey("OAuth connected");
            localStorage.setItem(`quantclaw_oauth_${llmProvider}`, "true");
          }
        })
        .catch(() => {});
    }
  }, [llmProvider]);
  const [searchProvider, setSearchProvider] = useState<string>("brave");
  const [searchKey, setSearchKey] = useState("");
  const [dataSources, setDataSources] = useState<string[]>([]);

  // Auto-enable free sources and set default watchlist when geo loads
  useEffect(() => {
    if (!geoLoaded) return;
    const cats = isChina ? DATA_CHINA : DATA_GLOBAL;
    const freeSources: string[] = [];
    for (const cat of cats) {
      for (const p of cat.providers) {
        if (p.free) freeSources.push(p.id);
      }
    }
    setDataSources(freeSources);
    setWatchlist(isChina ? ["600519", "300750"] : ["SPY", "QQQ"]);
  }, [geoLoaded, isChina]);
  const [dataKeys, setDataKeys] = useState<Record<string, string>>({});
  const [brokerType, setBrokerType] = useState<string>("paper");
  const [brokerKey, setBrokerKey] = useState("");
  const [brokerSecret, setBrokerSecret] = useState("");
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [customTicker, setCustomTicker] = useState("");
  const [launching, setLaunching] = useState(false);
  const [launched, setLaunched] = useState(false);

  const t = useTranslations(language);

  const localizedSteps = STEPS.map((s) => ({
    ...s,
    label: t.steps[s.id as keyof typeof t.steps] || s.label,
  }));

  const currentIndex = STEPS.findIndex((s) => s.id === currentStep);
  const progress = ((currentIndex + 1) / STEPS.length) * 100;

  const goTo = (step: Step) => {
    setAnimating(true);
    setTimeout(() => {
      setCurrentStep(step);
      setAnimating(false);
    }, 200);
  };

  const next = () => {
    const idx = STEPS.findIndex((s) => s.id === currentStep);
    if (idx < STEPS.length - 1) goTo(STEPS[idx + 1].id);
  };

  const prev = () => {
    const idx = STEPS.findIndex((s) => s.id === currentStep);
    if (idx > 0) goTo(STEPS[idx - 1].id);
  };

  const toggleTicker = (ticker: string) => {
    setWatchlist((prev) =>
      prev.includes(ticker) ? prev.filter((t) => t !== ticker) : [...prev, ticker],
    );
  };

  const addCustomTicker = () => {
    const t = customTicker.trim().toUpperCase();
    if (t && !watchlist.includes(t)) {
      setWatchlist((prev) => [...prev, t]);
      setCustomTicker("");
    }
  };

  const applyPreset = (tickers: string[]) => {
    setWatchlist((prev) => Array.from(new Set([...prev, ...tickers])));
  };

  const handleLaunch = async () => {
    setLaunching(true);

    // Save all onboarding settings to backend
    try {
      await fetch(`${API}/api/onboarding/complete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          llm_provider: llmProvider,
          llm_key: llmKey,
          search_provider: searchProvider,
          search_key: searchKey,
          data_sources: dataSources,
          broker_type: brokerType,
          broker_key: brokerKey,
          broker_secret: brokerSecret,
          watchlist,
          language,
        }),
      });
    } catch {}

    // Save API key to localStorage if provided
    if (llmKey && llmProvider !== "ollama") {
      localStorage.setItem(`quantclaw_key_${llmProvider}`, llmKey);
    }
    if (searchKey) {
      localStorage.setItem(`quantclaw_key_search_${searchProvider}`, searchKey);
    }
    localStorage.setItem("quantclaw_provider", llmProvider);

    await new Promise((r) => setTimeout(r, 2000));
    setLaunched(true);
    await new Promise((r) => setTimeout(r, 1500));
    router.push("/dashboard");
  };

  const canProceed = (): boolean => {
    switch (currentStep) {
      case "llm": return !!llmProvider;
      case "search": return !!searchProvider;
      case "data": return dataSources.length > 0;
      case "broker": return !!brokerType;
      case "watchlist": return watchlist.length > 0;
      case "launch": return true;
      default: return false;
    }
  };

  const keyFreeSearch = ["duckduckgo", "searxng"].includes(searchProvider);
  const searchProviderName = SEARCH_PROVIDERS.find((p) => p.id === searchProvider)?.name || searchProvider;
  const llmProviderName = LLM_PROVIDERS.find((p) => p.id === llmProvider)?.name || llmProvider;

  return (
    <div className="min-h-screen flex flex-col">
      {/* Progress bar */}
      <div className="relative h-0.5 bg-hull">
        <div
          className="absolute inset-y-0 left-0 bg-gold transition-all duration-500 ease-out"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Step indicators */}
      <div className="flex items-center justify-center gap-1 pt-8 pb-2 px-4">
        {localizedSteps.map((step, i) => {
          const isActive = i === currentIndex;
          const isDone = i < currentIndex;
          return (
            <button
              key={step.id}
              onClick={() => i <= currentIndex && goTo(step.id)}
              className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-xs font-mono transition-all duration-300 ${
                isActive
                  ? "text-gold bg-gold/8"
                  : isDone
                    ? "text-muted hover:text-[#6a7a9a] cursor-pointer"
                    : "text-[#1a2a4a] cursor-default"
              }`}
            >
              <span
                className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-semibold transition-all duration-300 ${
                  isActive
                    ? "bg-gold text-void"
                    : isDone
                      ? "bg-trace-glow text-[#6a7a9a]"
                      : "bg-keel/50 text-[#1a2a4a]"
                }`}
              >
                {isDone ? "✓" : step.number}
              </span>
              <span className="hidden sm:inline">{step.label}</span>
            </button>
          );
        })}
      </div>

      {/* Content */}
      <div className="flex-1 flex items-center justify-center px-4 py-8">
        <div
          className={`w-full max-w-xl transition-all duration-200 ${
            animating ? "opacity-0 translate-y-2" : "opacity-100 translate-y-0"
          }`}
        >
          {/* Step 01: Model Provider */}
          {currentStep === "llm" && (
            <div className="animate-fade-up">
              <StepHeader
                number="01"
                title={t.llmStep.title}
                subtitle={t.llmStep.subtitle}
                stepPrefix={t.stepPrefix}
              />

              <div className="space-y-2 mb-6 max-h-[340px] overflow-y-auto pr-1 scrollbar-thin">
                {LLM_PROVIDERS.map((p) => (
                  <ProviderCard
                    key={p.id}
                    name={p.name}
                    description={t.llmDescriptions[p.description] || p.description}
                    tag={p.tag ? translateTag(p.tag, t) : undefined}
                    tagRaw={p.tag}
                    selected={llmProvider === p.id}
                    onClick={() => setLlmProvider(p.id)}
                  />
                ))}
              </div>

              {/* Auth section for selected provider */}
              {(() => {
                const selectedProvider = LLM_PROVIDERS.find((p) => p.id === llmProvider);
                const isPairable = selectedProvider?.pairable;
                const isOllama = llmProvider === "ollama";

                return (
                  <div className="space-y-3">
                    {/* Pairing button for OAuth-capable providers */}
                    {isPairable && (
                      <button
                        onClick={async () => {
                          try {
                            const resp = await fetch(`${API}/api/oauth/start/${llmProvider}`, { method: "POST" });
                            const data = await resp.json();
                            if (data.auth_url) {
                              window.open(data.auth_url, "_blank");
                              // Poll for completion
                              const poll = setInterval(async () => {
                                try {
                                  const status = await fetch(`${API}/api/oauth/status/${llmProvider}`);
                                  const s = await status.json();
                                  if (s.flow_status === "code_received") {
                                    // Exchange auth code for token
                                    const exchangeRes = await fetch(`${API}/api/oauth/exchange/${llmProvider}`, { method: "POST" });
                                    const result = await exchangeRes.json();
                                    if (result.status === "authenticated") {
                                      clearInterval(poll);
                                      localStorage.setItem(`quantclaw_oauth_${llmProvider}`, "true");
                                      setLlmKey("OAuth connected");
                                    }
                                  } else if (s.authenticated) {
                                    clearInterval(poll);
                                    localStorage.setItem(`quantclaw_oauth_${llmProvider}`, "true");
                                    setLlmKey("OAuth connected");
                                  }
                                } catch {}
                              }, 2000);
                              // Stop polling after 2 minutes
                              setTimeout(() => clearInterval(poll), 120000);
                            } else if (data.error) {
                              // Fallback: open API key page
                              const urls: Record<string, string> = {
                                openai: "https://platform.openai.com/account/api-keys",
                                anthropic: "https://console.anthropic.com/settings/keys",
                                google: "https://aistudio.google.com/apikey",
                              };
                              const url = urls[llmProvider];
                              if (url) window.open(url, "_blank");
                            }
                          } catch {
                            // Fallback: open API key page
                            const urls: Record<string, string> = {
                              openai: "https://platform.openai.com/account/api-keys",
                              anthropic: "https://console.anthropic.com/settings/keys",
                              google: "https://aistudio.google.com/apikey",
                            };
                            const url = urls[llmProvider];
                            if (url) window.open(url, "_blank");
                          }
                        }}
                        className={`w-full flex items-center justify-center gap-2 py-3 rounded-xl border text-sm font-medium transition-all ${
                          llmKey === "OAuth connected"
                            ? "border-green-500/30 bg-green-500/10 text-green-400 cursor-default"
                            : "border-gold/30 bg-gold/5 text-gold hover:bg-gold/10 cursor-pointer"
                        }`}
                      >
                        {llmKey === "OAuth connected" ? (
                          <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M3 8.5L6.5 12L13 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/></svg>
                        ) : (
                          <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M6 2L10 2C11.1 2 12 2.9 12 4V5M4 7H12M4 10H9M3 5H13C13.5523 5 14 5.44772 14 6V13C14 13.5523 13.5523 14 13 14H3C2.44772 14 2 13.5523 2 13V6C2 5.44772 2.44772 5 3 5Z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
                        )}
                        {llmKey === "OAuth connected" ? "Connected" : t.pairWithBrowser}
                      </button>
                    )}

                    {/* Divider between pair and manual key */}
                    {isPairable && (
                      <div className="flex items-center gap-3">
                        <div className="flex-1 h-px bg-keel" />
                        <span className="text-[10px] text-[#2a3a5a] font-mono">{t.orEnterKey}</span>
                        <div className="flex-1 h-px bg-keel" />
                      </div>
                    )}

                    {/* API key input */}
                    {!isOllama && (
                      <div className="space-y-2">
                        <label className="text-xs font-mono text-muted uppercase tracking-wider">
                          {t.apiKey}
                        </label>
                        <input
                          type="password"
                          value={llmKey}
                          onChange={(e) => setLlmKey(e.target.value)}
                          placeholder={`${llmProviderName} API key...`}
                          className="w-full bg-hull/60 border border-trace rounded-xl px-4 py-3 text-sm text-[#a0b0cc] placeholder-[#2a3a5a] outline-none focus:border-gold/30 transition-colors font-mono"
                        />
                      </div>
                    )}

                    {/* Ollama — status check + setup guide */}
                    {isOllama && <OllamaStatus lang={language} />}

                    <p className="text-[11px] text-[#2a3a5a]">
                      {t.storedLocally}
                      {!llmKey && !isOllama && (
                        <button
                          onClick={next}
                          className="ml-2 text-gold/60 hover:text-gold transition-colors"
                        >
                          {t.skipForNow}
                        </button>
                      )}
                    </p>
                  </div>
                );
              })()}
            </div>
          )}

          {/* Step 03: Search Provider */}
          {currentStep === "search" && (
            <div className="animate-fade-up">
              <StepHeader
                number="02"
                title={t.searchStep.title}
                subtitle={t.searchStep.subtitle}
                stepPrefix={t.stepPrefix}
              />

              <div className="space-y-2 mb-6 max-h-[340px] overflow-y-auto pr-1 scrollbar-thin">
                {SEARCH_PROVIDERS.map((p) => (
                  <ProviderCard
                    key={p.id}
                    name={p.name}
                    description={t.searchDescriptions[p.description] || p.description}
                    tag={p.tag ? translateTag(p.tag, t) : undefined}
                    tagRaw={p.tag}
                    selected={searchProvider === p.id}
                    onClick={() => setSearchProvider(p.id)}
                  />
                ))}
              </div>

              {/* Skip / use DuckDuckGo — always visible */}
              <button
                onClick={() => {
                  setSearchProvider("duckduckgo");
                  setSearchKey("");
                  next();
                }}
                className="w-full mb-4 py-3 rounded-xl border border-circuit/30 bg-circuit-light/5 text-circuit-light text-sm font-medium hover:bg-circuit-light/10 transition-all cursor-pointer flex items-center justify-center gap-2"
              >
                <span>🦆</span>
                {t.skipUseDuckDuckGo}
              </button>

              {!keyFreeSearch ? (
                <div className="space-y-2 animate-fade-up">
                  <label className="text-xs font-mono text-muted uppercase tracking-wider">
                    {t.apiKey}
                  </label>
                  <input
                    type="password"
                    value={searchKey}
                    onChange={(e) => setSearchKey(e.target.value)}
                    placeholder={`${searchProviderName} API key...`}
                    className="w-full bg-hull/60 border border-trace rounded-xl px-4 py-3 text-sm text-[#a0b0cc] placeholder-[#2a3a5a] outline-none focus:border-gold/30 transition-colors font-mono"
                  />
                  <p className="text-[11px] text-[#2a3a5a]">
                    {t.fallbackNote}
                  </p>
                </div>
              ) : (
                <div className="mt-2 px-4 py-3 rounded-xl bg-circuit-light/5 border border-circuit/20">
                  <p className="text-xs text-circuit-light/80 font-mono">
                    {t.noKeyRequired}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Step 04: Market Data */}
          {currentStep === "data" && (
            <div className="animate-fade-up">
              <StepHeader
                number="03"
                title={t.dataStep.title}
                subtitle={t.dataStep.subtitle}
                stepPrefix={t.stepPrefix}
              />

              <div className="space-y-6 max-h-[420px] overflow-y-auto pr-1 scrollbar-thin">
                {DATA_CATEGORIES.map((cat) => (
                  <div key={cat.id}>
                    <h3 className="text-xs font-mono text-muted uppercase tracking-wider mb-2 sticky top-0 bg-void py-1 z-10">
                      {t.dataCategories[cat.id] || cat.label}
                    </h3>
                    <div className="space-y-1.5">
                      {cat.providers.map((p) => {
                        const isSelected = dataSources.includes(p.id);
                        const needsKey = !p.free;
                        return (
                          <div key={p.id}>
                            <button
                              onClick={() =>
                                setDataSources((prev) =>
                                  prev.includes(p.id)
                                    ? prev.filter((x) => x !== p.id)
                                    : [...prev, p.id],
                                )
                              }
                              className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl border text-left transition-all duration-200 cursor-pointer ${
                                isSelected
                                  ? "border-gold/40 bg-gold/6"
                                  : "border-trace/40 bg-hull/20 hover:border-trace-glow"
                              }`}
                            >
                              <span
                                className={`w-4 h-4 rounded flex items-center justify-center text-[10px] shrink-0 transition-all ${
                                  isSelected ? "bg-gold text-void" : "bg-keel/60 text-transparent"
                                }`}
                              >
                                ✓
                              </span>
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2">
                                  <span className={`text-sm font-medium ${isSelected ? "text-[#a0b0cc]" : "text-[#6a7a9a]"}`}>
                                    {p.name}
                                  </span>
                                  {p.tag && (
                                    <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded tracking-wide ${
                                      p.tag === "Free" ? "bg-circuit-light/15 text-circuit-light"
                                        : p.tag === "Pro" ? "bg-keel text-muted"
                                        : "bg-keel text-muted"
                                    }`}>
                                      {translateTag(p.tag, t)}
                                    </span>
                                  )}
                                </div>
                                <p className="text-xs text-[#2a3a5a] mt-0.5">{t.dataDescriptions[p.description] || p.description}</p>
                              </div>
                            </button>
                            {isSelected && needsKey && (
                              <div className="mt-1.5 ml-7 flex items-center gap-2" style={{ width: "calc(100% - 1.75rem)" }}>
                                <input
                                  type="password"
                                  value={dataKeys[p.id] || ""}
                                  onChange={(e) => setDataKeys((prev) => ({ ...prev, [p.id]: e.target.value }))}
                                  placeholder={`${p.name} API key...`}
                                  className="flex-1 bg-hull/40 border border-trace/40 rounded-lg px-3 py-2 text-xs text-[#8a9ab0] placeholder-[#2a3a5a] outline-none focus:border-gold/20 transition-colors font-mono"
                                />
                                {p.keyUrl && (
                                  <a
                                    href={p.keyUrl}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="shrink-0 text-[10px] font-mono px-2 py-2 rounded-lg border border-gold/30 text-gold hover:bg-gold/10 transition-colors whitespace-nowrap"
                                  >
                                    Get key &rarr;
                                  </a>
                                )}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>

              <div className="mt-3 space-y-1">
                <p className="text-xs text-[#2a3a5a] font-mono">
                  {dataSources.length} {t.sourcesEnabled}
                  <span className="text-[#1a2a4a]"> · {dataSources.filter((id) => DATA_CATEGORIES.flatMap((c) => c.providers).find((p) => p.id === id)?.free).length} {t.free}</span>
                </p>
                <p className="text-[10px] text-[#1a2a4a]">
                  {t.autoUpgradeNote}
                </p>
              </div>
            </div>
          )}

          {/* Step 05: Broker */}
          {currentStep === "broker" && (
            <div className="animate-fade-up">
              <StepHeader
                number="04"
                title={t.brokerStep.title}
                subtitle={t.brokerStep.subtitle}
                stepPrefix={t.stepPrefix}
              />

              <div className="space-y-2 mb-6">
                <ProviderCard
                  name={t.paperTrading}
                  description={t.paperTradingDesc}
                  tag={t.recommended}
                  selected={brokerType === "paper"}
                  onClick={() => setBrokerType("paper")}
                />
                <ProviderCard
                  name="Alpaca"
                  description={t.alpacaDesc}
                  selected={brokerType === "alpaca"}
                  onClick={() => setBrokerType("alpaca")}
                />
                <ProviderCard
                  name="Interactive Brokers"
                  description={t.ibkrDesc}
                  tag={t.pro}
                  selected={brokerType === "ibkr"}
                  onClick={() => setBrokerType("ibkr")}
                />
              </div>

              {brokerType !== "paper" && (
                <div className="space-y-3 animate-fade-up">
                  <div className="space-y-2">
                    <label className="text-xs font-mono text-muted uppercase tracking-wider">{t.apiKey}</label>
                    <input
                      type="password"
                      value={brokerKey}
                      onChange={(e) => setBrokerKey(e.target.value)}
                      placeholder="API key..."
                      className="w-full bg-hull/60 border border-trace rounded-xl px-4 py-3 text-sm text-[#a0b0cc] placeholder-[#2a3a5a] outline-none focus:border-gold/30 transition-colors font-mono"
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-xs font-mono text-muted uppercase tracking-wider">{t.secretKey}</label>
                    <input
                      type="password"
                      value={brokerSecret}
                      onChange={(e) => setBrokerSecret(e.target.value)}
                      placeholder="Secret key..."
                      className="w-full bg-hull/60 border border-trace rounded-xl px-4 py-3 text-sm text-[#a0b0cc] placeholder-[#2a3a5a] outline-none focus:border-gold/30 transition-colors font-mono"
                    />
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Step 06: Watchlist */}
          {currentStep === "watchlist" && (
            <div className="animate-fade-up">
              <StepHeader
                number="05"
                title={t.watchlistStep.title}
                subtitle={t.watchlistStep.subtitle}
                stepPrefix={t.stepPrefix}
              />

              <div className="flex gap-2 mb-4">
                {PRESETS.map((preset, i) => {
                  const globalNames = [t.presetMag7, t.presetIndexETFs, t.presetBlueChips];
                  const displayName = isChina ? preset.name : (globalNames[i] || preset.name);
                  return (
                    <button
                      key={preset.name}
                      onClick={() => applyPreset(preset.tickers)}
                      className="px-3 py-1.5 rounded-lg border border-trace bg-hull/40 text-xs text-[#6a7a9a] hover:border-gold/30 hover:text-gold-light transition-all cursor-pointer"
                    >
                      + {displayName}
                    </button>
                  );
                })}
              </div>

              <div className="grid grid-cols-3 gap-2 mb-4">
                {TICKERS.map((tk) => {
                  const isSelected = watchlist.includes(tk.symbol);
                  return (
                    <button
                      key={tk.symbol}
                      onClick={() => toggleTicker(tk.symbol)}
                      className={`flex items-center gap-2.5 px-3 py-2.5 rounded-xl border text-left text-sm transition-all duration-200 cursor-pointer ${
                        isSelected
                          ? "border-gold/40 bg-gold/8 text-[#a0b0cc]"
                          : "border-trace/60 bg-hull/30 text-muted hover:border-trace-glow hover:text-[#6a7a9a]"
                      }`}
                    >
                      <span
                        className={`w-4 h-4 rounded flex items-center justify-center text-[10px] shrink-0 transition-all ${
                          isSelected ? "bg-gold text-void" : "bg-keel/60 text-transparent"
                        }`}
                      >
                        ✓
                      </span>
                      <div className="min-w-0">
                        <span className="font-mono font-medium text-xs">{tk.symbol}</span>
                        <span className="text-[#2a3a5a] text-[10px] ml-1.5">{tk.name}</span>
                      </div>
                    </button>
                  );
                })}
              </div>

              <div className="flex gap-2">
                <input
                  value={customTicker}
                  onChange={(e) => setCustomTicker(e.target.value.toUpperCase())}
                  onKeyDown={(e) => e.key === "Enter" && addCustomTicker()}
                  placeholder={t.addCustomTicker}
                  className="flex-1 bg-hull/60 border border-trace rounded-xl px-4 py-2.5 text-sm text-[#a0b0cc] placeholder-[#2a3a5a] outline-none focus:border-gold/30 transition-colors font-mono"
                />
                <button
                  onClick={addCustomTicker}
                  disabled={!customTicker.trim()}
                  className="px-4 py-2.5 rounded-xl bg-keel text-[#6a7a9a] text-sm hover:bg-trace-glow disabled:opacity-40 disabled:cursor-not-allowed transition-all cursor-pointer"
                >
                  {t.add}
                </button>
              </div>

              <p className="text-xs text-[#2a3a5a] mt-3 font-mono">
                {watchlist.length} {t.tickersSelected}
                {watchlist.length > 0 && (
                  <span className="text-[#1a2a4a]"> — {watchlist.join(", ")}</span>
                )}
              </p>
            </div>
          )}

          {/* Step 07: Launch */}
          {currentStep === "launch" && (
            <div className="animate-fade-up">
              {!launched ? (
                <>
                  <StepHeader
                    number="06"
                    title={t.launchStep.title}
                    subtitle={t.launchStep.subtitle}
                    stepPrefix={t.stepPrefix}
                  />

                  <div className="space-y-3 mb-8">
                    <ReviewRow
                      label={t.reviewLanguage}
                      value={LANG_NAMES[language] || "English"}
                      status="configured"
                      t={t}
                    />
                    <ReviewRow
                      label={t.reviewModel}
                      value={llmProviderName}
                      status={llmKey || llmProvider === "ollama" ? "configured" : "skipped"}
                      t={t}
                    />
                    <ReviewRow
                      label={t.reviewSearch}
                      value={searchKey || keyFreeSearch ? searchProviderName : `DuckDuckGo (fallback)`}
                      status="configured"
                      t={t}
                    />
                    <ReviewRow
                      label={t.reviewData}
                      value={`${dataSources.length} ${t.sourcesEnabled}`}
                      status="configured"
                      t={t}
                    />
                    <ReviewRow
                      label={t.reviewBroker}
                      value={brokerType === "paper" ? t.paperTrading : brokerType === "alpaca" ? "Alpaca" : "Interactive Brokers"}
                      status={brokerType === "paper" || brokerKey ? "configured" : "skipped"}
                      t={t}
                    />
                    <ReviewRow
                      label={t.reviewWatchlist}
                      value={`${watchlist.length} ${t.tickersSelected}`}
                      status="configured"
                      t={t}
                    />
                  </div>

                  {!launching ? (
                    <button
                      onClick={handleLaunch}
                      className="w-full py-4 rounded-2xl bg-gold text-void font-semibold text-base tracking-wide hover:bg-gold-light hover:shadow-lg hover:shadow-gold/20 transition-all duration-300 cursor-pointer"
                    >
                      {t.launchButton}
                    </button>
                  ) : (
                    <div className="w-full py-4 rounded-2xl border border-gold/30 bg-gold/5 text-center">
                      <div className="flex items-center justify-center gap-3">
                        <span className="w-5 h-5 border-2 border-gold border-t-transparent rounded-full animate-spin" />
                        <span className="text-gold font-medium">{t.initializingAgents}</span>
                      </div>
                      <div className="mt-3 flex justify-center gap-1">
                        {[0, 1, 2, 3, 4, 5].map((i) => (
                          <div key={i} className="h-1 w-8 rounded-full bg-gold/20 overflow-hidden">
                            <div
                              className="h-full bg-gold rounded-full"
                              style={{ animation: `launch-bar 2s ease-out ${i * 0.3}s both` }}
                            />
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="text-center animate-scale-in">
                  <div className="text-5xl mb-4">🚀</div>
                  <h2 className="text-3xl font-bold mb-2" style={{ fontFamily: "var(--font-display)" }}>
                    {t.youreLive}
                  </h2>
                  <p className="text-muted">{t.redirecting}</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Navigation */}
      {currentStep !== "launch" && (
        <div className="flex items-center justify-between px-4 pb-8 max-w-xl mx-auto w-full">
          <button
            onClick={prev}
            disabled={currentIndex === 0}
            className="px-5 py-2.5 rounded-xl text-sm text-muted hover:text-[#8a9ab0] disabled:opacity-0 disabled:cursor-default transition-all cursor-pointer"
          >
            {t.back}
          </button>
          <button
            onClick={next}
            disabled={!canProceed()}
            className={`px-6 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 ${
              canProceed()
                ? "bg-gold text-void hover:bg-gold-light cursor-pointer"
                : "bg-keel/50 text-[#2a3a5a] cursor-not-allowed"
            }`}
          >
            {t.continue_}
          </button>
        </div>
      )}

      {currentStep === "launch" && !launching && !launched && (
        <div className="flex justify-center pb-8">
          <button
            onClick={prev}
            className="px-5 py-2.5 rounded-xl text-sm text-muted hover:text-[#8a9ab0] transition-all cursor-pointer"
          >
            {t.back}
          </button>
        </div>
      )}

      <style jsx>{`
        @keyframes launch-bar {
          from { width: 0%; }
          to { width: 100%; }
        }
        .scrollbar-thin::-webkit-scrollbar {
          width: 4px;
        }
        .scrollbar-thin::-webkit-scrollbar-track {
          background: transparent;
        }
        .scrollbar-thin::-webkit-scrollbar-thumb {
          background: rgba(107, 114, 128, 0.3);
          border-radius: 2px;
        }
      `}</style>
    </div>
  );
}

const ollamaI18n: Record<string, { checking: string; connected: string; modelsAvail: string; notRunning: string; installSteps: string[]; pullModel: string; pulling: string; pullDone: string }> = {
  en: {
    checking: "Checking Ollama connection...",
    connected: "Ollama is running",
    modelsAvail: "model(s) available",
    notRunning: "Ollama is not running",
    installSteps: [
      "1. Download Ollama from ollama.com",
      "2. Install and run it",
      "3. Pull a model: ollama pull qwen3:8b",
      "4. Come back here — it will auto-detect",
    ],
    pullModel: "Pull recommended model",
    pulling: "Pulling model...",
    pullDone: "Model ready!",
  },
  zh: {
    checking: "正在检查 Ollama 连接...",
    connected: "Ollama 运行中",
    modelsAvail: "个模型可用",
    notRunning: "Ollama 未运行",
    installSteps: [
      "1. 从 ollama.com 下载 Ollama",
      "2. 安装并运行",
      "3. 拉取模型：ollama pull qwen3:8b",
      "4. 返回此页面 — 会自动检测",
    ],
    pullModel: "拉取推荐模型",
    pulling: "正在拉取模型...",
    pullDone: "模型就绪！",
  },
  ja: {
    checking: "Ollama 接続を確認中...",
    connected: "Ollama 稼働中",
    modelsAvail: "モデルが利用可能",
    notRunning: "Ollama が実行されていません",
    installSteps: [
      "1. ollama.com から Ollama をダウンロード",
      "2. インストールして実行",
      "3. モデルを取得：ollama pull qwen3:8b",
      "4. このページに戻る — 自動検出されます",
    ],
    pullModel: "推奨モデルを取得",
    pulling: "モデルを取得中...",
    pullDone: "モデル準備完了！",
  },
};

function OllamaStatus({ lang }: { lang: string }) {
  const ot = ollamaI18n[lang] || ollamaI18n.en;
  const [status, setStatus] = useState<"checking" | "connected" | "disconnected">("checking");
  const [models, setModels] = useState<string[]>([]);

  useEffect(() => {
    let interval: ReturnType<typeof setInterval>;

    const check = async () => {
      try {
        const res = await fetch("http://localhost:11434/api/tags", { signal: AbortSignal.timeout(3000) });
        if (res.ok) {
          const data = await res.json();
          const modelNames = (data.models || []).map((m: { name: string }) => m.name);
          setModels(modelNames);
          setStatus("connected");
        } else {
          setStatus("disconnected");
        }
      } catch {
        setStatus("disconnected");
      }
    };

    check();
    // Re-check every 5s in case user installs/starts Ollama
    interval = setInterval(check, 5000);
    return () => clearInterval(interval);
  }, []);

  if (status === "checking") {
    return (
      <div className="px-4 py-3 rounded-xl bg-hull/40 border border-trace/40">
        <p className="text-xs text-muted font-mono flex items-center gap-2">
          <span className="w-3 h-3 border-2 border-muted border-t-transparent rounded-full animate-spin" />
          {ot.checking}
        </p>
      </div>
    );
  }

  if (status === "connected") {
    return (
      <div className="px-4 py-3 rounded-xl bg-circuit-light/5 border border-circuit/20 space-y-2">
        <p className="text-xs text-circuit-light font-mono flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-circuit-light" />
          {ot.connected} — {models.length} {ot.modelsAvail}
        </p>
        {models.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {models.map((m) => (
              <span key={m} className="text-[10px] font-mono text-[#6a7a9a] bg-keel/60 px-2 py-0.5 rounded">
                {m}
              </span>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="px-4 py-4 rounded-xl bg-gold/5 border border-gold/20 space-y-3">
      <p className="text-xs text-gold font-medium flex items-center gap-2">
        <span className="w-1.5 h-1.5 rounded-full bg-gold" />
        {ot.notRunning}
      </p>
      <div className="space-y-1.5">
        {ot.installSteps.map((step, i) => (
          <p key={i} className="text-xs text-muted font-mono">
            {step}
          </p>
        ))}
      </div>
      <a
        href="https://ollama.com/download"
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1.5 text-xs text-gold hover:text-gold-light transition-colors"
      >
        ollama.com/download ↗
      </a>
    </div>
  );
}

function StepHeader({ number, title, subtitle, stepPrefix }: { number: string; title: string; subtitle: string; stepPrefix?: string }) {
  return (
    <div className="mb-8">
      <span className="text-[11px] font-mono text-gold/60 tracking-widest uppercase">{stepPrefix || "Step"} {number}</span>
      <h2 className="text-2xl font-bold tracking-tight mt-1 mb-2" style={{ fontFamily: "var(--font-display)" }}>
        {title}
      </h2>
      <p className="text-sm text-muted leading-relaxed">{subtitle}</p>
    </div>
  );
}

function ProviderCard({ name, description, tag, selected, onClick, tagRaw }: {
  name: string; description: string; tag?: string; selected: boolean; onClick: () => void; tagRaw?: string;
}) {
  const displayTag = tag;
  const styleTag = tagRaw || tag;
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-4 p-4 rounded-xl border text-left transition-all duration-200 cursor-pointer ${
        selected
          ? "border-gold/40 bg-gold/6"
          : "border-trace/60 bg-hull/30 hover:border-trace-glow"
      }`}
    >
      <span
        className={`w-4 h-4 rounded-full border-2 shrink-0 flex items-center justify-center transition-all ${
          selected ? "border-gold" : "border-trace-glow"
        }`}
      >
        {selected && <span className="w-2 h-2 rounded-full bg-gold" />}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className={`text-sm font-medium ${selected ? "text-[#a0b0cc]" : "text-[#6a7a9a]"}`}>{name}</span>
          {displayTag && (
            <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded tracking-wide ${
              styleTag === "Recommended" ? "bg-gold/15 text-gold"
                : styleTag === "Free" ? "bg-circuit-light/15 text-circuit-light"
                : styleTag === "Fast" ? "bg-cyan-500/15 text-cyan-500"
                : styleTag === "Local" ? "bg-violet-500/15 text-violet-500"
                : styleTag === "Self-hosted" ? "bg-violet-500/15 text-violet-500"
                : "bg-keel text-muted"
            }`}>
              {displayTag}
            </span>
          )}
        </div>
        <p className="text-xs text-[#2a3a5a] mt-0.5">{description}</p>
      </div>
    </button>
  );
}

function ReviewRow({ label, value, status, t }: { label: string; value: string; status: "configured" | "skipped"; t: ReturnType<typeof useTranslations> }) {
  return (
    <div className="flex items-center justify-between p-3.5 rounded-xl bg-hull/40 border border-trace/40">
      <div>
        <p className="text-xs text-muted font-mono uppercase tracking-wider">{label}</p>
        <p className="text-sm text-[#8a9ab0] mt-0.5">{value}</p>
      </div>
      <span className={`text-[10px] font-mono px-2 py-0.5 rounded ${
        status === "configured" ? "bg-circuit-light/10 text-circuit-light" : "bg-keel text-muted"
      }`}>
        {status === "configured" ? t.configured : t.skipped}
      </span>
    </div>
  );
}
