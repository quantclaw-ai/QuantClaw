# Trading Floor Playground — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the QuantClaw dashboard home page with a live 2D canvas trading floor showing 13 AI agents at themed stations, with a chat panel for @mention interaction.

**Architecture:** HTML5 Canvas renders the floor with sprite-based agents. React handles the chat panel, overlays, and state. WebSocket pushes real-time agent events. Three swappable visual modes (pixel, isometric, modern) share one logic layer.

**Tech Stack:** Next.js, HTML5 Canvas API, WebSocket, Tailwind CSS, existing FastAPI backend + `/ws/events` endpoint.

---

## Phase 1: Canvas Foundation & Floor Layout

### Task 1: Create the TradingFloor component shell

**Files:**
- Create: `quantclaw/dashboard/app/app/dashboard/floor/TradingFloor.tsx`
- Create: `quantclaw/dashboard/app/app/dashboard/floor/types.ts`

**Step 1: Create types file**

```typescript
// floor/types.ts
export type AgentState = "idle" | "busy" | "complete" | "error";
export type VisualMode = "pixel" | "isometric" | "modern";

export interface FloorAgent {
  name: string;
  displayName: string;
  enabled: boolean;
  locked: boolean;
  state: AgentState;
  progress: number; // 0-100
  speechBubble: string | null;
  zone: string;
  x: number; // station position on canvas
  y: number;
}

export interface FloorConfig {
  width: number;
  height: number;
  agents: FloorAgent[];
  mode: VisualMode;
}
```

**Step 2: Create TradingFloor canvas component**

```tsx
// floor/TradingFloor.tsx
"use client";
import { useRef, useEffect, useState, useCallback } from "react";
import type { FloorAgent, VisualMode } from "./types";

interface TradingFloorProps {
  agents: FloorAgent[];
  mode: VisualMode;
  onAgentClick: (agentName: string) => void;
  selectedAgent: string | null;
}

export function TradingFloor({ agents, mode, onAgentClick, selectedAgent }: TradingFloorProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animFrameRef = useRef<number>(0);

  // Render loop placeholder
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const render = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = "#030712"; // gray-950
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      // TODO: draw floor, stations, agents
      animFrameRef.current = requestAnimationFrame(render);
    };
    render();
    return () => cancelAnimationFrame(animFrameRef.current);
  }, [agents, mode, selectedAgent]);

  // Click hit-testing
  const handleClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    // TODO: hit-test agent stations
  }, [agents, onAgentClick]);

  return (
    <canvas
      ref={canvasRef}
      width={960}
      height={640}
      onClick={handleClick}
      className="w-full h-full"
      style={{ imageRendering: mode === "pixel" ? "pixelated" : "auto" }}
    />
  );
}
```

**Step 3: Commit**

```bash
git add quantclaw/dashboard/app/app/dashboard/floor/
git commit -m "feat(floor): create TradingFloor canvas component shell and types"
```

---

### Task 2: Define agent station positions and zones

**Files:**
- Create: `quantclaw/dashboard/app/app/dashboard/floor/stations.ts`

**Step 1: Create station layout config**

Define all 13 agent stations with positions, zone assignments, and themed metadata. Positions are in a 960x640 canvas coordinate space.

```typescript
// floor/stations.ts
import type { FloorAgent } from "./types";

export interface StationConfig {
  name: string;
  displayName: string;
  zone: string;
  x: number;
  y: number;
  width: number;
  height: number;
  theme: {
    props: string[]; // descriptive, used for rendering
    busyAnimation: string;
    color: string; // accent color hex
  };
}

export const STATIONS: StationConfig[] = [
  // Command Center
  { name: "scheduler", displayName: "Scheduler", zone: "Command Center", x: 80, y: 60, width: 120, height: 100,
    theme: { props: ["reception_desk", "workflow_board", "megaphone"], busyAnimation: "cards_shuffle", color: "#f59e0b" }},
  { name: "sentinel", displayName: "Sentinel", zone: "Command Center", x: 80, y: 200, width: 120, height: 100,
    theme: { props: ["watchtower", "radar", "binoculars"], busyAnimation: "radar_sweep", color: "#f43f5e" }},

  // Data Room
  { name: "ingestor", displayName: "Ingestor", zone: "Data Room", x: 80, y: 380, width: 120, height: 100,
    theme: { props: ["data_pipes", "satellite_dish", "monitors"], busyAnimation: "pipes_flow", color: "#3b82f6" }},

  // Quant Lab
  { name: "backtester", displayName: "Backtester", zone: "Quant Lab", x: 320, y: 60, width: 120, height: 100,
    theme: { props: ["time_machine", "rewind_dials", "equity_curve"], busyAnimation: "dials_spin", color: "#8b5cf6" }},
  { name: "miner", displayName: "Miner", zone: "Quant Lab", x: 320, y: 200, width: 120, height: 100,
    theme: { props: ["pickaxe", "ore_cart", "crystals"], busyAnimation: "pickaxe_swing", color: "#ef4444" }},
  { name: "trainer", displayName: "Trainer", zone: "Quant Lab", x: 320, y: 340, width: 120, height: 100,
    theme: { props: ["neural_network", "brain_jar", "training_bars"], busyAnimation: "nodes_pulse", color: "#ec4899" }},
  { name: "researcher", displayName: "Researcher", zone: "Quant Lab", x: 320, y: 480, width: 120, height: 100,
    theme: { props: ["library_desk", "magnifying_glass", "lightbulb"], busyAnimation: "pages_flip", color: "#06b6d4" }},

  // Trading Desk
  { name: "executor", displayName: "Executor", zone: "Trading Desk", x: 560, y: 60, width: 120, height: 100,
    theme: { props: ["bloomberg_terminal", "order_blotter", "buy_sell_lights"], busyAnimation: "lights_flash", color: "#22c55e" }},
  { name: "risk_monitor", displayName: "Risk Monitor", zone: "Trading Desk", x: 560, y: 200, width: 120, height: 100,
    theme: { props: ["gauges", "warning_lights", "shield"], busyAnimation: "gauges_swing", color: "#a855f7" }},

  // Back Office
  { name: "reporter", displayName: "Reporter", zone: "Back Office", x: 760, y: 60, width: 120, height: 100,
    theme: { props: ["printing_press", "papers", "wall_charts"], busyAnimation: "printer_output", color: "#f97316" }},
  { name: "cost_tracker", displayName: "Cost Tracker", zone: "Back Office", x: 760, y: 200, width: 120, height: 100,
    theme: { props: ["calculator", "ledger", "coin_stacks"], busyAnimation: "coins_animate", color: "#14b8a6" }},
  { name: "compliance", displayName: "Compliance", zone: "Back Office", x: 760, y: 340, width: 120, height: 100,
    theme: { props: ["filing_cabinet", "stamp", "scales"], busyAnimation: "stamp_pound", color: "#6366f1" }},

  // Debug Bay
  { name: "debugger", displayName: "Debugger", zone: "Debug Bay", x: 560, y: 380, width: 120, height: 100,
    theme: { props: ["workbench", "bug_jar", "circuit_boards"], busyAnimation: "magnify_scan", color: "#eab308" }},
];

export function getStationByName(name: string): StationConfig | undefined {
  return STATIONS.find((s) => s.name === name);
}
```

**Step 2: Commit**

```bash
git add quantclaw/dashboard/app/app/dashboard/floor/stations.ts
git commit -m "feat(floor): define 13 agent station positions and zone layout"
```

---

### Task 3: Render stations on canvas (Modern mode first)

**Files:**
- Modify: `quantclaw/dashboard/app/app/dashboard/floor/TradingFloor.tsx`
- Create: `quantclaw/dashboard/app/app/dashboard/floor/renderers/modern.ts`

**Step 1: Create modern renderer**

The modern renderer draws each station as styled rectangles with neon accents — no sprites needed for v1, just canvas drawing primitives that look clean and match the dashboard.

```typescript
// floor/renderers/modern.ts
import type { FloorAgent } from "../types";
import { STATIONS, type StationConfig } from "../stations";

const STATE_COLORS = {
  idle: "#22c55e",
  busy: "#f59e0b",
  complete: "#22c55e",
  error: "#ef4444",
};

export function renderModernFloor(
  ctx: CanvasRenderingContext2D,
  agents: FloorAgent[],
  selectedAgent: string | null,
  frame: number,
) {
  const w = ctx.canvas.width;
  const h = ctx.canvas.height;

  // Background
  ctx.fillStyle = "#030712";
  ctx.fillRect(0, 0, w, h);

  // Grid lines
  ctx.strokeStyle = "#111827";
  ctx.lineWidth = 0.5;
  for (let x = 0; x < w; x += 40) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
  }
  for (let y = 0; y < h; y += 40) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
  }

  // Zone labels
  renderZoneLabels(ctx);

  // Stations
  for (const station of STATIONS) {
    const agent = agents.find((a) => a.name === station.name);
    renderStation(ctx, station, agent, selectedAgent === station.name, frame);
  }
}

function renderZoneLabels(ctx: CanvasRenderingContext2D) {
  ctx.font = "10px monospace";
  ctx.fillStyle = "#374151";
  ctx.fillText("COMMAND CENTER", 80, 40);
  ctx.fillText("DATA ROOM", 80, 360);
  ctx.fillText("QUANT LAB", 320, 40);
  ctx.fillText("TRADING DESK", 560, 40);
  ctx.fillText("BACK OFFICE", 760, 40);
  ctx.fillText("DEBUG BAY", 560, 360);
}

function renderStation(
  ctx: CanvasRenderingContext2D,
  station: StationConfig,
  agent: FloorAgent | undefined,
  isSelected: boolean,
  frame: number,
) {
  const { x, y, width: sw, height: sh } = station;
  const locked = agent?.locked ?? true;
  const state = agent?.state ?? "idle";
  const progress = agent?.progress ?? 0;

  ctx.save();
  if (locked) ctx.globalAlpha = 0.3;

  // Station background
  ctx.fillStyle = "#0a0f1a";
  ctx.strokeStyle = isSelected ? "#f59e0b" : "#1f2937";
  ctx.lineWidth = isSelected ? 2 : 1;
  roundRect(ctx, x, y, sw, sh, 8);
  ctx.fill();
  ctx.stroke();

  // Agent character (simple circle avatar)
  const cx = x + sw / 2;
  const cy = y + 35;
  const radius = 14;

  // Glow for busy state
  if (state === "busy") {
    ctx.shadowColor = station.theme.color;
    ctx.shadowBlur = 10 + Math.sin(frame * 0.1) * 5;
  }

  ctx.beginPath();
  ctx.arc(cx, cy, radius, 0, Math.PI * 2);
  ctx.fillStyle = locked ? "#374151" : station.theme.color;
  ctx.fill();
  ctx.shadowBlur = 0;

  // Status dot
  const dotColor = STATE_COLORS[state] || STATE_COLORS.idle;
  ctx.beginPath();
  ctx.arc(cx + radius - 2, cy - radius + 2, 4, 0, Math.PI * 2);
  ctx.fillStyle = dotColor;
  ctx.fill();

  // Idle animation: subtle bob
  if (state === "idle" && !locked) {
    const bob = Math.sin(frame * 0.03 + station.x) * 1.5;
    ctx.beginPath();
    ctx.arc(cx, cy + bob, radius, 0, Math.PI * 2);
    ctx.fillStyle = station.theme.color + "20";
    ctx.fill();
  }

  // Mini data display
  ctx.fillStyle = "#111827";
  roundRect(ctx, x + 8, y + 55, sw - 16, 16, 3);
  ctx.fill();
  if (state === "busy") {
    // Animated data line
    ctx.strokeStyle = station.theme.color + "80";
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let i = 0; i < sw - 20; i += 3) {
      const ly = y + 63 + Math.sin((i + frame * 2) * 0.15) * 4;
      i === 0 ? ctx.moveTo(x + 10 + i, ly) : ctx.lineTo(x + 10 + i, ly);
    }
    ctx.stroke();
  }

  // Progress bar (busy only)
  if (state === "busy" && progress > 0) {
    ctx.fillStyle = "#1f2937";
    roundRect(ctx, x + 8, y + 75, sw - 16, 6, 3);
    ctx.fill();
    ctx.fillStyle = station.theme.color;
    roundRect(ctx, x + 8, y + 75, (sw - 16) * (progress / 100), 6, 3);
    ctx.fill();
  }

  // Name label
  ctx.font = "10px sans-serif";
  ctx.fillStyle = locked ? "#4b5563" : "#9ca3af";
  ctx.textAlign = "center";
  ctx.fillText(station.displayName, cx, y + sh - 6);
  ctx.textAlign = "start";

  // Lock icon for locked agents
  if (locked) {
    ctx.font = "16px sans-serif";
    ctx.fillStyle = "#4b5563";
    ctx.textAlign = "center";
    ctx.fillText("L", cx, cy + 5); // placeholder for lock icon
    ctx.textAlign = "start";
  }

  // Speech bubble
  if (agent?.speechBubble) {
    renderSpeechBubble(ctx, cx, y - 10, agent.speechBubble);
  }

  ctx.restore();
}

function renderSpeechBubble(ctx: CanvasRenderingContext2D, x: number, y: number, text: string) {
  const maxWidth = 140;
  ctx.font = "9px sans-serif";
  const lines = wrapText(ctx, text, maxWidth - 16);
  const bh = lines.length * 12 + 12;
  const bw = maxWidth;
  const bx = x - bw / 2;
  const by = y - bh - 8;

  // Bubble
  ctx.fillStyle = "#1f2937";
  ctx.strokeStyle = "#374151";
  ctx.lineWidth = 1;
  roundRect(ctx, bx, by, bw, bh, 6);
  ctx.fill();
  ctx.stroke();

  // Tail
  ctx.beginPath();
  ctx.moveTo(x - 5, by + bh);
  ctx.lineTo(x, by + bh + 6);
  ctx.lineTo(x + 5, by + bh);
  ctx.fillStyle = "#1f2937";
  ctx.fill();

  // Text
  ctx.fillStyle = "#d1d5db";
  lines.forEach((line, i) => {
    ctx.fillText(line, bx + 8, by + 14 + i * 12);
  });
}

function wrapText(ctx: CanvasRenderingContext2D, text: string, maxWidth: number): string[] {
  const words = text.split(" ");
  const lines: string[] = [];
  let current = "";
  for (const word of words) {
    const test = current ? `${current} ${word}` : word;
    if (ctx.measureText(test).width > maxWidth) {
      if (current) lines.push(current);
      current = word;
    } else {
      current = test;
    }
  }
  if (current) lines.push(current);
  return lines.slice(0, 3); // max 3 lines
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}
```

**Step 2: Wire renderer into TradingFloor component**

Update `TradingFloor.tsx` to call `renderModernFloor` in the render loop and implement click hit-testing against station rects.

**Step 3: Commit**

```bash
git add quantclaw/dashboard/app/app/dashboard/floor/
git commit -m "feat(floor): implement modern renderer with station drawing and hit-testing"
```

---

## Phase 2: Page Layout & Chat Panel

### Task 4: Create the split-view home page

**Files:**
- Modify: `quantclaw/dashboard/app/app/dashboard/page.tsx`
- Create: `quantclaw/dashboard/app/app/dashboard/floor/ChatPanel.tsx`
- Create: `quantclaw/dashboard/app/app/dashboard/floor/FloorOverlay.tsx`

**Step 1: Create ChatPanel component**

Extract and adapt the existing chat logic from `page.tsx` into a standalone `ChatPanel` component. Add @mention autocomplete and click-to-talk integration.

Key features:
- Input field with `@agent` autocomplete dropdown
- Messages grouped by agent with colored badges
- Header showing current target agent (default: Scheduler)
- CEO greeting on first load

**Step 2: Create FloorOverlay component**

Small overlay controls rendered on top of the canvas:
- Top-left: Visual mode toggle (3 icon buttons)
- Bottom: Status bar (active tasks count, agent status summary)

**Step 3: Rewrite page.tsx as split layout**

```tsx
// Simplified structure
export default function DashboardHome() {
  return (
    <div className="flex h-[calc(100vh-48px)]">
      {/* Trading Floor Canvas - 65% */}
      <div className="flex-[65] relative">
        <TradingFloor agents={agents} mode={mode} onAgentClick={...} selectedAgent={...} />
        <FloorOverlay mode={mode} onModeChange={...} agents={agents} />
      </div>
      {/* Chat Panel - 35% */}
      <div className="flex-[35] border-l border-gray-800">
        <ChatPanel agents={agents} targetAgent={...} onSend={...} />
      </div>
    </div>
  );
}
```

**Step 4: Commit**

```bash
git add quantclaw/dashboard/app/app/dashboard/
git commit -m "feat(floor): split home page into canvas + chat panel layout"
```

---

### Task 5: Implement @mention autocomplete

**Files:**
- Modify: `quantclaw/dashboard/app/app/dashboard/floor/ChatPanel.tsx`

**Step 1: Add autocomplete logic**

When user types `@` in the input, show a dropdown of enabled agents with their status (idle/busy). Clicking an agent inserts `@agentname ` into the input and sets the target agent. Locked agents shown greyed out.

**Step 2: Commit**

```bash
git commit -m "feat(floor): add @mention autocomplete in chat panel"
```

---

## Phase 3: WebSocket & Agent State

### Task 6: Connect to WebSocket for real-time agent events

**Files:**
- Create: `quantclaw/dashboard/app/app/dashboard/floor/useFloorEvents.ts`
- Modify: `quantclaw/dashboard/app/app/dashboard/page.tsx`

**Step 1: Create useFloorEvents hook**

Custom hook that:
- Connects to `ws://localhost:8000/ws/events`
- Parses incoming events (`agent.task.started`, `agent.task.completed`, etc.)
- Updates agent state (idle -> busy -> complete/error)
- Falls back to polling `/api/events` every 3s on disconnect

```typescript
export function useFloorEvents(agents: FloorAgent[]): FloorAgent[] {
  // Returns updated agents array with real-time state
}
```

**Step 2: Wire into page.tsx state management**

**Step 3: Commit**

```bash
git commit -m "feat(floor): add WebSocket hook for real-time agent state updates"
```

---

### Task 7: Emit agent events from chat endpoint

**Files:**
- Modify: `quantclaw/dashboard/api.py`

**Step 1: Update POST /api/chat to emit WebSocket events**

Before calling the LLM, emit `agent.task.started`. After response, emit `agent.task.completed` or `agent.task.failed`. For broadcast (Scheduler delegating), emit `agent.broadcast` with target agent list.

**Step 2: Commit**

```bash
git commit -m "feat(api): emit agent task events via WebSocket from chat endpoint"
```

---

## Phase 4: Broadcast Animation & Multi-Agent

### Task 8: Implement broadcast pulse animation

**Files:**
- Modify: `quantclaw/dashboard/app/app/dashboard/floor/renderers/modern.ts`

**Step 1: Add pulse ring effect**

When `agent.broadcast` event fires, render an expanding circle from Scheduler's station that fades out as it reaches target agents. Target agents transition to Busy simultaneously.

**Step 2: Commit**

```bash
git commit -m "feat(floor): add broadcast pulse ring animation from Scheduler"
```

---

## Phase 5: Visual Mode Switching

### Task 9: Create pixel art renderer

**Files:**
- Create: `quantclaw/dashboard/app/app/dashboard/floor/renderers/pixel.ts`

**Step 1: Implement pixel renderer**

Same API as modern renderer but draws using chunky pixel-art style: blocky shapes, limited palette, 8-bit aesthetic. Uses `imageRendering: pixelated` on canvas.

**Step 2: Commit**

```bash
git commit -m "feat(floor): add pixel art visual mode renderer"
```

---

### Task 10: Create isometric renderer

**Files:**
- Create: `quantclaw/dashboard/app/app/dashboard/floor/renderers/isometric.ts`

**Step 1: Implement isometric renderer**

Diamond-tile projection. Stations rendered as isometric boxes with depth sorting. 2.5D perspective.

**Step 2: Commit**

```bash
git commit -m "feat(floor): add isometric visual mode renderer"
```

---

### Task 11: Wire mode toggle

**Files:**
- Modify: `quantclaw/dashboard/app/app/dashboard/floor/FloorOverlay.tsx`
- Modify: `quantclaw/dashboard/app/app/dashboard/floor/TradingFloor.tsx`

**Step 1: Add mode switching with fade transition**

FloorOverlay has 3 toggle buttons. Clicking triggers 0.3s canvas fade, swaps renderer, fades back in. Preference saved to localStorage.

**Step 2: Commit**

```bash
git commit -m "feat(floor): wire visual mode toggle with fade transition"
```

---

## Phase 6: Polish & i18n

### Task 12: Add i18n for floor UI

**Files:**
- Modify: `quantclaw/dashboard/app/app/dashboard/floor/ChatPanel.tsx`
- Modify: `quantclaw/dashboard/app/app/dashboard/floor/FloorOverlay.tsx`
- Modify: `quantclaw/dashboard/app/app/dashboard/floor/stations.ts`

**Step 1: Translate agent names, zone labels, status text, chat UI**

Use existing `useLang()` context. Add translated agent display names and zone labels for EN/ZH/JA.

**Step 2: Commit**

```bash
git commit -m "feat(floor): add i18n for trading floor UI (EN/ZH/JA)"
```

---

### Task 13: Locked agent interaction

**Files:**
- Modify: `quantclaw/dashboard/app/app/dashboard/floor/TradingFloor.tsx`
- Modify: `quantclaw/dashboard/app/app/dashboard/floor/ChatPanel.tsx`

**Step 1: Handle locked agent clicks**

Clicking a locked agent on the canvas shows a tooltip: "Unlock at Level X". In chat, typing `@locked_agent` shows a system message about progression.

**Step 2: Commit**

```bash
git commit -m "feat(floor): add locked agent click handling with unlock hints"
```

---

### Task 14: Final integration and cleanup

**Files:**
- Modify: `quantclaw/dashboard/app/app/dashboard/page.tsx`

**Step 1: Remove old chat-only home page code**

Ensure the old chat-only page is fully replaced. Verify provider/model selector from top bar is integrated into the new layout. Test all flows: chat, @mentions, click-to-talk, mode switching, WebSocket events, locked agents.

**Step 2: Commit and push**

```bash
git add -A
git commit -m "feat(floor): complete Trading Floor Playground integration"
git push
```

---

## Task Dependency Graph

```
Task 1 (canvas shell) -> Task 2 (stations) -> Task 3 (modern renderer)
                                                    |
Task 4 (split layout + chat) -> Task 5 (@mentions) |
                                                    v
Task 6 (WebSocket hook) -> Task 7 (backend events) -> Task 8 (broadcast animation)
                                                            |
Task 9 (pixel renderer) -> Task 11 (mode toggle) <---------+
Task 10 (iso renderer)  -/                                  |
                                                            v
                                              Task 12 (i18n) -> Task 13 (locked) -> Task 14 (cleanup)
```

**Critical path:** Tasks 1-4-6-7 (canvas + layout + WebSocket) must be done first. Renderers (9, 10) and polish (12, 13) can be parallelized.
