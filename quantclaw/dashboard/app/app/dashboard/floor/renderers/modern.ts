import type { AgentLogEntry, FloorAgent, LogKind } from "../types";
import {
  STATIONS,
  getStationByName,
  getStationDisplayName,
  getZoneDisplayName,
  type StationConfig,
} from "../stations";

// ---------------------------------------------------------------------------
// Aesthetic: "digital terrarium meets Bloomberg terminal". Each station is a
// glass box holding a living agent-pet with a scrolling caretaker's log of
// everything it has said. Phosphor mono typography, faint scanlines, subtle
// CRT flicker. No emoji — every creature is drawn in canvas primitives so
// they're crisp at any resolution and each species has a distinct silhouette.
// ---------------------------------------------------------------------------

const BG_COLOR = "#050912";
const GRID_COLOR = "#0a1020";
const STATION_BG = "#0a1122";
const STATION_BG_INNER = "#0c1428";
const STATION_BORDER = "#1a2545";
const SELECTED_BORDER = "#d4a517";
const TEXT_COLOR = "#c8d1db";
const NAME_COLOR = "#e3ecf7";
const LABEL_COLOR = "#4a5a7a";
const LOCK_COLOR = "#2a3a5a";
const SCANLINE_COLOR = "rgba(255,255,255,0.02)";

// Log color per kind — phosphor terminal palette.
const LOG_COLORS: Record<LogKind, string> = {
  start:    "#7dd3fc", // sky-300 — "I've begun"
  progress: "#a0b0cc", // muted — "still at it"
  complete: "#34d399", // emerald-400 — "done"
  error:    "#f87171", // red-400 — "oops"
  note:     "#c8d1db", // default text
};

const GRID_SPACING = 40;
const CORNER_RADIUS = 8;
const PORTRAIT_RADIUS = 14;

// Typewriter reveal: characters-per-ms on the newest log entry.
const TYPEWRITER_CHARS_PER_MS = 0.06;

// ---------------------------------------------------------------------------
// Small utilities
// ---------------------------------------------------------------------------

function hexToRgb(hex: string): { r: number; g: number; b: number } {
  const n = parseInt(hex.replace("#", ""), 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

function rgba(hex: string, alpha: number): string {
  const { r, g, b } = hexToRgb(hex);
  return `rgba(${r},${g},${b},${alpha})`;
}

function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
): void {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.arcTo(x + w, y, x + w, y + r, r);
  ctx.lineTo(x + w, y + h - r);
  ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
  ctx.lineTo(x + r, y + h);
  ctx.arcTo(x, y + h, x, y + h - r, r);
  ctx.lineTo(x, y + r);
  ctx.arcTo(x, y, x + r, y, r);
  ctx.closePath();
}

// Deterministic pseudo-random from name — used to vary blink/bob phase per agent
// so they don't all breathe in unison.
function seed(name: string): number {
  let h = 2166136261;
  for (let i = 0; i < name.length; i++) {
    h ^= name.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0) / 4294967295;
}

// ---------------------------------------------------------------------------
// Background & grid & scanlines
// ---------------------------------------------------------------------------

function drawBackground(ctx: CanvasRenderingContext2D, w: number, h: number): void {
  // Deep navy base with faint vignette
  const grad = ctx.createRadialGradient(w / 2, h / 2, 50, w / 2, h / 2, Math.max(w, h) / 1.1);
  grad.addColorStop(0, "#070c1a");
  grad.addColorStop(1, BG_COLOR);
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, h);

  // Fine grid
  ctx.strokeStyle = GRID_COLOR;
  ctx.lineWidth = 0.5;
  for (let x = 0; x < w; x += GRID_SPACING) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, h);
    ctx.stroke();
  }
  for (let y = 0; y < h; y += GRID_SPACING) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  }
}

// Faint scanlines overlay — applied per-station for performance.
function drawScanlines(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
): void {
  ctx.save();
  ctx.fillStyle = SCANLINE_COLOR;
  for (let sy = y + 2; sy < y + h; sy += 3) {
    ctx.fillRect(x, sy, w, 1);
  }
  ctx.restore();
}

// ---------------------------------------------------------------------------
// Zone labels (etched, small-caps)
// ---------------------------------------------------------------------------

function drawZoneLabels(ctx: CanvasRenderingContext2D, lang: string): void {
  const drawn = new Set<string>();

  for (const station of STATIONS) {
    if (drawn.has(station.zone)) continue;
    drawn.add(station.zone);

    const label = getZoneDisplayName(station, lang);
    ctx.save();
    ctx.font = 'bold 10px "JetBrains Mono", ui-monospace, monospace';
    ctx.fillStyle = LABEL_COLOR;
    ctx.textAlign = "left";
    ctx.textBaseline = "bottom";
    // Draw a small bracket before the zone name
    ctx.fillText(`▸ ${label.toUpperCase()}`, station.x, station.y - 8);
    ctx.restore();
  }
}

// ---------------------------------------------------------------------------
// The creatures — each is a small procedural drawing indexed by agent name.
// All creatures share: body (ellipse, scales with breath), one or two eyes
// that blink on a schedule, and a species-specific silhouette accent.
// ---------------------------------------------------------------------------

type CreatureCtx = {
  ctx: CanvasRenderingContext2D;
  cx: number;       // center x
  cy: number;       // center y
  color: string;
  frame: number;
  busy: boolean;
  error: boolean;
  complete: boolean;
  seedVal: number;  // 0..1 per agent, for phase offsets
};

function drawCreatureBase(c: CreatureCtx, bodyW: number, bodyH: number): void {
  const { ctx, cx, cy, color, frame, busy, error, seedVal } = c;
  const phase = seedVal * Math.PI * 2;
  const sleeping = !busy && !error;

  // Breathing: sleepers breathe slower + deeper. Busy is fast + shallow.
  const breathSpeed = busy ? 0.14 : sleeping ? 0.028 : 0.05;
  const breathAmp = busy ? 0.08 : sleeping ? 0.07 : 0.04;
  const sy = 1 + Math.sin(frame * breathSpeed + phase) * breathAmp;

  // Droop: errored pets sag; sleepers sink a pixel lower than alert.
  const droopY = error ? 3 : sleeping ? 1 : 0;

  // Outer glow (aura)
  const auraAlpha = busy ? 0.25 + 0.15 * Math.abs(Math.sin(frame * 0.12)) : 0.12;
  ctx.fillStyle = rgba(color, auraAlpha);
  ctx.beginPath();
  ctx.ellipse(cx, cy + droopY, bodyW + 4, bodyH * sy + 2, 0, 0, Math.PI * 2);
  ctx.fill();

  // Body — rounded blob
  ctx.fillStyle = rgba(color, error ? 0.35 : 0.7);
  ctx.beginPath();
  ctx.ellipse(cx, cy + droopY, bodyW, bodyH * sy, 0, 0, Math.PI * 2);
  ctx.fill();

  // Body rim highlight
  ctx.strokeStyle = rgba(color, error ? 0.4 : 0.95);
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  ctx.ellipse(cx, cy + droopY, bodyW, bodyH * sy, 0, 0, Math.PI * 2);
  ctx.stroke();
}

function drawEye(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  isBlinking: boolean,
  isError: boolean,
): void {
  if (isBlinking) {
    // Closed eye: horizontal line
    ctx.strokeStyle = rgba("#0a0a10", 0.9);
    ctx.lineWidth = 1.3;
    ctx.beginPath();
    ctx.moveTo(x - 2, y);
    ctx.lineTo(x + 2, y);
    ctx.stroke();
    return;
  }
  // Open eye: white dot with pupil
  ctx.fillStyle = "#f4f7fb";
  ctx.beginPath();
  ctx.arc(x, y, 1.8, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = isError ? "#7f1d1d" : "#0a0a10";
  ctx.beginPath();
  ctx.arc(x, y, 1, 0, Math.PI * 2);
  ctx.fill();
}

function blinkNow(frame: number, seedVal: number): boolean {
  // Awake pets blink briefly every 3-5 seconds.
  const period = 180 + seedVal * 120;
  const phase = seedVal * period;
  const t = (frame + phase) % period;
  return t < 6;
}

// Sleepers close their eyes almost all the time, cracking open briefly every
// few seconds. Returns true when eyes should be drawn CLOSED.
function sleepingEyesClosed(frame: number, seedVal: number): boolean {
  const period = 240 + seedVal * 180;
  const phase = seedVal * period;
  const t = (frame + phase) % period;
  // Crack eyes open for ~8 frames, once per period.
  const peekStart = period * 0.5;
  return !(t > peekStart && t < peekStart + 8);
}

// Unified "are eyes closed right now" — dispatches to sleeping or blink logic
// based on pet state. Every species drawer uses this.
function eyesClosed(c: CreatureCtx): boolean {
  const sleeping = !c.busy && !c.error && !c.complete;
  return sleeping
    ? sleepingEyesClosed(c.frame, c.seedVal)
    : blinkNow(c.frame, c.seedVal);
}

// Floating "zzz" that drifts up and fades when idle. Three Zs stagger per
// breath cycle so each pet radiates its own sleep rhythm.
function drawSleepingZzz(c: CreatureCtx, headX: number, headY: number): void {
  const sleeping = !c.busy && !c.error && !c.complete;
  if (!sleeping) return;
  const { ctx, frame, seedVal } = c;
  const period = 220 + seedVal * 120;
  const phase = seedVal * period;
  ctx.save();
  ctx.font = 'bold 9px "JetBrains Mono", ui-monospace, monospace';
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  for (let i = 0; i < 3; i++) {
    const offset = i * (period / 3);
    const t = (frame + phase + offset) % period;
    const lifespan = 90;
    if (t > lifespan) continue;
    const p = t / lifespan;
    const alpha = (1 - p) * 0.7;
    const size = 9 - i * 1.2;
    const drift = Math.sin(p * Math.PI * 2) * 2;
    const x = headX + i * 2 + drift;
    const y = headY - p * 14 - i * 3;
    ctx.font = `bold ${Math.max(6, size).toFixed(0)}px "JetBrains Mono", ui-monospace, monospace`;
    ctx.fillStyle = `rgba(200,209,219,${alpha.toFixed(2)})`;
    ctx.fillText("z", x, y);
  }
  ctx.restore();
}

// Species-specific silhouette accents drawn ABOVE / BESIDE the body.
type SpeciesDrawer = (c: CreatureCtx) => void;

const SPECIES: Record<string, SpeciesDrawer> = {
  scheduler: (c) => {
    // Clock-hands antenna
    drawCreatureBase(c, 10, 8);
    const { ctx, cx, cy, color, frame } = c;
    const angle = frame * 0.03;
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.3;
    ctx.beginPath();
    ctx.moveTo(cx, cy - 6);
    ctx.lineTo(cx, cy - 14);
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(cx, cy - 14);
    ctx.lineTo(cx + Math.cos(angle) * 4, cy - 14 + Math.sin(angle) * 4);
    ctx.stroke();
    // Tiny stalk tip
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(cx, cy - 14, 1.2, 0, Math.PI * 2);
    ctx.fill();
    // Eyes
    const b = eyesClosed(c);
    drawEye(ctx, cx - 3, cy - 1, b, c.error);
    drawEye(ctx, cx + 3, cy - 1, b, c.error);
  },

  sentinel: (c) => {
    // Single cyclops eye that scans
    drawCreatureBase(c, 10, 8);
    const { ctx, cx, cy, frame, busy, color } = c;
    const scan = busy ? Math.sin(frame * 0.08) * 2 : 0;
    // Radar arc above
    ctx.strokeStyle = rgba(color, 0.6);
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(cx, cy - 2, 12, Math.PI * 1.15, Math.PI * 1.85);
    ctx.stroke();
    // Central large eye
    const b = eyesClosed(c);
    if (b) {
      ctx.strokeStyle = "#0a0a10";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(cx - 3, cy - 1);
      ctx.lineTo(cx + 3, cy - 1);
      ctx.stroke();
    } else {
      ctx.fillStyle = "#f4f7fb";
      ctx.beginPath();
      ctx.arc(cx, cy - 1, 2.8, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = c.error ? "#7f1d1d" : "#0a0a10";
      ctx.beginPath();
      ctx.arc(cx + scan, cy - 1, 1.5, 0, Math.PI * 2);
      ctx.fill();
    }
  },

  ingestor: (c) => {
    // Funnel mouth "drinking" data
    drawCreatureBase(c, 10, 8);
    const { ctx, cx, cy, color, frame, busy } = c;
    // Funnel at top
    ctx.fillStyle = rgba(color, 0.9);
    ctx.beginPath();
    ctx.moveTo(cx - 5, cy - 7);
    ctx.lineTo(cx + 5, cy - 7);
    ctx.lineTo(cx + 2, cy - 11);
    ctx.lineTo(cx - 2, cy - 11);
    ctx.closePath();
    ctx.fill();
    // Droplets falling into funnel
    if (busy) {
      for (let i = 0; i < 3; i++) {
        const t = ((frame * 1.2 + i * 20) % 60) / 60;
        const dy = -20 + t * 10;
        const alpha = 1 - t;
        ctx.fillStyle = rgba(color, alpha);
        ctx.beginPath();
        ctx.arc(cx + (i - 1) * 3, cy + dy, 1.3, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    const b = eyesClosed(c);
    drawEye(ctx, cx - 3, cy + 1, b, c.error);
    drawEye(ctx, cx + 3, cy + 1, b, c.error);
  },

  validator: (c) => {
    // Time-loop swirl above
    drawCreatureBase(c, 10, 8);
    const { ctx, cx, cy, color, frame } = c;
    const spin = -frame * 0.05;
    ctx.strokeStyle = rgba(color, 0.9);
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    for (let i = 0; i < 12; i++) {
      const a = spin + (i / 12) * Math.PI * 2;
      const r = 4 + i * 0.2;
      const px = cx + Math.cos(a) * r;
      const py = cy - 10 + Math.sin(a) * r * 0.5;
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.stroke();
    const b = eyesClosed(c);
    drawEye(ctx, cx - 3, cy - 1, b, c.error);
    drawEye(ctx, cx + 3, cy - 1, b, c.error);
  },

  miner: (c) => {
    // Pickaxe that swings when busy
    drawCreatureBase(c, 10, 8);
    const { ctx, cx, cy, color, frame, busy } = c;
    const angle = busy ? Math.sin(frame * 0.2) * 0.7 : -0.3;
    ctx.save();
    ctx.translate(cx + 9, cy - 5);
    ctx.rotate(angle);
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(6, -6);
    ctx.moveTo(4, -8);
    ctx.lineTo(8, -4);
    ctx.stroke();
    ctx.restore();
    const b = eyesClosed(c);
    drawEye(ctx, cx - 3, cy - 1, b, c.error);
    drawEye(ctx, cx + 2, cy - 1, b, c.error);
  },

  trainer: (c) => {
    // Three-node brain squiggle above
    drawCreatureBase(c, 10, 8);
    const { ctx, cx, cy, color, frame, busy } = c;
    const nodes = [
      { x: cx - 4, y: cy - 11 },
      { x: cx + 4, y: cy - 13 },
      { x: cx,     y: cy - 16 },
    ];
    ctx.strokeStyle = rgba(color, 0.6);
    ctx.lineWidth = 0.9;
    ctx.beginPath();
    ctx.moveTo(nodes[0].x, nodes[0].y);
    ctx.lineTo(nodes[2].x, nodes[2].y);
    ctx.lineTo(nodes[1].x, nodes[1].y);
    ctx.stroke();
    for (let i = 0; i < nodes.length; i++) {
      const pulse = busy ? 0.5 + 0.5 * Math.sin(frame * 0.15 + i * 1.7) : 0.6;
      ctx.fillStyle = rgba(color, pulse);
      ctx.beginPath();
      ctx.arc(nodes[i].x, nodes[i].y, 1.8, 0, Math.PI * 2);
      ctx.fill();
    }
    const b = eyesClosed(c);
    drawEye(ctx, cx - 3, cy, b, c.error);
    drawEye(ctx, cx + 3, cy, b, c.error);
  },

  researcher: (c) => {
    // Magnifying glass that hovers
    drawCreatureBase(c, 10, 8);
    const { ctx, cx, cy, color, frame, busy } = c;
    const drift = busy ? Math.sin(frame * 0.06) * 3 : 0;
    const gx = cx + 9 + drift;
    const gy = cy - 6;
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.arc(gx, gy, 3, 0, Math.PI * 2);
    ctx.moveTo(gx + 2, gy + 2);
    ctx.lineTo(gx + 5, gy + 5);
    ctx.stroke();
    const b = eyesClosed(c);
    drawEye(ctx, cx - 3, cy - 1, b, c.error);
    drawEye(ctx, cx + 2, cy - 1, b, c.error);
  },

  executor: (c) => {
    // Two buy/sell indicator lights above
    drawCreatureBase(c, 10, 8);
    const { ctx, cx, cy, frame, busy } = c;
    const buyA = busy ? 0.3 + 0.7 * Math.abs(Math.sin(frame * 0.12)) : 0.4;
    const sellA = busy ? 0.3 + 0.7 * Math.abs(Math.cos(frame * 0.12)) : 0.4;
    ctx.fillStyle = rgba("#34d399", buyA);
    ctx.beginPath();
    ctx.arc(cx - 4, cy - 11, 1.6, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = rgba("#f87171", sellA);
    ctx.beginPath();
    ctx.arc(cx + 4, cy - 11, 1.6, 0, Math.PI * 2);
    ctx.fill();
    const b = eyesClosed(c);
    drawEye(ctx, cx - 3, cy - 1, b, c.error);
    drawEye(ctx, cx + 3, cy - 1, b, c.error);
  },

  risk_monitor: (c) => {
    // Tiny shield crest above
    drawCreatureBase(c, 10, 8);
    const { ctx, cx, cy, color } = c;
    ctx.fillStyle = rgba(color, 0.7);
    ctx.strokeStyle = color;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx - 4, cy - 10);
    ctx.lineTo(cx + 4, cy - 10);
    ctx.lineTo(cx + 4, cy - 6);
    ctx.lineTo(cx, cy - 2);
    ctx.lineTo(cx - 4, cy - 6);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
    const b = eyesClosed(c);
    drawEye(ctx, cx - 3, cy + 2, b, c.error);
    drawEye(ctx, cx + 3, cy + 2, b, c.error);
  },

  reporter: (c) => {
    // Paper strip tongue
    drawCreatureBase(c, 10, 8);
    const { ctx, cx, cy, color, frame, busy } = c;
    const len = busy ? 6 + (Math.sin(frame * 0.15) + 1) * 3 : 4;
    ctx.fillStyle = "#e3ecf7";
    ctx.fillRect(cx - 2, cy + 6, 4, len);
    // Ink lines on paper
    ctx.fillStyle = rgba(color, 0.8);
    for (let i = 0; i < 3; i++) {
      ctx.fillRect(cx - 1.5, cy + 7 + i * 2, 3, 0.6);
    }
    const b = eyesClosed(c);
    drawEye(ctx, cx - 3, cy - 2, b, c.error);
    drawEye(ctx, cx + 3, cy - 2, b, c.error);
  },

  compliance: (c) => {
    // Stamp hat that pounds when busy
    drawCreatureBase(c, 10, 8);
    const { ctx, cx, cy, color, frame, busy } = c;
    const pound = busy ? -Math.abs(Math.sin(frame * 0.2)) * 4 : 0;
    ctx.fillStyle = rgba(color, 0.85);
    ctx.fillRect(cx - 5, cy - 10 + pound, 10, 2);
    ctx.fillRect(cx - 1, cy - 14 + pound, 2, 4);
    const b = eyesClosed(c);
    drawEye(ctx, cx - 3, cy, b, c.error);
    drawEye(ctx, cx + 3, cy, b, c.error);
  },

  debugger: (c) => {
    // Bug with two antennae
    drawCreatureBase(c, 10, 8);
    const { ctx, cx, cy, color, frame, busy } = c;
    const wiggle = busy ? Math.sin(frame * 0.18) * 0.4 : 0;
    ctx.strokeStyle = color;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx - 2, cy - 7);
    ctx.lineTo(cx - 4 + wiggle, cy - 13);
    ctx.moveTo(cx + 2, cy - 7);
    ctx.lineTo(cx + 4 - wiggle, cy - 13);
    ctx.stroke();
    // Antenna tips
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(cx - 4 + wiggle, cy - 13, 1.1, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(cx + 4 - wiggle, cy - 13, 1.1, 0, Math.PI * 2);
    ctx.fill();
    const b = eyesClosed(c);
    drawEye(ctx, cx - 3, cy - 1, b, c.error);
    drawEye(ctx, cx + 3, cy - 1, b, c.error);
  },
};

function drawCreature(
  ctx: CanvasRenderingContext2D,
  name: string,
  cx: number,
  cy: number,
  color: string,
  frame: number,
  state: FloorAgent["state"],
): void {
  const species = SPECIES[name];
  const c: CreatureCtx = {
    ctx,
    cx,
    cy,
    color,
    frame,
    busy: state === "busy",
    error: state === "error",
    complete: state === "complete",
    seedVal: seed(name),
  };
  if (species) {
    species(c);
  } else {
    drawCreatureBase(c, 10, 8);
    const b = eyesClosed(c);
    drawEye(ctx, cx - 3, cy - 1, b, c.error);
    drawEye(ctx, cx + 3, cy - 1, b, c.error);
  }

  // Sleeping Zzz above every pet when idle.
  drawSleepingZzz(c, cx + 8, cy - 10);

  // Complete sparkle: tiny plus above
  if (state === "complete" && frame % 90 < 45) {
    const a = 1 - (frame % 90) / 45;
    ctx.strokeStyle = rgba("#34d399", a);
    ctx.lineWidth = 1.3;
    ctx.beginPath();
    ctx.moveTo(cx + 8, cy - 14);
    ctx.lineTo(cx + 12, cy - 14);
    ctx.moveTo(cx + 10, cy - 16);
    ctx.lineTo(cx + 10, cy - 12);
    ctx.stroke();
  }
  // Error exclamation above
  if (state === "error") {
    ctx.fillStyle = "#f87171";
    ctx.font = 'bold 10px "JetBrains Mono", ui-monospace, monospace';
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("!", cx + 10, cy - 12);
  }
}

// ---------------------------------------------------------------------------
// Status dot (small, top-right of portrait)
// ---------------------------------------------------------------------------

function drawStatusDot(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  state: FloorAgent["state"],
  frame: number,
): void {
  let color: string;
  let glow = 0;
  switch (state) {
    case "busy":     color = "#d4a517"; glow = 0.4 + 0.3 * Math.sin(frame * 0.12); break;
    case "error":    color = "#f87171"; glow = 0.5; break;
    case "complete": color = "#34d399"; glow = Math.max(0, 1 - (frame % 60) / 30); break;
    default:         color = "#34d399"; glow = 0;
  }
  if (glow > 0) {
    ctx.fillStyle = rgba(color, glow);
    ctx.beginPath();
    ctx.arc(x, y, 6, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(x, y, 3, 0, Math.PI * 2);
  ctx.fill();
}

function drawLockIcon(ctx: CanvasRenderingContext2D, x: number, y: number): void {
  ctx.save();
  ctx.strokeStyle = LOCK_COLOR;
  ctx.fillStyle = LOCK_COLOR;
  ctx.lineWidth = 1.3;
  ctx.beginPath();
  ctx.arc(x, y - 3, 4, Math.PI, 0);
  ctx.stroke();
  ctx.fillRect(x - 5, y, 10, 7);
  ctx.restore();
}

// ---------------------------------------------------------------------------
// Vitals ribbon — a tiny moving waveform even at idle so the pet feels alive.
// ---------------------------------------------------------------------------

function drawVitals(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  color: string,
  frame: number,
  busy: boolean,
  seedVal: number,
): void {
  const h = 8;
  // Background trough
  ctx.fillStyle = "#05090f";
  roundRect(ctx, x, y, w, h, 2);
  ctx.fill();

  ctx.save();
  ctx.beginPath();
  ctx.rect(x + 1, y + 1, w - 2, h - 2);
  ctx.clip();

  // Heartbeat-ish waveform: base sine plus occasional spike
  ctx.strokeStyle = rgba(color, busy ? 0.95 : 0.55);
  ctx.lineWidth = 1.1;
  ctx.beginPath();
  const speed = busy ? 0.18 : 0.06;
  const amp = busy ? 3 : 1.6;
  for (let i = 0; i <= w; i++) {
    const t = i + frame * (busy ? 2 : 1);
    const base = Math.sin(t * speed + seedVal * 6) * amp;
    // spike once per period
    const spikeT = (t * 0.1 + seedVal * 10) % 20;
    const spike = spikeT < 1 ? -amp * 1.8 : spikeT < 2 ? amp * 2 : 0;
    const py = y + h / 2 + base + spike;
    if (i === 0) ctx.moveTo(x + i, py);
    else ctx.lineTo(x + i, py);
  }
  ctx.stroke();
  ctx.restore();
}

// ---------------------------------------------------------------------------
// Log panel — the caretaker's notebook
// ---------------------------------------------------------------------------

function truncateToWidth(
  ctx: CanvasRenderingContext2D,
  text: string,
  maxWidth: number,
): string {
  if (ctx.measureText(text).width <= maxWidth) return text;
  let lo = 0;
  let hi = text.length;
  while (lo < hi) {
    const mid = Math.floor((lo + hi + 1) / 2);
    const candidate = text.slice(0, mid) + "…";
    if (ctx.measureText(candidate).width <= maxWidth) lo = mid;
    else hi = mid - 1;
  }
  return text.slice(0, lo) + "…";
}

function drawLogPanel(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  history: AgentLogEntry[],
  nowMs: number,
): void {
  // Inset background — inner panel with faint scanlines
  ctx.fillStyle = "#05080f";
  roundRect(ctx, x, y, w, h, 4);
  ctx.fill();

  ctx.save();
  ctx.beginPath();
  ctx.rect(x, y, w, h);
  ctx.clip();

  // Inner scanlines (even fainter than outer)
  ctx.fillStyle = "rgba(255,255,255,0.015)";
  for (let sy = y + 1; sy < y + h; sy += 2) {
    ctx.fillRect(x, sy, w, 1);
  }

  if (history.length === 0) {
    ctx.fillStyle = rgba("#4a5a7a", 0.7);
    ctx.font = '8px "JetBrains Mono", ui-monospace, monospace';
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillText("· awaiting task ·", x + 6, y + h / 2);
    ctx.restore();
    return;
  }

  const lineH = 10;
  const padX = 6;
  const padY = 4;
  const maxLines = Math.floor((h - padY * 2) / lineH);
  const visible = history.slice(0, maxLines);
  const textW = w - padX * 2;

  ctx.font = '8px "JetBrains Mono", ui-monospace, monospace';
  ctx.textAlign = "left";
  ctx.textBaseline = "top";

  for (let i = 0; i < visible.length; i++) {
    const entry = visible[i];
    const yi = y + padY + i * lineH;
    const age = i;  // 0 = newest, higher = older
    const fade = Math.max(0.35, 1 - age * 0.18);

    // Typewriter reveal on the NEWEST entry only
    let shown = entry.text;
    if (i === 0) {
      const elapsed = nowMs - entry.ts;
      const reveal = Math.floor(elapsed * TYPEWRITER_CHARS_PER_MS);
      shown = entry.text.slice(0, Math.max(1, reveal));
    }

    const truncated = truncateToWidth(ctx, shown, textW);
    const color = LOG_COLORS[entry.kind] || LOG_COLORS.note;
    ctx.fillStyle = rgba(color, fade);
    ctx.fillText(truncated, x + padX, yi);

    // Blinking cursor on newest while still typing
    if (i === 0 && shown.length < entry.text.length) {
      const cursorX = x + padX + ctx.measureText(truncated.replace(/…$/, "")).width + 1;
      const blink = Math.floor(nowMs / 200) % 2 === 0;
      if (blink) {
        ctx.fillStyle = rgba(color, fade);
        ctx.fillRect(cursorX, yi, 3, 8);
      }
    }
  }

  ctx.restore();
}

// ---------------------------------------------------------------------------
// Individual station (the glass terrarium box)
// ---------------------------------------------------------------------------

function drawStation(
  ctx: CanvasRenderingContext2D,
  station: StationConfig,
  agent: FloorAgent,
  isSelected: boolean,
  frame: number,
  nowMs: number,
  lang: string,
): void {
  const { x, y, width: w, height: h } = station;
  const color = station.theme.color;
  const isLocked = agent.locked;
  const isBusy = agent.state === "busy";
  const isComplete = agent.state === "complete";
  const isIdle = agent.state === "idle";
  const isError = agent.state === "error";
  const showLockedActivity = isLocked && (isBusy || isComplete || isError || (agent.logHistory?.length ?? 0) > 0);
  const allowRuntimeVisualization = !isLocked || showLockedActivity;
  const seedVal = seed(station.name);

  ctx.save();

  if (isLocked) {
    ctx.globalAlpha = showLockedActivity ? 0.8 : 0.45;
  }

  // Outer aura per state — faint glow around the box
  if (isIdle && !isLocked) {
    const glow = 0.05 + 0.04 * Math.sin(frame * 0.04 + seedVal * 6);
    ctx.shadowColor = color;
    ctx.shadowBlur = 12;
    ctx.fillStyle = rgba(color, glow);
    roundRect(ctx, x - 2, y - 2, w + 4, h + 4, CORNER_RADIUS + 2);
    ctx.fill();
    ctx.shadowBlur = 0;
  }
  if (isBusy && allowRuntimeVisualization) {
    const pulse = 0.10 + 0.10 * Math.sin(frame * 0.1);
    ctx.shadowColor = "#d4a517";
    ctx.shadowBlur = 18 + 6 * Math.sin(frame * 0.1);
    ctx.fillStyle = rgba("#d4a517", pulse);
    roundRect(ctx, x - 3, y - 3, w + 6, h + 6, CORNER_RADIUS + 3);
    ctx.fill();
    ctx.shadowBlur = 0;
  }
  if (isComplete && allowRuntimeVisualization) {
    const flash = Math.max(0, 0.3 - (frame % 90) / 300);
    if (flash > 0) {
      ctx.shadowColor = "#34d399";
      ctx.shadowBlur = 20;
      ctx.fillStyle = rgba("#34d399", flash);
      roundRect(ctx, x - 2, y - 2, w + 4, h + 4, CORNER_RADIUS + 2);
      ctx.fill();
      ctx.shadowBlur = 0;
    }
  }
  if (isError && allowRuntimeVisualization) {
    const pulse = 0.15 + 0.1 * Math.sin(frame * 0.2);
    ctx.shadowColor = "#ef4444";
    ctx.shadowBlur = 14;
    ctx.fillStyle = rgba("#ef4444", pulse);
    roundRect(ctx, x - 2, y - 2, w + 4, h + 4, CORNER_RADIUS + 2);
    ctx.fill();
    ctx.shadowBlur = 0;
  }

  // Station backplate — dual layer for depth
  ctx.fillStyle = STATION_BG;
  roundRect(ctx, x, y, w, h, CORNER_RADIUS);
  ctx.fill();

  // Inner panel
  const ipx = x + 1;
  const ipy = y + 1;
  const ipw = w - 2;
  const iph = h - 2;
  ctx.fillStyle = STATION_BG_INNER;
  roundRect(ctx, ipx, ipy, ipw, iph, CORNER_RADIUS - 1);
  ctx.fill();

  // Border
  ctx.strokeStyle = isSelected ? SELECTED_BORDER : STATION_BORDER;
  ctx.lineWidth = isSelected ? 1.8 : 1;
  roundRect(ctx, x, y, w, h, CORNER_RADIUS);
  ctx.stroke();

  if (isSelected) {
    ctx.shadowColor = SELECTED_BORDER;
    ctx.shadowBlur = 8;
    roundRect(ctx, x, y, w, h, CORNER_RADIUS);
    ctx.stroke();
    ctx.shadowBlur = 0;
  }

  // Scanlines across the whole box (gives it the CRT feel)
  drawScanlines(ctx, x + 1, y + 1, w - 2, h - 2);

  // ---- Layout within the box ----
  // Portrait column: left 40px. The rest is name/status/log.
  const portraitCX = x + 20;
  const portraitCY = y + 22;

  // Portrait frame — a circle aperture
  ctx.save();
  ctx.beginPath();
  ctx.arc(portraitCX, portraitCY, PORTRAIT_RADIUS, 0, Math.PI * 2);
  ctx.closePath();
  ctx.fillStyle = "#060a14";
  ctx.fill();
  ctx.strokeStyle = rgba(color, 0.5);
  ctx.lineWidth = 1;
  ctx.stroke();

  // Creature inside aperture
  ctx.beginPath();
  ctx.arc(portraitCX, portraitCY, PORTRAIT_RADIUS - 1, 0, Math.PI * 2);
  ctx.clip();

  if (isLocked) {
    drawLockIcon(ctx, portraitCX, portraitCY);
  } else {
    drawCreature(ctx, station.name, portraitCX, portraitCY, color, frame, agent.state);
  }
  ctx.restore();

  // Name + status dot row (to the right of portrait)
  const infoX = x + 40;
  const nameY = y + 12;
  const statusDotX = x + w - 10;

  ctx.fillStyle = isLocked ? LOCK_COLOR : NAME_COLOR;
  ctx.font = 'bold 10px "JetBrains Mono", ui-monospace, monospace';
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  const displayName = getStationDisplayName(station, lang).toUpperCase();
  const maxNameW = statusDotX - infoX - 14;
  ctx.fillText(truncateToWidth(ctx, displayName, maxNameW), infoX, nameY);

  if (allowRuntimeVisualization) {
    drawStatusDot(ctx, statusDotX, nameY, agent.state, frame);
  }

  // Vitals ribbon below name
  if (!isLocked || showLockedActivity) {
    drawVitals(ctx, infoX, y + 22, w - 40 - 8, color, frame, isBusy, seedVal);
  }

  // Log panel occupies bottom of box (below portrait area)
  const logX = x + 6;
  const logY = y + 44;
  const logW = w - 12;
  const logH = h - 50;

  if (allowRuntimeVisualization) {
    drawLogPanel(ctx, logX, logY, logW, logH, agent.logHistory || [], nowMs);
  }

  ctx.restore();
}

// ---------------------------------------------------------------------------
// Broadcast pulse
// ---------------------------------------------------------------------------

function drawBroadcastPulse(
  ctx: CanvasRenderingContext2D,
  centerX: number,
  centerY: number,
  frame: number,
): void {
  const ringCount = 3;
  const period = 120;

  for (let i = 0; i < ringCount; i++) {
    const phase = (frame + i * (period / ringCount)) % period;
    const t = phase / period;
    const radius = t * 160;
    const alpha = Math.max(0, 0.22 * (1 - t));

    ctx.strokeStyle = rgba("#3b82f6", alpha);
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
    ctx.stroke();
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export function renderModernFloor(
  ctx: CanvasRenderingContext2D,
  agents: ReadonlyArray<FloorAgent>,
  selectedAgent: string | null,
  frame: number,
  lang: string,
): void {
  const w = ctx.canvas.width;
  const h = ctx.canvas.height;
  const nowMs = performance.now();

  drawBackground(ctx, w, h);
  drawZoneLabels(ctx, lang);
  drawBroadcastPulse(ctx, w / 2, h / 2, frame);

  for (const agent of agents) {
    const station = getStationByName(agent.name);
    if (!station) continue;
    const isSelected = agent.name === selectedAgent;
    drawStation(ctx, station, agent, isSelected, frame, nowMs, lang);
  }
}

export function hitTestStation(
  x: number,
  y: number,
  agents: ReadonlyArray<FloorAgent>,
): string | null {
  for (let i = agents.length - 1; i >= 0; i--) {
    const agent = agents[i];
    const station = getStationByName(agent.name);
    if (!station) continue;
    if (
      x >= station.x &&
      x <= station.x + station.width &&
      y >= station.y &&
      y <= station.y + station.height
    ) {
      return agent.name;
    }
  }
  return null;
}
