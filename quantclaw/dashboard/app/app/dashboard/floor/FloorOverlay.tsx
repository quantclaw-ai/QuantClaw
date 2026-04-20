"use client";
import { useLang } from "../../lang-context";
import type { FloorAgent, VisualMode } from "./types";

type Lang = "en" | "zh" | "ja";

const overlayI18n: Record<Lang, {
  pixel: string;
  modern: string;
  active: string;
  idle: string;
  locked: string;
  agents: string;
}> = {
  en: {
    pixel: "Pixel",
    modern: "Modern",
    active: "Active",
    idle: "Idle",
    locked: "Locked",
    agents: "agents",
  },
  zh: {
    pixel: "像素",
    modern: "现代",
    active: "活跃",
    idle: "空闲",
    locked: "锁定",
    agents: "代理",
  },
  ja: {
    pixel: "ピクセル",
    modern: "モダン",
    active: "アクティブ",
    idle: "アイドル",
    locked: "ロック",
    agents: "エージェント",
  },
};

interface FloorOverlayProps {
  mode: VisualMode;
  onModeChange: (mode: VisualMode) => void;
  agents: FloorAgent[];
}

const MODE_ICONS: Record<VisualMode, React.ReactNode> = {
  modern: (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
      <rect x="1" y="1" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.2" fill="none" />
      <rect x="8" y="1" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.2" fill="none" />
      <rect x="1" y="8" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.2" fill="none" />
      <rect x="8" y="8" width="5" height="5" rx="1" stroke="currentColor" strokeWidth="1.2" fill="none" />
    </svg>
  ),
  pixel: (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
      <rect x="1" y="1" width="4" height="4" fill="currentColor" />
      <rect x="5" y="5" width="4" height="4" fill="currentColor" />
      <rect x="9" y="1" width="4" height="4" fill="currentColor" />
      <rect x="1" y="9" width="4" height="4" fill="currentColor" />
      <rect x="9" y="9" width="4" height="4" fill="currentColor" />
    </svg>
  ),
};

const MODE_LABELS: Record<VisualMode, keyof typeof overlayI18n.en> = {
  modern: "modern",
  pixel: "pixel",
};

export function FloorOverlay({ mode, onModeChange, agents }: FloorOverlayProps) {
  const { lang } = useLang();
  const t = overlayI18n[lang as Lang] || overlayI18n.en;

  const activeCount = agents.filter((a) => a.state !== "idle").length;
  const idleCount = agents.filter((a) => !a.locked && a.state === "idle").length;
  const lockedCount = agents.filter((a) => a.locked && a.state === "idle").length;

  const modes: VisualMode[] = ["modern", "pixel"];

  return (
    <div className="absolute inset-0 pointer-events-none">
      {/* Top-left: Visual mode toggles */}
      <div className="absolute top-3 left-3 pointer-events-auto">
        <div className="flex items-center gap-1 bg-void/80 backdrop-blur-sm border border-trace rounded-xl p-1">
          {modes.map((m) => {
            const isActive = mode === m;
            const label = t[MODE_LABELS[m]];
            return (
              <button
                key={m}
                onClick={() => onModeChange(m)}
                className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-medium transition-all duration-200 cursor-pointer ${
                  isActive
                    ? "bg-gold/15 text-gold border border-gold/30"
                    : "text-muted hover:text-[#a0b0cc] border border-transparent hover:bg-keel/50"
                }`}
              >
                {MODE_ICONS[m]}
                <span>{label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Bottom: Status bar */}
      <div className="absolute bottom-3 left-3 right-3 pointer-events-auto">
        <div className="flex items-center justify-between bg-void/80 backdrop-blur-sm border border-trace rounded-xl px-4 py-2">
          <div className="flex items-center gap-4">
            {/* Active agents */}
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-gold animate-pulse" />
              <span className="text-[11px] font-mono text-gold">
                {activeCount}
              </span>
              <span className="text-[11px] font-mono text-muted">
                {t.active}
              </span>
            </div>

            <div className="w-px h-3 bg-trace" />

            {/* Idle agents */}
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-circuit-light" />
              <span className="text-[11px] font-mono text-circuit-light">
                {idleCount}
              </span>
              <span className="text-[11px] font-mono text-muted">
                {t.idle}
              </span>
            </div>

            <div className="w-px h-3 bg-trace" />

            {/* Locked agents */}
            <div className="flex items-center gap-2">
              <svg className="w-3 h-3 text-[#2a3a5a]" viewBox="0 0 16 16" fill="currentColor">
                <path d="M8 1a4 4 0 0 0-4 4v2H3a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V8a1 1 0 0 0-1-1h-1V5a4 4 0 0 0-4-4zm2 6H6V5a2 2 0 1 1 4 0v2z" />
              </svg>
              <span className="text-[11px] font-mono text-[#2a3a5a]">
                {lockedCount}
              </span>
              <span className="text-[11px] font-mono text-muted">
                {t.locked}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            <span className="text-[11px] font-mono text-muted">
              {agents.length} {t.agents}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
