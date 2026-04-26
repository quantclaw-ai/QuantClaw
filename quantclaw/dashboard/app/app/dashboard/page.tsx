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
  const [rawAgents, setRawAgents] = useState<FloorAgent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);

  // Fetch agent data from API
  useEffect(() => {
    fetch(`${API}/api/agents`)
      .then((r) => r.json())
      .then((data) => {
        const apiAgents = data.agents || [];
        const floorAgents: FloorAgent[] = STATIONS.map((station) => {
          const apiAgent = apiAgents.find((a: { name: string }) => a.name === station.name);
          return {
            name: station.name,
            displayName: station.displayName,
            enabled: apiAgent?.enabled ?? false,
            locked: !(apiAgent?.enabled ?? false),
            state: "idle" as const,
            progress: 0,
            speechBubble: null,
            logHistory: [],
            zone: station.zone,
            x: station.x,
            y: station.y,
          };
        });
        setRawAgents(floorAgents);
      })
      .catch(() => {
        // Fallback: show all agents as idle
        const fallback: FloorAgent[] = STATIONS.map((station) => ({
          name: station.name,
          displayName: station.displayName,
          enabled: true,
          locked: false,
          state: "idle" as const,
          progress: 0,
          speechBubble: null,
          logHistory: [],
          zone: station.zone,
          x: station.x,
          y: station.y,
        }));
        setRawAgents(fallback);
      });
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

  // Initialize to the default on both server and client to avoid hydration
  // mismatch; the saved width is applied in the effect below after mount.
  const [chatWidth, setChatWidth] = useState(480);
  useEffect(() => {
    const saved = localStorage.getItem("quantclaw_chat_width");
    if (saved) setChatWidth(parseInt(saved, 10));
  }, []);
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
