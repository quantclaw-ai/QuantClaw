"use client";
import { createContext, useContext, useState, useEffect, type ReactNode } from "react";

type Lang = "en" | "zh" | "ja";

interface LangContextValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
}

const LangContext = createContext<LangContextValue>({ lang: "en", setLang: () => {} });

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("quantclaw_lang") as Lang | null;
    if (stored && ["en", "zh", "ja"].includes(stored)) {
      setLangState(stored);
    }
    setLoaded(true);
  }, []);

  const setLang = (newLang: Lang) => {
    setLangState(newLang);
    localStorage.setItem("quantclaw_lang", newLang);
  };

  if (!loaded) return null;

  return (
    <LangContext.Provider value={{ lang, setLang }}>
      {children}
    </LangContext.Provider>
  );
}

export function useLang(): LangContextValue {
  return useContext(LangContext);
}
