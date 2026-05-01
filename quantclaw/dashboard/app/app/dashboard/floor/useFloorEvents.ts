"use client";
import { useEffect, useRef, useCallback, useState } from "react";
import type { AgentLogEntry, FloorAgent, FloorEvent, LogKind } from "./types";
import { STATIONS } from "./stations";

const WS_URL = "ws://localhost:24120/ws/events";
const POLL_URL = "http://localhost:24120/api/events";
const POLL_INTERVAL = 3000;
const RECONNECT_DELAY = 2000;
const SPEECH_BUBBLE_DURATION = 8000;
const MAX_LOG_ENTRIES = 5;

function pushLog(history: AgentLogEntry[], text: string, kind: LogKind): AgentLogEntry[] {
  const trimmed = text.trim();
  if (!trimmed) return history;
  // Dedupe against the newest entry so rapid duplicates don't spam the strip.
  if (history.length > 0 && history[0].text === trimmed && history[0].kind === kind) {
    return history;
  }
  const next: AgentLogEntry = { text: trimmed, kind, ts: Date.now() };
  return [next, ...history].slice(0, MAX_LOG_ENTRIES);
}

export function useFloorEvents(
  initialAgents: FloorAgent[],
): {
  agents: FloorAgent[];
  broadcastOrigin: { x: number; y: number } | null;
} {
  const [agents, setAgents] = useState<FloorAgent[]>(initialAgents);
  const [broadcastOrigin, setBroadcastOrigin] = useState<{ x: number; y: number } | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const initialAgentsRef = useRef(initialAgents);
  const lastTimestampRef = useRef("");
  const seenEventKeysRef = useRef<string[]>([]);
  const seenEventSetRef = useRef(new Set<string>());

  useEffect(() => {
    initialAgentsRef.current = initialAgents;
  }, [initialAgents]);

  const mergeAgents = useCallback((baseAgents: FloorAgent[], liveAgents: FloorAgent[]) => (
    baseAgents.map((agent) => {
      const existing = liveAgents.find((candidate) => candidate.name === agent.name);
      if (!existing) {
        return agent;
      }
      return {
        ...agent,
        state: existing.state,
        progress: existing.progress,
        speechBubble: existing.speechBubble,
        speechBubbleTimeout: existing.speechBubbleTimeout,
        logHistory: existing.logHistory ?? agent.logHistory ?? [],
      };
    })
  ), []);

  const handleEvent = useCallback((event: FloorEvent) => {
    setAgents((prev) => {
      const updated = initialAgentsRef.current.length > 0
        ? mergeAgents(initialAgentsRef.current, prev)
        : [...prev];
      const idx = updated.findIndex((a) => a.name === event.agent);

      switch (event.type) {
        case "agent.task.started":
          if (idx >= 0) {
            const msg = event.message || "Working...";
            updated[idx] = {
              ...updated[idx],
              state: "busy",
              progress: 0,
              speechBubble: msg,
              logHistory: pushLog(updated[idx].logHistory || [], msg, "start"),
            };
          }
          break;

        case "agent.task.progress":
          if (idx >= 0) {
            const progressText = event.message?.trim();
            updated[idx] = {
              ...updated[idx],
              progress: event.progress || 0,
              logHistory: progressText
                ? pushLog(updated[idx].logHistory || [], progressText, "progress")
                : (updated[idx].logHistory || []),
            };
          }
          break;

        case "agent.task.completed":
          if (idx >= 0) {
            const msg = event.message || "Done.";
            updated[idx] = {
              ...updated[idx],
              state: "complete",
              progress: 100,
              speechBubble: msg,
              logHistory: pushLog(updated[idx].logHistory || [], msg, "complete"),
            };
            // Reset to idle after animation
            setTimeout(() => {
              setAgents((prev2) => {
                const u = [...prev2];
                const i = u.findIndex((a) => a.name === event.agent);
                if (i >= 0 && u[i].state === "complete") {
                  u[i] = { ...u[i], state: "idle", progress: 0, speechBubble: null };
                }
                return u;
              });
            }, 3000);
          }
          break;

        case "agent.task.failed":
          if (idx >= 0) {
            const msg = event.message || "Error.";
            updated[idx] = {
              ...updated[idx],
              state: "error",
              progress: 0,
              speechBubble: msg,
              logHistory: pushLog(updated[idx].logHistory || [], msg, "error"),
            };
            setTimeout(() => {
              setAgents((prev2) => {
                const u = [...prev2];
                const i = u.findIndex((a) => a.name === event.agent);
                if (i >= 0 && u[i].state === "error") {
                  u[i] = { ...u[i], state: "idle", speechBubble: null };
                }
                return u;
              });
            }, 5000);
          }
          break;

        case "agent.broadcast": {
          // Scheduler broadcasts — find Scheduler position for pulse origin
          const scheduler = STATIONS.find((s) => s.name === "scheduler");
          if (scheduler) {
            setBroadcastOrigin({ x: scheduler.x + scheduler.width / 2, y: scheduler.y + scheduler.height / 2 });
            setTimeout(() => setBroadcastOrigin(null), 2000);
          }
          // Light up target agents
          const targets = event.targets || [];
          for (const target of targets) {
            const ti = updated.findIndex((a) => a.name === target);
            if (ti >= 0) {
              updated[ti] = { ...updated[ti], state: "busy", progress: 0 };
            }
          }
          break;
        }

        case "orchestration.plan_created": {
          // Light up scheduler with plan info
          const schedulerIdx = updated.findIndex((a) => a.name === "scheduler");
          if (schedulerIdx >= 0) {
            const msg = event.message || "Drafting plan...";
            updated[schedulerIdx] = {
              ...updated[schedulerIdx],
              state: "busy",
              speechBubble: msg,
              logHistory: pushLog(updated[schedulerIdx].logHistory || [], msg, "start"),
            };
          }
          break;
        }

        case "orchestration.step_started": {
          const targetAgent = (event.payload?.agent as string) || event.agent;
          const ti = updated.findIndex((a) => a.name === targetAgent);
          if (ti >= 0) {
            const msg = (event.payload?.description as string) || event.message || "Working...";
            updated[ti] = {
              ...updated[ti],
              state: "busy",
              progress: 0,
              speechBubble: msg,
              logHistory: pushLog(updated[ti].logHistory || [], msg, "start"),
            };
          }
          break;
        }

        case "orchestration.step_completed": {
          const targetAgent = (event.payload?.agent as string) || event.agent;
          const ti = updated.findIndex((a) => a.name === targetAgent);
          if (ti >= 0) {
            const msg = (event.payload?.summary as string) || event.message || "Step complete.";
            updated[ti] = {
              ...updated[ti],
              state: "complete",
              progress: 100,
              speechBubble: msg,
              logHistory: pushLog(updated[ti].logHistory || [], msg, "complete"),
            };
            setTimeout(() => {
              setAgents((prev2) => {
                const u = [...prev2];
                const i = u.findIndex((a) => a.name === targetAgent);
                if (i >= 0 && u[i].state === "complete") {
                  u[i] = { ...u[i], state: "idle", progress: 0, speechBubble: null };
                }
                return u;
              });
            }, 3000);
          }
          break;
        }

        case "orchestration.step_failed": {
          const targetAgent = (event.payload?.agent as string) || event.agent;
          const ti = updated.findIndex((a) => a.name === targetAgent);
          if (ti >= 0) {
            const msg = (event.payload?.error as string) || event.message || "Step failed.";
            updated[ti] = {
              ...updated[ti],
              state: "error",
              progress: 0,
              speechBubble: msg,
              logHistory: pushLog(updated[ti].logHistory || [], msg, "error"),
            };
            setTimeout(() => {
              setAgents((prev2) => {
                const u = [...prev2];
                const i = u.findIndex((a) => a.name === targetAgent);
                if (i >= 0 && u[i].state === "error") {
                  u[i] = { ...u[i], state: "idle", speechBubble: null };
                }
                return u;
              });
            }, 5000);
          }
          break;
        }

        case "orchestration.broadcast": {
          // Pulse from scheduler to targets
          const scheduler = STATIONS.find((s) => s.name === "scheduler");
          if (scheduler) {
            setBroadcastOrigin({
              x: scheduler.x + scheduler.width / 2,
              y: scheduler.y + scheduler.height / 2,
            });
            setTimeout(() => setBroadcastOrigin(null), 2000);
          }
          const orchTargets = (event.payload?.targets as string[]) || event.targets || [];
          for (const target of orchTargets) {
            const ti = updated.findIndex((a) => a.name === target);
            if (ti >= 0) {
              updated[ti] = { ...updated[ti], state: "busy", progress: 0 };
            }
          }
          break;
        }

        case "playbook.entry_added": {
          // Brief highlight on scheduler for knowledge recording
          const schedulerIdx = updated.findIndex((a) => a.name === "scheduler");
          if (schedulerIdx >= 0) {
            const msg = `Recorded: ${(event.payload?.entry_type as string) || "knowledge"}`;
            updated[schedulerIdx] = {
              ...updated[schedulerIdx],
              speechBubble: msg,
              logHistory: pushLog(updated[schedulerIdx].logHistory || [], msg, "note"),
            };
          }
          break;
        }

        case "trust.level_changed": {
          const schedulerIdx = updated.findIndex((a) => a.name === "scheduler");
          if (schedulerIdx >= 0) {
            const msg = `Trust: ${(event.payload?.new_level as string) || "upgraded"}`;
            updated[schedulerIdx] = {
              ...updated[schedulerIdx],
              speechBubble: msg,
              logHistory: pushLog(updated[schedulerIdx].logHistory || [], msg, "note"),
            };
          }
          break;
        }

        case "chat.narrative": {
          const schedulerIdx = updated.findIndex((a) => a.name === "scheduler");
          if (schedulerIdx >= 0) {
            const msg = (event.payload?.message as string) || event.message || "";
            if (msg) {
              updated[schedulerIdx] = {
                ...updated[schedulerIdx],
                speechBubble: msg.slice(0, 80),
                logHistory: pushLog(updated[schedulerIdx].logHistory || [], msg.slice(0, 120), "note"),
              };
            }
          }
          break;
        }

        case "orchestration.evaluation": {
          const schedulerIdx = updated.findIndex((a) => a.name === "scheduler");
          if (schedulerIdx >= 0) {
            const verdict = (event.payload?.verdict as string) || "";
            const msg = `Eval: ${verdict}`;
            updated[schedulerIdx] = {
              ...updated[schedulerIdx],
              speechBubble: msg,
              logHistory: pushLog(updated[schedulerIdx].logHistory || [], msg, "note"),
            };
          }
          break;
        }

        case "orchestration.cycle_complete": {
          const schedulerIdx = updated.findIndex((a) => a.name === "scheduler");
          if (schedulerIdx >= 0) {
            updated[schedulerIdx] = {
              ...updated[schedulerIdx],
              state: "idle",
              progress: 0,
              speechBubble: "Cycle complete",
              logHistory: pushLog(updated[schedulerIdx].logHistory || [], "Cycle complete.", "complete"),
            };
            setTimeout(() => {
              setAgents((prev2) => {
                const u = [...prev2];
                const i = u.findIndex((a) => a.name === "scheduler");
                if (i >= 0) {
                  u[i] = { ...u[i], speechBubble: null };
                }
                return u;
              });
            }, 5000);
          }
          break;
        }
      }

      return updated;
    });

    // Clear speech bubbles after duration
    if (event.message && event.agent) {
      setTimeout(() => {
        setAgents((prev) => {
          const u = [...prev];
          const i = u.findIndex((a) => a.name === event.agent);
          if (i >= 0 && u[i].speechBubble === event.message) {
            u[i] = { ...u[i], speechBubble: null };
          }
          return u;
        });
      }, SPEECH_BUBBLE_DURATION);
    }
  }, [mergeAgents]);

  const normalizeEvent = useCallback((event: FloorEvent): FloorEvent => {
    const payload = event.payload && typeof event.payload === "object" ? event.payload : {};
    const normalizedType = ({
      "agent.task_started": "agent.task.started",
      "agent.task_completed": "agent.task.completed",
      "agent.task_failed": "agent.task.failed",
    } as Record<string, string>)[event.type] || event.type;
    const payloadAgent = typeof payload.agent === "string" ? payload.agent : undefined;
    const payloadMessage = typeof payload.message === "string" ? payload.message : undefined;
    const payloadTargets = Array.isArray(payload.targets)
      ? payload.targets.filter((target): target is string => typeof target === "string")
      : undefined;
    const payloadProgress = typeof payload.progress === "number" ? payload.progress : undefined;

    return {
      ...event,
      type: normalizedType,
      payload,
      agent: event.agent || payloadAgent || event.source_agent,
      message: event.message || payloadMessage,
      targets: event.targets || payloadTargets,
      progress: event.progress ?? payloadProgress,
    };
  }, []);

  const getEventKey = useCallback((event: FloorEvent) => {
    const payload = event.payload ? JSON.stringify(event.payload) : "";
    const targets = event.targets ? event.targets.join(",") : "";
    return [
      event.timestamp || "",
      event.type,
      event.agent || "",
      event.message || "",
      String(event.progress ?? ""),
      targets,
      payload,
    ].join("|");
  }, []);

  const rememberEvent = useCallback((key: string) => {
    if (!key || seenEventSetRef.current.has(key)) {
      return false;
    }
    seenEventSetRef.current.add(key);
    seenEventKeysRef.current.push(key);
    if (seenEventKeysRef.current.length > 500) {
      const stale = seenEventKeysRef.current.shift();
      if (stale) {
        seenEventSetRef.current.delete(stale);
      }
    }
    return true;
  }, []);

  const processEvent = useCallback((rawEvent: FloorEvent) => {
    const event = normalizeEvent(rawEvent);
    const eventKey = getEventKey(event);
    if (!rememberEvent(eventKey)) {
      return;
    }
    if (event.timestamp && event.timestamp > lastTimestampRef.current) {
      lastTimestampRef.current = event.timestamp;
    }
    handleEvent(event);
  }, [getEventKey, handleEvent, normalizeEvent, rememberEvent]);

  // Persist last-seen timestamp across mounts so navigating away and
  // back replays the events that arrived while the floor was unmounted.
  // Without this, agent state (busy/complete) appears to "stop" on
  // return because the WebSocket only delivers events from now forward.
  const persistLastTimestamp = useCallback((ts: string | undefined) => {
    if (!ts) return;
    // Compare against localStorage rather than the ref, because
    // processEvent already advanced the ref before we got here.
    try {
      const stored = localStorage.getItem("quantclaw_floor_last_event_ts") || "";
      if (ts > stored) localStorage.setItem("quantclaw_floor_last_event_ts", ts);
    } catch { /* ignore */ }
  }, []);

  const processEventTracked = useCallback((rawEvent: FloorEvent) => {
    processEvent(rawEvent);
    persistLastTimestamp(rawEvent.timestamp);
  }, [processEvent, persistLastTimestamp]);

  // WebSocket connection
  useEffect(() => {
    let reconnectTimeout: ReturnType<typeof setTimeout>;
    let cancelled = false;

    // Hydrate last-seen timestamp from storage so the catch-up fetch
    // covers the actual gap (initial render of useState is "" otherwise).
    try {
      const stored = localStorage.getItem("quantclaw_floor_last_event_ts");
      if (stored && stored > lastTimestampRef.current) {
        lastTimestampRef.current = stored;
      }
    } catch { /* ignore */ }

    async function replayMissed() {
      if (!lastTimestampRef.current) return;
      try {
        const params = new URLSearchParams({
          since: lastTimestampRef.current,
          limit: "500",
        });
        const resp = await fetch(`${POLL_URL}?${params.toString()}`);
        const data = await resp.json();
        if (cancelled) return;
        for (const event of data.events || []) {
          processEventTracked(event as FloorEvent);
        }
      } catch { /* offline ok */ }
    }

    function connect() {
      try {
        const ws = new WebSocket(WS_URL);
        wsRef.current = ws;

        ws.onmessage = (e) => {
          try {
            const event = JSON.parse(e.data) as FloorEvent;
            processEventTracked(event);
          } catch {}
        };

        ws.onclose = () => {
          wsRef.current = null;
          // Start polling as fallback
          if (!pollRef.current) {
            pollRef.current = setInterval(async () => {
              try {
                const params = new URLSearchParams({ limit: "200" });
                if (lastTimestampRef.current) {
                  params.set("since", lastTimestampRef.current);
                }
                const resp = await fetch(`${POLL_URL}?${params.toString()}`);
                const data = await resp.json();
                for (const event of data.events || []) {
                  processEventTracked(event);
                }
              } catch {}
            }, POLL_INTERVAL);
          }
          // Try reconnecting
          reconnectTimeout = setTimeout(connect, RECONNECT_DELAY);
        };

        ws.onopen = () => {
          // Stop polling if WebSocket reconnects
          if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
        };
      } catch {
        reconnectTimeout = setTimeout(connect, RECONNECT_DELAY);
      }
    }

    void replayMissed().then(() => { if (!cancelled) connect(); });

    return () => {
      cancelled = true;
      clearTimeout(reconnectTimeout);
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (pollRef.current) {
        clearInterval(pollRef.current);
      }
    };
  }, [processEventTracked]);

  const mergedAgents = initialAgents.length > 0 ? mergeAgents(initialAgents, agents) : agents;

  return { agents: mergedAgents, broadcastOrigin };
}
