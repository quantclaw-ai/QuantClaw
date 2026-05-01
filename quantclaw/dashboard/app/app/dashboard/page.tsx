"use client";
import { useEffect, useState } from "react";
import { useLang } from "../lang-context";
import { TradingFloor } from "./floor/TradingFloor";
import { ChatPanel } from "./floor/ChatPanel";
import { FloorOverlay } from "./floor/FloorOverlay";
import { useFloorEvents } from "./floor/useFloorEvents";
import { STATIONS } from "./floor/stations";
import type { FloorAgent, VisualMode } from "./floor/types";

const API = "http://localhost:24120";

export default function DashboardHome() {
  const { lang } = useLang();
  const [mode, setMode] = useState<VisualMode>(() => {
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("quantclaw_floor_mode");
      // Migrate legacy "isometric" setting -> "modern".
      if (saved === "pixel" || saved === "modern") return saved;
      if (saved === "isometric") localStorage.setItem("quantclaw_floor_mode", "modern");
      return "modern";
    }
    return "modern";
  });
  // Build agent slots from STATIONS so the floor always has something
  // to render — even immediately on mount before /api/agents responds,
  // and even if the backend is unreachable. Without this, navigating
  // away and back briefly (or permanently, if the backend is down)
  // leaves the floor blank with "0 active 0 idle 0 agents" because
  // ``useState([])`` is the source of truth until fetch resolves.
  const buildAgentSlots = (apiAgents: { name: string; enabled?: boolean }[] | null): FloorAgent[] =>
    STATIONS.map((station) => {
      const apiAgent = apiAgents?.find((a) => a.name === station.name);
      // When the API call hasn't resolved yet (apiAgents === null), assume
      // enabled — better to show everything live and let the API correct
      // it than to show nothing. Once apiAgents is populated, honor the
      // server's enabled flag (some agents may be disabled by config).
      const enabled = apiAgents === null ? true : (apiAgent?.enabled ?? false);
      return {
        name: station.name,
        displayName: station.displayName,
        enabled,
        locked: !enabled,
        state: "idle" as const,
        progress: 0,
        speechBubble: null,
        logHistory: [],
        zone: station.zone,
        x: station.x,
        y: station.y,
      };
    });

  const [rawAgents, setRawAgents] = useState<FloorAgent[]>(() => buildAgentSlots(null));
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);

  // Fetch agent data from API to honor server-side enabled flags. We
  // start from the STATIONS fallback above so the floor never blanks
  // while this is in flight.
  useEffect(() => {
    fetch(`${API}/api/agents`)
      .then((r) => r.json())
      .then((data) => setRawAgents(buildAgentSlots(data.agents || [])))
      .catch(() => { /* keep the optimistic slots from useState */ });
  }, []);

  // Wire up real-time WebSocket events
  const { agents } = useFloorEvents(rawAgents);

  const handleModeChange = (newMode: VisualMode) => {
    setMode(newMode);
    localStorage.setItem("quantclaw_floor_mode", newMode);
  };

  const handleAgentClick = (agentName: string) => {
    setSelectedAgent(agentName);
  };

  const [chatWidth, setChatWidth] = useState(() => {
    if (typeof window !== "undefined") {
      return parseInt(localStorage.getItem("quantclaw_chat_width") || "480", 10);
    }
    return 480;
  });
  const [dragging, setDragging] = useState(false);

  const handleDragStart = () => setDragging(true);

  useEffect(() => {
    if (!dragging) return;
    const handleMove = (e: MouseEvent) => {
      const newWidth = Math.max(350, Math.min(800, window.innerWidth - e.clientX));
      setChatWidth(newWidth);
    };
    const handleUp = () => {
      setDragging(false);
      localStorage.setItem("quantclaw_chat_width", String(chatWidth));
    };
    window.addEventListener("mousemove", handleMove);
    window.addEventListener("mouseup", handleUp);
    return () => {
      window.removeEventListener("mousemove", handleMove);
      window.removeEventListener("mouseup", handleUp);
    };
  }, [dragging, chatWidth]);

  return (
    <div className="flex h-[calc(100vh-48px)]">
      {/* Trading Floor Canvas */}
      <div className="flex-1 relative min-w-0">
        <TradingFloor
          agents={agents}
          mode={mode}
          onAgentClick={handleAgentClick}
          selectedAgent={selectedAgent}
        />
        <FloorOverlay
          mode={mode}
          onModeChange={handleModeChange}
          agents={agents}
        />
      </div>

      {/* Resize Handle */}
      <div
        onMouseDown={handleDragStart}
        className={`w-1.5 cursor-col-resize transition-colors ${dragging ? "bg-gold/50" : "bg-trace"}`}
        style={{
          background: dragging
            ? "linear-gradient(180deg, rgba(212,165,23,0.4), rgba(12,122,148,0.3))"
            : undefined,
        }}
      />

      {/* Chat Panel */}
      <div style={{ width: chatWidth }} className="min-w-[350px] max-w-[800px] flex-shrink-0">
        <ChatPanel
          agents={agents}
          selectedAgent={selectedAgent}
          onAgentSelect={handleAgentClick}
        />
      </div>
    </div>
  );
}
