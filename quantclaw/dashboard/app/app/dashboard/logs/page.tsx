"use client";
import { useState, useEffect, useCallback } from "react";

const API_URL = "http://localhost:24120/api/events";
const POLL_INTERVAL = 5000;

interface EventEntry {
  type: string;
  payload: Record<string, unknown>;
  source_agent: string;
  timestamp: string;
}

const EVENT_TYPE_OPTIONS = [
  { label: "All Events", value: "" },
  { label: "Orchestration", value: "orchestration.*" },
  { label: "Agent", value: "agent.*" },
  { label: "Chat", value: "chat.*" },
  { label: "Market", value: "market.*" },
  { label: "Trade", value: "trade.*" },
];

const AGENT_OPTIONS = [
  "", "scheduler", "researcher", "validator", "miner",
  "ingestor", "executor", "reporter", "trainer",
  "risk_monitor", "sentinel", "compliance", "debugger",
];

const TIME_RANGES = [
  { label: "All", value: "" },
  { label: "Today", value: "today" },
  { label: "Last 24h", value: "24h" },
  { label: "Last 7d", value: "7d" },
];

function getSinceDate(range: string): string {
  if (!range) return "";
  const now = new Date();
  if (range === "today") {
    return now.toISOString().split("T")[0];
  }
  if (range === "24h") {
    return new Date(now.getTime() - 24 * 60 * 60 * 1000).toISOString();
  }
  if (range === "7d") {
    return new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000).toISOString();
  }
  return "";
}

function formatPayload(payload: Record<string, unknown>): string {
  const parts: string[] = [];
  if (payload.reasoning) parts.push(String(payload.reasoning));
  if (payload.verdict) parts.push(`Verdict: ${payload.verdict}`);
  if (payload.message) parts.push(String(payload.message));
  if (payload.exploration_mode) parts.push(`Mode: ${payload.exploration_mode} (temp ${payload.temperature})`);
  if (payload.sharpe || payload.result_summary) {
    const summary = (payload.result_summary || payload) as Record<string, unknown>;
    if (summary.sharpe) parts.push(`Sharpe: ${summary.sharpe}`);
  }
  if (payload.error) parts.push(`Error: ${payload.error}`);
  if (parts.length === 0) {
    const str = JSON.stringify(payload);
    return str.length > 200 ? str.slice(0, 200) + "..." : str;
  }
  return parts.join(" | ");
}

function typeColor(type: string): string {
  if (type.startsWith("orchestration.")) return "#0ea5e9";
  if (type.startsWith("agent.task_completed")) return "#14b8a6";
  if (type.startsWith("agent.task_failed")) return "#dc3545";
  if (type.startsWith("agent.")) return "#a78bfa";
  if (type.startsWith("chat.")) return "#d4a517";
  if (type.startsWith("market.")) return "#ec4899";
  return "#4a5a7a";
}

export default function LogsPage() {
  const [events, setEvents] = useState<EventEntry[]>([]);
  const [typeFilter, setTypeFilter] = useState("");
  const [agentFilter, setAgentFilter] = useState("");
  const [timeRange, setTimeRange] = useState("");

  const fetchEvents = useCallback(async () => {
    const params = new URLSearchParams();
    params.set("limit", "100");
    if (typeFilter) params.set("type", typeFilter);
    if (agentFilter) params.set("agent", agentFilter);
    const since = getSinceDate(timeRange);
    if (since) params.set("since", since);

    try {
      const resp = await fetch(`${API_URL}?${params}`);
      const data = await resp.json();
      setEvents((data.events || []).reverse());
    } catch {
      // Silently handle fetch errors
    }
  }, [typeFilter, agentFilter, timeRange]);

  useEffect(() => {
    fetchEvents();
    const interval = setInterval(fetchEvents, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchEvents]);

  const selectStyle = {
    background: "var(--color-keel)",
    color: "#8a9ab0",
    border: "1px solid var(--color-trace)",
    padding: "6px 10px",
    borderRadius: 8,
    fontSize: 12,
    fontFamily: "var(--font-mono)",
  };

  return (
    <div style={{ padding: "24px", fontFamily: "var(--font-mono)", color: "#c8d1db", maxWidth: 900 }}>
      <h1 style={{ fontSize: 24, marginBottom: 16, fontFamily: "var(--font-display)", color: "var(--color-gold)" }}>Logs</h1>

      <div style={{ display: "flex", gap: 12, marginBottom: 20 }}>
        <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} style={selectStyle}>
          {EVENT_TYPE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <select value={agentFilter} onChange={(e) => setAgentFilter(e.target.value)} style={selectStyle}>
          <option value="">All Agents</option>
          {AGENT_OPTIONS.filter(Boolean).map((a) => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>
        <select value={timeRange} onChange={(e) => setTimeRange(e.target.value)} style={selectStyle}>
          {TIME_RANGES.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        {events.length === 0 && (
          <div style={{ color: "var(--color-muted)", padding: 20, textAlign: "center" }}>No events found</div>
        )}
        {events.map((e, i) => {
          const time = new Date(e.timestamp).toLocaleTimeString();
          return (
            <div key={i} style={{
              padding: "8px 12px",
              borderLeftWidth: 3,
              borderLeftColor: typeColor(e.type),
              borderLeftStyle: "solid",
              borderRightWidth: 1,
              borderRightColor: "var(--color-trace)",
              borderRightStyle: "solid",
              borderTopWidth: 1,
              borderTopColor: "var(--color-trace)",
              borderTopStyle: "solid",
              borderBottomWidth: 1,
              borderBottomColor: "var(--color-trace)",
              borderBottomStyle: "solid",
              background: "var(--color-hull)",
              borderRadius: 6,
              fontSize: 13,
            }}>
              <div style={{ display: "flex", gap: 12, color: "var(--color-muted)" }}>
                <span>{time}</span>
                <span style={{ color: "#8a9ab0" }}>{e.source_agent || "\u2014"}</span>
                <span style={{ color: typeColor(e.type) }}>{e.type}</span>
              </div>
              <div style={{ color: "#8a9ab0", marginTop: 4, fontSize: 12 }}>
                {formatPayload(e.payload)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
