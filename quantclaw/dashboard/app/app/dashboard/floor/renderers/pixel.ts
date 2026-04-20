import type { FloorAgent } from "../types";
import {
  STATIONS,
  getStationByName,
  getStationDisplayName,
  getZoneDisplayName,
  type StationConfig,
} from "../stations";
import { getSprite, drawSprite, drawTile, type SpriteSheet } from "../sprites";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SELECTED_BORDER = "#d4a517";
const TEXT_COLOR = "#c8d1db";
const LABEL_COLOR = "#4a5a7a";
const LOCK_COLOR = "#2a3a5a";

const TILE_SIZE = 16;
const TILE_SCALE = 2; // render 16px tiles at 32px
const STATUS_DOT_SIZE = 4;
const SPEECH_PADDING = 6;
const SPEECH_TAIL = 4;

// ---------------------------------------------------------------------------
// Tile indices for the "tiles" sheet (16x16 frames, 16 cols x 16 rows)
// These are approximate indices into a typical RPG interior tileset.
// ---------------------------------------------------------------------------

// Tile indices mapped from visual inspection of tileset_16x16_interior.png
// Sheet is 16 cols x 16 rows (256x256, 16px tiles)
// Row 0: walls/windows/doors | Row 1: furniture (bed, curtain, dresser, chairs)
// Row 2: more walls/bed      | Row 3: green floor, shelves
// Row 4: blue floor, drawers | Row 5+: variations

const FLOOR_TILE_A = 48;       // green solid floor (row 3, col 0)
const FLOOR_TILE_B = 49;       // green floor variant (row 3, col 1)
const WALL_TOP = 1;            // wall top (row 0, col 1)
const WALL_SIDE = 16;          // wall side (row 1, col 0)
const WALL_CORNER_TL = 0;     // top-left corner (row 0, col 0)
const WALL_CORNER_TR = 3;     // top-right corner
const WALL_CORNER_BL = 32;    // bottom-left corner
const WALL_CORNER_BR = 35;    // bottom-right corner
const WALL_BOTTOM = 33;       // bottom wall
const DESK_TILE = 25;         // dresser/desk (row 1, col 9) — the wooden dresser
const CHAIR_TILE = 29;        // chair (row 1, col 13)
const MONITOR_TILE = 27;      // small table/screen (row 1, col 11)
const BOOKSHELF_TILE = 26;    // bookshelf (row 1, col 10)
const PLANT_TILE = 77;        // pot (row 4, col 13)
const CABINET_TILE = 73;      // drawer/cabinet (row 4, col 9)
const RUG_TILE = 50;          // patterned floor accent (row 3, col 2)

// Office sheet not used — interior tileset has enough furniture
const OFFICE_DESK = 8;
const OFFICE_CHAIR = 9;
const OFFICE_MONITOR = 16;
const OFFICE_SHELF = 24;
const OFFICE_CABINET = 25;

// Character frame indices — assign a unique base per agent so they look different
const AGENT_CHAR_FRAMES: Record<string, { sheet: string; base: number; idleFrames: number[]; busyFrames: number[] }> = {
  scheduler:    { sheet: "chars", base: 0,   idleFrames: [0, 1],       busyFrames: [0, 1, 2, 3] },
  sentinel:     { sheet: "chars", base: 50,  idleFrames: [50, 51],     busyFrames: [50, 51, 52, 53] },
  ingestor:     { sheet: "chars", base: 100, idleFrames: [100, 101],   busyFrames: [100, 101, 102, 103] },
  validator:    { sheet: "chars", base: 150, idleFrames: [150, 151],   busyFrames: [150, 151, 152, 153] },
  miner:        { sheet: "chars_male", base: 0,  idleFrames: [0, 1],   busyFrames: [0, 1, 2, 3] },
  trainer:      { sheet: "chars_male", base: 6,  idleFrames: [6, 7],   busyFrames: [6, 7, 8, 9] },
  researcher:   { sheet: "chars", base: 200, idleFrames: [200, 201],   busyFrames: [200, 201, 202, 203] },
  executor:     { sheet: "chars_male", base: 12, idleFrames: [12, 13], busyFrames: [12, 13, 14, 15] },
  risk_monitor: { sheet: "chars", base: 250, idleFrames: [250, 251],   busyFrames: [250, 251, 252, 253] },
  reporter:     { sheet: "chars", base: 300, idleFrames: [300, 301],   busyFrames: [300, 301, 302, 303] },
  compliance:   { sheet: "chars", base: 350, idleFrames: [350, 351],   busyFrames: [350, 351, 352, 353] },
  debugger:     { sheet: "chars_male", base: 24, idleFrames: [24, 25], busyFrames: [24, 25, 26, 27] },
};

// Furniture layout per station — which tile sprites to place and where (relative offsets)
interface FurniturePiece {
  sheet: "tiles" | "office";
  tile: number;
  dx: number; // pixel offset from station top-left
  dy: number;
  scale: number;
}

function getStationFurniture(name: string): ReadonlyArray<FurniturePiece> {
  switch (name) {
    case "scheduler":
      return [
        { sheet: "tiles", tile: DESK_TILE, dx: 48, dy: 50, scale: TILE_SCALE },
        { sheet: "tiles", tile: MONITOR_TILE, dx: 48, dy: 34, scale: TILE_SCALE },
        { sheet: "tiles", tile: CHAIR_TILE, dx: 48, dy: 70, scale: TILE_SCALE },
        { sheet: "tiles", tile: BOOKSHELF_TILE, dx: 90, dy: 20, scale: TILE_SCALE },
      ];
    case "sentinel":
      return [
        { sheet: "tiles", tile: DESK_TILE, dx: 48, dy: 50, scale: TILE_SCALE },
        { sheet: "tiles", tile: MONITOR_TILE, dx: 48, dy: 34, scale: TILE_SCALE },
        { sheet: "tiles", tile: MONITOR_TILE, dx: 80, dy: 34, scale: TILE_SCALE },
        { sheet: "tiles", tile: CHAIR_TILE, dx: 60, dy: 70, scale: TILE_SCALE },
      ];
    case "ingestor":
      return [
        { sheet: "tiles", tile: DESK_TILE, dx: 48, dy: 50, scale: TILE_SCALE },
        { sheet: "tiles", tile: MONITOR_TILE, dx: 56, dy: 34, scale: TILE_SCALE },
        { sheet: "tiles", tile: CABINET_TILE, dx: 90, dy: 20, scale: TILE_SCALE },
        { sheet: "tiles", tile: CHAIR_TILE, dx: 48, dy: 70, scale: TILE_SCALE },
      ];
    case "validator":
      return [
        { sheet: "tiles", tile: DESK_TILE, dx: 48, dy: 50, scale: TILE_SCALE },
        { sheet: "tiles", tile: MONITOR_TILE, dx: 48, dy: 34, scale: TILE_SCALE },
        { sheet: "tiles", tile: BOOKSHELF_TILE, dx: 90, dy: 20, scale: TILE_SCALE },
        { sheet: "tiles", tile: CHAIR_TILE, dx: 48, dy: 70, scale: TILE_SCALE },
      ];
    case "miner":
      return [
        { sheet: "tiles", tile: DESK_TILE, dx: 48, dy: 50, scale: TILE_SCALE },
        { sheet: "tiles", tile: MONITOR_TILE, dx: 56, dy: 34, scale: TILE_SCALE },
        { sheet: "tiles", tile: PLANT_TILE, dx: 95, dy: 60, scale: TILE_SCALE },
        { sheet: "tiles", tile: CHAIR_TILE, dx: 48, dy: 70, scale: TILE_SCALE },
      ];
    case "trainer":
      return [
        { sheet: "tiles", tile: DESK_TILE, dx: 48, dy: 50, scale: TILE_SCALE },
        { sheet: "tiles", tile: MONITOR_TILE, dx: 48, dy: 34, scale: TILE_SCALE },
        { sheet: "tiles", tile: MONITOR_TILE, dx: 80, dy: 34, scale: TILE_SCALE },
        { sheet: "tiles", tile: CHAIR_TILE, dx: 60, dy: 70, scale: TILE_SCALE },
      ];
    case "researcher":
      return [
        { sheet: "tiles", tile: DESK_TILE, dx: 48, dy: 50, scale: TILE_SCALE },
        { sheet: "tiles", tile: BOOKSHELF_TILE, dx: 48, dy: 20, scale: TILE_SCALE },
        { sheet: "tiles", tile: BOOKSHELF_TILE, dx: 80, dy: 20, scale: TILE_SCALE },
        { sheet: "tiles", tile: CHAIR_TILE, dx: 60, dy: 70, scale: TILE_SCALE },
      ];
    case "executor":
      return [
        { sheet: "tiles", tile: DESK_TILE, dx: 40, dy: 50, scale: TILE_SCALE },
        { sheet: "tiles", tile: DESK_TILE, dx: 72, dy: 50, scale: TILE_SCALE },
        { sheet: "tiles", tile: MONITOR_TILE, dx: 40, dy: 34, scale: TILE_SCALE },
        { sheet: "tiles", tile: MONITOR_TILE, dx: 72, dy: 34, scale: TILE_SCALE },
        { sheet: "tiles", tile: CHAIR_TILE, dx: 56, dy: 70, scale: TILE_SCALE },
      ];
    case "risk_monitor":
      return [
        { sheet: "tiles", tile: DESK_TILE, dx: 48, dy: 50, scale: TILE_SCALE },
        { sheet: "tiles", tile: MONITOR_TILE, dx: 48, dy: 34, scale: TILE_SCALE },
        { sheet: "tiles", tile: CABINET_TILE, dx: 90, dy: 50, scale: TILE_SCALE },
        { sheet: "tiles", tile: CHAIR_TILE, dx: 48, dy: 70, scale: TILE_SCALE },
      ];
    case "reporter":
      return [
        { sheet: "tiles", tile: DESK_TILE, dx: 48, dy: 50, scale: TILE_SCALE },
        { sheet: "tiles", tile: MONITOR_TILE, dx: 56, dy: 34, scale: TILE_SCALE },
        { sheet: "tiles", tile: BOOKSHELF_TILE, dx: 90, dy: 20, scale: TILE_SCALE },
        { sheet: "tiles", tile: CHAIR_TILE, dx: 48, dy: 70, scale: TILE_SCALE },
      ];
    case "compliance":
      return [
        { sheet: "tiles", tile: DESK_TILE, dx: 48, dy: 50, scale: TILE_SCALE },
        { sheet: "tiles", tile: CABINET_TILE, dx: 48, dy: 20, scale: TILE_SCALE },
        { sheet: "tiles", tile: CABINET_TILE, dx: 80, dy: 20, scale: TILE_SCALE },
        { sheet: "tiles", tile: MONITOR_TILE, dx: 56, dy: 34, scale: TILE_SCALE },
        { sheet: "tiles", tile: CHAIR_TILE, dx: 48, dy: 70, scale: TILE_SCALE },
      ];
    case "debugger":
      return [
        { sheet: "tiles", tile: DESK_TILE, dx: 48, dy: 50, scale: TILE_SCALE },
        { sheet: "tiles", tile: MONITOR_TILE, dx: 48, dy: 34, scale: TILE_SCALE },
        { sheet: "tiles", tile: PLANT_TILE, dx: 95, dy: 60, scale: TILE_SCALE },
        { sheet: "tiles", tile: CHAIR_TILE, dx: 48, dy: 70, scale: TILE_SCALE },
      ];
    default:
      return [
        { sheet: "tiles", tile: DESK_TILE, dx: 48, dy: 50, scale: TILE_SCALE },
        { sheet: "tiles", tile: CHAIR_TILE, dx: 48, dy: 70, scale: TILE_SCALE },
      ];
  }
}

// ---------------------------------------------------------------------------
// Retro palette snapping (kept for UI overlays)
// ---------------------------------------------------------------------------

const RETRO_PALETTE: ReadonlyArray<string> = [
  "#ff004d", "#ffa300", "#ffec27", "#00e436",
  "#29adff", "#83769c", "#ff77a8", "#ffccaa",
  "#ab5236", "#ff6c24", "#008751", "#1d2b53",
  "#7e2553", "#c2c3c7", "#fff1e8", "#5f574f",
];

function snapToRetro(hex: string): string {
  const { r, g, b } = hexToRgb(hex);
  let bestDist = Infinity;
  let best = hex;
  for (const p of RETRO_PALETTE) {
    const c = hexToRgb(p);
    const dist = (r - c.r) ** 2 + (g - c.g) ** 2 + (b - c.b) ** 2;
    if (dist < bestDist) {
      bestDist = dist;
      best = p;
    }
  }
  return best;
}

// ---------------------------------------------------------------------------
// Utility helpers
// ---------------------------------------------------------------------------

function hexToRgb(hex: string): { r: number; g: number; b: number } {
  const n = parseInt(hex.replace("#", ""), 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

function rgba(hex: string, alpha: number): string {
  const { r, g, b } = hexToRgb(hex);
  return `rgba(${r},${g},${b},${alpha})`;
}

function spritesReady(): boolean {
  const tiles = getSprite("tiles");
  const chars = getSprite("chars");
  return Boolean(tiles?.loaded && chars?.loaded);
}

// ---------------------------------------------------------------------------
// Background — tiled floor using sprite sheet
// ---------------------------------------------------------------------------

function drawBackground(ctx: CanvasRenderingContext2D, w: number, h: number): void {
  const tiles = getSprite("tiles");

  if (!tiles?.loaded) {
    // Fallback: solid dark background
    ctx.fillStyle = "#1a1a2e";
    ctx.fillRect(0, 0, w, h);
    return;
  }

  const tileW = TILE_SIZE * TILE_SCALE;

  for (let ty = 0; ty < h; ty += tileW) {
    for (let tx = 0; tx < w; tx += tileW) {
      const checker = ((Math.floor(tx / tileW) + Math.floor(ty / tileW)) % 2 === 0);
      drawTile(ctx, tiles, checker ? FLOOR_TILE_A : FLOOR_TILE_B, tx, ty, TILE_SCALE);
    }
  }
}

// ---------------------------------------------------------------------------
// Wall borders around zones
// ---------------------------------------------------------------------------

function drawZoneWalls(ctx: CanvasRenderingContext2D): void {
  const tiles = getSprite("tiles");
  if (!tiles?.loaded) return;

  // Collect zone bounding boxes
  const zones = new Map<string, { minX: number; minY: number; maxX: number; maxY: number }>();

  for (const station of STATIONS) {
    const key = station.zone;
    const existing = zones.get(key);
    const right = station.x + station.width;
    const bottom = station.y + station.height;

    if (existing) {
      zones.set(key, {
        minX: Math.min(existing.minX, station.x),
        minY: Math.min(existing.minY, station.y),
        maxX: Math.max(existing.maxX, right),
        maxY: Math.max(existing.maxY, bottom),
      });
    } else {
      zones.set(key, { minX: station.x, minY: station.y, maxX: right, maxY: bottom });
    }
  }

  const tileW = TILE_SIZE * TILE_SCALE;
  const padding = 10;

  zones.forEach((bounds) => {
    const left = bounds.minX - padding;
    const top = bounds.minY - padding - 16; // extra space for zone label
    const right = bounds.maxX + padding;
    const bottom = bounds.maxY + padding + 16; // extra space for name labels

    // Top wall
    for (let tx = left; tx < right; tx += tileW) {
      drawTile(ctx, tiles, WALL_TOP, tx, top, TILE_SCALE);
    }

    // Bottom wall
    for (let tx = left; tx < right; tx += tileW) {
      drawTile(ctx, tiles, WALL_BOTTOM, tx, bottom, TILE_SCALE);
    }

    // Left wall
    for (let ty = top + tileW; ty < bottom; ty += tileW) {
      drawTile(ctx, tiles, WALL_SIDE, left - tileW, ty, TILE_SCALE);
    }

    // Right wall
    for (let ty = top + tileW; ty < bottom; ty += tileW) {
      drawTile(ctx, tiles, WALL_SIDE, right, ty, TILE_SCALE);
    }

    // Corners
    drawTile(ctx, tiles, WALL_CORNER_TL, left - tileW, top, TILE_SCALE);
    drawTile(ctx, tiles, WALL_CORNER_TR, right, top, TILE_SCALE);
    drawTile(ctx, tiles, WALL_CORNER_BL, left - tileW, bottom, TILE_SCALE);
    drawTile(ctx, tiles, WALL_CORNER_BR, right, bottom, TILE_SCALE);

    // Rug/carpet tiles inside the zone (every other row for variety)
    for (let ty = top + tileW; ty < bottom; ty += tileW * 2) {
      for (let tx = left; tx < right; tx += tileW * 2) {
        drawTile(ctx, tiles, RUG_TILE, tx, ty, TILE_SCALE);
      }
    }
  });
}

// ---------------------------------------------------------------------------
// Zone labels — pixel font style
// ---------------------------------------------------------------------------

function drawZoneLabels(ctx: CanvasRenderingContext2D, lang: string): void {
  const drawn = new Set<string>();

  for (const station of STATIONS) {
    const zoneKey = station.zone;
    if (drawn.has(zoneKey)) continue;
    drawn.add(zoneKey);

    const label = getZoneDisplayName(station, lang);
    ctx.save();
    ctx.font = "bold 10px monospace";
    ctx.fillStyle = LABEL_COLOR;
    ctx.textAlign = "left";
    ctx.textBaseline = "bottom";
    ctx.imageSmoothingEnabled = false;

    // Shadow for readability over tiles
    ctx.fillStyle = "#000000";
    ctx.fillText(label.toUpperCase(), station.x + 1, station.y - 3);
    ctx.fillStyle = LABEL_COLOR;
    ctx.fillText(label.toUpperCase(), station.x, station.y - 4);
    ctx.restore();
  }
}

// ---------------------------------------------------------------------------
// Station furniture — sprite-based
// ---------------------------------------------------------------------------

function drawStationFurniture(
  ctx: CanvasRenderingContext2D,
  station: StationConfig,
): void {
  const furniture = getStationFurniture(station.name);

  for (const piece of furniture) {
    const sheet = getSprite(piece.sheet);
    if (!sheet?.loaded) continue;
    drawTile(ctx, sheet, piece.tile, station.x + piece.dx, station.y + piece.dy, piece.scale);
  }
}

// ---------------------------------------------------------------------------
// Agent character — sprite-based with animation
// ---------------------------------------------------------------------------

function drawAgentCharacter(
  ctx: CanvasRenderingContext2D,
  station: StationConfig,
  agent: FloorAgent,
  frame: number,
): void {
  const charConfig = AGENT_CHAR_FRAMES[agent.name];
  if (!charConfig) return;

  const sheet = getSprite(charConfig.sheet);
  if (!sheet?.loaded) return;

  const avatarX = station.x + 10;
  const avatarY = station.y + 30;

  let frameIndex: number;

  if (agent.state === "busy") {
    // Busy: cycle through frames faster
    const busySpeed = 8;
    const idx = Math.floor(frame / busySpeed) % charConfig.busyFrames.length;
    frameIndex = charConfig.busyFrames[idx];
  } else {
    // Idle: bob between 2 frames slowly
    const idleSpeed = 24;
    const idx = Math.floor(frame / idleSpeed) % charConfig.idleFrames.length;
    frameIndex = charConfig.idleFrames[idx];
  }

  // Idle vertical bob
  const bobOffset = agent.state === "idle"
    ? (Math.floor(frame / 20) % 2 === 0 ? 0 : -2)
    : 0;

  drawSprite(ctx, sheet, frameIndex, avatarX, avatarY + bobOffset, TILE_SCALE);
}

// ---------------------------------------------------------------------------
// Pixel pets — per-agent species accents drawn on top of the base sprite.
// Every pet gets: a breathing shadow, a species flourish (tool/emblem), idle
// thought dots, and state reactions (sparkle / droop / dust). Everything is
// drawn on integer pixel positions and snapped to the retro palette so it
// coheres with the sprite characters. Think Tamagotchi meets Liberty's Kids.
// ---------------------------------------------------------------------------

type PixelPetState = FloorAgent["state"];

interface PixelPetCtx {
  ctx: CanvasRenderingContext2D;
  charX: number;       // top-left of the base character sprite
  charY: number;
  color: string;       // station theme color (retro-snapped)
  frame: number;
  state: PixelPetState;
  seedVal: number;     // 0..1 per-agent, for phase offsets
}

const PX = 2;          // base pixel unit — matches TILE_SCALE

// Deterministic per-agent seed. Different phase → blinks / bobs stagger.
function pixelSeed(name: string): number {
  let h = 2166136261;
  for (let i = 0; i < name.length; i++) {
    h ^= name.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0) / 4294967295;
}

function px(ctx: CanvasRenderingContext2D, x: number, y: number, w = 1, h = 1, color?: string): void {
  if (color) ctx.fillStyle = color;
  ctx.fillRect(Math.floor(x), Math.floor(y), w * PX, h * PX);
}

// Breathing shadow — a 2-row horizontal ellipse beneath the character that
// subtly scales with the breath cycle.
function drawPixelShadow(c: PixelPetCtx): void {
  const { ctx, charX, charY, frame, seedVal, state } = c;
  const phase = seedVal * Math.PI * 2;
  const busy = state === "busy";
  const breath = 1 + Math.sin(frame * (busy ? 0.14 : 0.05) + phase) * (busy ? 0.2 : 0.1);
  const baseW = 9;     // in PX units
  const w = Math.max(6, Math.round(baseW * breath));
  const footX = charX + 16 - (w * PX) / 2;
  const footY = charY + 32;

  ctx.save();
  ctx.imageSmoothingEnabled = false;
  ctx.fillStyle = "rgba(0,0,0,0.35)";
  ctx.fillRect(Math.floor(footX), Math.floor(footY), w * PX, PX);
  ctx.fillStyle = "rgba(0,0,0,0.2)";
  ctx.fillRect(Math.floor(footX + PX), Math.floor(footY + PX), (w - 2) * PX, PX);
  ctx.restore();
}

// Selection halo — golden dashed ring, pixel-styled, only when selected.
function drawPixelSelectionHalo(
  ctx: CanvasRenderingContext2D,
  charX: number,
  charY: number,
  frame: number,
): void {
  ctx.save();
  ctx.imageSmoothingEnabled = false;
  const cx = charX + 16;
  const cy = charY + 16;
  const r = 22;
  const dashCount = 12;
  const spin = frame * 0.04;
  ctx.fillStyle = "#ffec27";
  for (let i = 0; i < dashCount; i++) {
    const a = spin + (i / dashCount) * Math.PI * 2;
    if (i % 2 === 0) continue;  // dashed
    const dx = cx + Math.cos(a) * r;
    const dy = cy + Math.sin(a) * r;
    ctx.fillRect(Math.floor(dx), Math.floor(dy), PX, PX);
  }
  ctx.restore();
}

// Sleeping Z — a 3x5 pixel "Z" that drifts up and fades when the pet is idle.
// Three Zs stagger: one big and near the head, progressively smaller and more
// transparent the higher they rise. Cadence varies per agent so the floor
// doesn't sync into a single breath.
//
//   X X X
//       X
//     X
//   X
//   X X X
const Z_SHAPE: ReadonlyArray<[number, number]> = [
  [0, 0], [1, 0], [2, 0],
  [2, 1],
  [1, 2],
  [0, 3],
  [0, 4], [1, 4], [2, 4],
];

function drawPixelZ(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  scale: number,
  alpha: number,
): void {
  ctx.fillStyle = `rgba(200,209,219,${alpha.toFixed(2)})`;
  for (const [dx, dy] of Z_SHAPE) {
    ctx.fillRect(Math.floor(x + dx * scale), Math.floor(y + dy * scale), scale, scale);
  }
}

function drawSleepingZzz(c: PixelPetCtx): void {
  if (c.state !== "idle") return;
  const period = Math.round(180 + c.seedVal * 120);  // 3–5s
  const phase = Math.round(c.seedVal * period);
  const headX = c.charX + 18;
  const headY = c.charY - 4;
  // Three staggered Zs climbing a gentle diagonal.
  for (let i = 0; i < 3; i++) {
    const offset = i * (period / 3);
    const t = (c.frame + phase + offset) % period;
    const lifespan = 72;
    if (t > lifespan) continue;
    const progress = t / lifespan;
    const alpha = (1 - progress) * 0.9;
    const lift = Math.floor(progress * 14);
    const drift = Math.floor(Math.sin(progress * Math.PI * 2) * 2);
    const scale = i === 0 ? PX : PX;  // keep crisp
    const zx = headX + drift - i * PX;
    const zy = headY - lift - i * PX * 3;
    drawPixelZ(c.ctx, zx, zy, scale, alpha);
  }
}

// Complete sparkle — a plus-shaped cluster above the pet for ~1.5s.
function drawCompleteSparkle(c: PixelPetCtx): void {
  if (c.state !== "complete") return;
  const age = c.frame % 90;
  if (age > 60) return;
  const alpha = 1 - age / 60;
  const color = `rgba(0,228,54,${alpha.toFixed(2)})`;
  const sx = c.charX + 20;
  const sy = c.charY - 6;
  c.ctx.fillStyle = color;
  c.ctx.fillRect(sx, sy - PX, PX, PX);
  c.ctx.fillRect(sx, sy + PX, PX, PX);
  c.ctx.fillRect(sx - PX, sy, PX, PX);
  c.ctx.fillRect(sx + PX, sy, PX, PX);
  c.ctx.fillRect(sx, sy, PX, PX);
}

// Error flag — "!" mark above the pet, flashing red.
function drawErrorFlag(c: PixelPetCtx): void {
  if (c.state !== "error") return;
  const flash = Math.floor(c.frame / 15) % 2 === 0;
  if (!flash) return;
  const sx = c.charX + 18;
  const sy = c.charY - 10;
  c.ctx.fillStyle = "#ff004d";
  c.ctx.fillRect(sx, sy, PX, PX * 3);
  c.ctx.fillRect(sx, sy + PX * 4, PX, PX);
}

// Busy dust — tiny ascending particles around the pet.
function drawBusyDust(c: PixelPetCtx): void {
  if (c.state !== "busy") return;
  const { ctx, charX, charY, color, frame } = c;
  ctx.fillStyle = color;
  for (let i = 0; i < 4; i++) {
    const phase = (frame * 2 + i * 23) % 90;
    if (phase > 60) continue;
    const alpha = 1 - phase / 60;
    ctx.fillStyle = `rgba(${hexToRgb(color).r},${hexToRgb(color).g},${hexToRgb(color).b},${alpha.toFixed(2)})`;
    const dx = charX + 4 + ((i * 8 + frame) % 28);
    const dy = charY + 28 - phase * 0.3;
    ctx.fillRect(Math.floor(dx), Math.floor(dy), PX, PX);
  }
}

// ---------------------------------------------------------------------------
// Species flourishes — the personality layer per agent. Drawn AFTER the base
// sprite so it overlays the character. All positions are relative to the
// 32x32 sprite at (charX, charY).
// ---------------------------------------------------------------------------

const PIXEL_SPECIES: Record<string, (c: PixelPetCtx) => void> = {
  scheduler: (c) => {
    // Clock face floating above head, hand rotates
    const { ctx, charX, charY, color, frame } = c;
    const cx = charX + 18;
    const cy = charY - 6;
    // Face (3x3 cluster)
    ctx.fillStyle = color;
    ctx.fillRect(cx - PX, cy - PX, PX * 3, PX * 3);
    ctx.fillStyle = "#0a0a1a";
    ctx.fillRect(cx, cy, PX, PX);
    // Hand (spinning)
    const a = frame * 0.06;
    const hx = cx + Math.round(Math.cos(a) * 1);
    const hy = cy + Math.round(Math.sin(a) * 1);
    ctx.fillStyle = "#fff1e8";
    ctx.fillRect(hx, hy, PX, PX);
  },

  sentinel: (c) => {
    // Radar sweep arc above head
    const { ctx, charX, charY, color, frame, state } = c;
    const cx = charX + 16;
    const cy = charY - 2;
    // Mast (2 pixels vertical)
    ctx.fillStyle = color;
    ctx.fillRect(cx, cy, PX, PX * 2);
    // Rotating dish
    const a = frame * 0.08;
    const dx = cx + Math.round(Math.cos(a) * 3);
    const dy = cy - PX * 2 + Math.round(Math.sin(a) * 2);
    ctx.fillRect(dx, dy, PX * 2, PX);
    // Scan blip (only when busy)
    if (state === "busy" && Math.floor(frame / 12) % 2 === 0) {
      ctx.fillStyle = "#ff004d";
      ctx.fillRect(dx + PX, dy - PX, PX, PX);
    }
  },

  ingestor: (c) => {
    // Funnel above head + falling drops
    const { ctx, charX, charY, color, frame, state } = c;
    const fx = charX + 14;
    const fy = charY - 6;
    ctx.fillStyle = color;
    ctx.fillRect(fx, fy, PX * 4, PX);         // top rim
    ctx.fillRect(fx + PX, fy + PX, PX * 2, PX); // narrow
    if (state === "busy" || state === "idle") {
      const cycle = 40;
      for (let i = 0; i < 3; i++) {
        const t = ((frame + i * 12) % cycle);
        if (t > 20) continue;
        const dropX = fx + PX * 2;
        const dropY = fy - PX * 4 + t;
        ctx.fillStyle = "#29adff";
        ctx.fillRect(dropX, dropY, PX, PX);
      }
    }
  },

  validator: (c) => {
    // Time-spiral orbiting above head
    const { ctx, charX, charY, color, frame } = c;
    const cx = charX + 18;
    const cy = charY - 6;
    const t = frame * 0.1;
    for (let i = 0; i < 6; i++) {
      const a = t + i * 0.6;
      const r = 1 + i * 0.6;
      const dx = cx + Math.round(Math.cos(a) * r);
      const dy = cy + Math.round(Math.sin(a) * r);
      const alpha = 1 - i / 6;
      ctx.fillStyle = `rgba(${hexToRgb(color).r},${hexToRgb(color).g},${hexToRgb(color).b},${alpha.toFixed(2)})`;
      ctx.fillRect(dx, dy, PX, PX);
    }
  },

  miner: (c) => {
    // Swinging pickaxe to the right of the pet
    const { ctx, charX, charY, color, frame, state } = c;
    const px0 = charX + 26;
    const py0 = charY + 8;
    const swing = state === "busy"
      ? Math.sin(frame * 0.22) * 0.8
      : -0.3;
    const hx = Math.round(Math.cos(swing) * 4);
    const hy = Math.round(Math.sin(swing) * 4);
    // Handle
    ctx.fillStyle = "#ab5236";
    for (let i = 0; i < 4; i++) {
      ctx.fillRect(px0 + Math.round(i * Math.cos(swing)), py0 + Math.round(i * Math.sin(swing)), PX, PX);
    }
    // Head
    ctx.fillStyle = color;
    ctx.fillRect(px0 + hx - PX, py0 + hy - PX, PX * 3, PX);
    // Strike sparks when busy
    if (state === "busy" && Math.floor(frame / 8) % 3 === 0) {
      ctx.fillStyle = "#ffec27";
      ctx.fillRect(px0 + hx + PX, py0 + hy, PX, PX);
      ctx.fillRect(px0 + hx + PX * 2, py0 + hy - PX, PX, PX);
    }
  },

  trainer: (c) => {
    // Three pulsing neural nodes above head with connecting lines
    const { ctx, charX, charY, color, frame, state } = c;
    const nodes = [
      { x: charX + 12, y: charY - 4 },
      { x: charX + 22, y: charY - 6 },
      { x: charX + 17, y: charY - 10 },
    ];
    // Connections first
    ctx.fillStyle = `rgba(${hexToRgb(color).r},${hexToRgb(color).g},${hexToRgb(color).b},0.4)`;
    for (let i = 0; i < nodes.length - 1; i++) {
      const a = nodes[i];
      const b = nodes[i + 1];
      const steps = 5;
      for (let s = 0; s < steps; s++) {
        const t = s / steps;
        ctx.fillRect(
          Math.round(a.x + (b.x - a.x) * t),
          Math.round(a.y + (b.y - a.y) * t),
          PX,
          PX,
        );
      }
    }
    // Nodes pulse
    for (let i = 0; i < nodes.length; i++) {
      const pulse = state === "busy"
        ? 0.5 + 0.5 * Math.sin(frame * 0.18 + i * 1.5)
        : 0.7;
      ctx.fillStyle = `rgba(${hexToRgb(color).r},${hexToRgb(color).g},${hexToRgb(color).b},${pulse.toFixed(2)})`;
      ctx.fillRect(nodes[i].x, nodes[i].y, PX * 2, PX * 2);
    }
  },

  researcher: (c) => {
    // Hovering magnifying glass beside head
    const { ctx, charX, charY, color, frame, state } = c;
    const drift = state === "busy" ? Math.round(Math.sin(frame * 0.08) * 2) : 0;
    const gx = charX + 26 + drift;
    const gy = charY + 4;
    // Lens ring (pixel circle approximation)
    ctx.fillStyle = color;
    ctx.fillRect(gx + PX,   gy,         PX * 2, PX);
    ctx.fillRect(gx,        gy + PX,    PX,     PX * 2);
    ctx.fillRect(gx + PX*3, gy + PX,    PX,     PX * 2);
    ctx.fillRect(gx + PX,   gy + PX*3,  PX * 2, PX);
    // Handle
    ctx.fillRect(gx + PX * 4, gy + PX * 3, PX, PX);
    ctx.fillRect(gx + PX * 5, gy + PX * 4, PX, PX);
    // Lens shine
    ctx.fillStyle = "#fff1e8";
    ctx.fillRect(gx + PX, gy + PX, PX, PX);
  },

  executor: (c) => {
    // Buy (green) and sell (red) lights above head, blinking
    const { ctx, charX, charY, frame, state } = c;
    const busy = state === "busy";
    const buyA = busy ? (0.3 + 0.7 * Math.abs(Math.sin(frame * 0.12))) : 0.5;
    const sellA = busy ? (0.3 + 0.7 * Math.abs(Math.cos(frame * 0.12))) : 0.5;
    ctx.fillStyle = `rgba(0,228,54,${buyA.toFixed(2)})`;
    ctx.fillRect(charX + 10, charY - 4, PX * 2, PX * 2);
    ctx.fillStyle = `rgba(255,0,77,${sellA.toFixed(2)})`;
    ctx.fillRect(charX + 20, charY - 4, PX * 2, PX * 2);
    // Bar between them (the terminal edge)
    ctx.fillStyle = "#5f574f";
    ctx.fillRect(charX + 8, charY - 2, PX * 8, PX);
  },

  risk_monitor: (c) => {
    // Shield emblem above head, glows on busy
    const { ctx, charX, charY, color, frame, state } = c;
    const sx = charX + 14;
    const sy = charY - 8;
    const pulse = state === "busy" ? 0.6 + 0.4 * Math.sin(frame * 0.15) : 0.9;
    ctx.fillStyle = `rgba(${hexToRgb(color).r},${hexToRgb(color).g},${hexToRgb(color).b},${pulse.toFixed(2)})`;
    // Shield silhouette
    ctx.fillRect(sx + PX,   sy,         PX * 4, PX);
    ctx.fillRect(sx,        sy + PX,    PX * 6, PX);
    ctx.fillRect(sx + PX,   sy + PX*2,  PX * 4, PX);
    ctx.fillRect(sx + PX*2, sy + PX*3,  PX * 2, PX);
    // Cross mark
    ctx.fillStyle = "#fff1e8";
    ctx.fillRect(sx + PX * 2, sy + PX, PX * 2, PX);
    ctx.fillRect(sx + PX * 2 + PX / 2, sy, PX, PX * 3);
  },

  reporter: (c) => {
    // Paper scroll unfurling beside head
    const { ctx, charX, charY, color, frame, state } = c;
    const busy = state === "busy";
    const len = busy ? 4 + Math.floor((Math.sin(frame * 0.12) + 1) * 3) : 4;
    const sx = charX + 24;
    const sy = charY - 2;
    // Paper body
    ctx.fillStyle = "#fff1e8";
    ctx.fillRect(sx, sy, PX * 3, len * PX);
    // Text lines
    ctx.fillStyle = color;
    for (let i = 0; i < Math.min(len - 1, 4); i++) {
      ctx.fillRect(sx + PX / 2, sy + (i * 2 + 1) * PX, PX * 2, PX / 2);
    }
  },

  compliance: (c) => {
    // Stamp pounding down above the head
    const { ctx, charX, charY, color, frame, state } = c;
    const busy = state === "busy";
    const drop = busy ? Math.round(Math.abs(Math.sin(frame * 0.22)) * 6) : 0;
    const sx = charX + 14;
    const sy = charY - 12 + drop;
    // Handle
    ctx.fillStyle = color;
    ctx.fillRect(sx + PX * 2, sy, PX, PX * 2);
    // Head
    ctx.fillRect(sx, sy + PX * 2, PX * 5, PX * 2);
    // Ink puff when pressed
    if (busy && drop > 4) {
      ctx.fillStyle = "rgba(255,241,232,0.6)";
      ctx.fillRect(sx - PX, sy + PX * 4 + PX, PX, PX);
      ctx.fillRect(sx + PX * 5, sy + PX * 4 + PX, PX, PX);
    }
  },

  debugger: (c) => {
    // Two wiggling antennae with glowing tips
    const { ctx, charX, charY, color, frame, state } = c;
    const cx = charX + 16;
    const cy = charY - 2;
    const wiggle = state === "busy" ? Math.round(Math.sin(frame * 0.2) * 2) : 0;
    ctx.fillStyle = color;
    // Left antenna
    ctx.fillRect(cx - PX * 2,     cy - PX,     PX, PX);
    ctx.fillRect(cx - PX * 3 + wiggle, cy - PX * 2, PX, PX);
    ctx.fillRect(cx - PX * 4 + wiggle, cy - PX * 3, PX, PX);
    // Right antenna
    ctx.fillRect(cx + PX * 2,     cy - PX,     PX, PX);
    ctx.fillRect(cx + PX * 3 - wiggle, cy - PX * 2, PX, PX);
    ctx.fillRect(cx + PX * 4 - wiggle, cy - PX * 3, PX, PX);
    // Glowing tips
    ctx.fillStyle = "#ffec27";
    ctx.fillRect(cx - PX * 4 + wiggle, cy - PX * 4, PX, PX);
    ctx.fillRect(cx + PX * 4 - wiggle, cy - PX * 4, PX, PX);
  },
};

function drawPixelPet(
  ctx: CanvasRenderingContext2D,
  station: StationConfig,
  agent: FloorAgent,
  frame: number,
  isSelected: boolean,
): void {
  const charX = station.x + 10;
  const charY = station.y + 30;
  const color = snapToRetro(station.theme.color);
  const seedVal = pixelSeed(station.name);
  const c: PixelPetCtx = {
    ctx,
    charX,
    charY,
    color,
    frame,
    state: agent.state,
    seedVal,
  };

  // Draw order: shadow → selection → species flourish → dust/sparkle/flag → thought
  drawPixelShadow(c);
  if (isSelected) drawPixelSelectionHalo(ctx, charX, charY, frame);

  // Species flourishes dim while the pet sleeps — tools rest too.
  const drawer = PIXEL_SPECIES[station.name];
  if (drawer) {
    ctx.save();
    if (agent.state === "idle") ctx.globalAlpha = 0.4;
    drawer(c);
    ctx.restore();
  }

  drawBusyDust(c);
  drawCompleteSparkle(c);
  drawErrorFlag(c);
  drawSleepingZzz(c);
}

// ---------------------------------------------------------------------------
// Crab mascot — near Scheduler as the CEO's pet
// ---------------------------------------------------------------------------

function drawCrabMascot(ctx: CanvasRenderingContext2D, frame: number): void {
  const schedulerStation = getStationByName("scheduler");
  if (!schedulerStation) return;

  // Place crab to the right of the scheduler desk area
  const crabX = schedulerStation.x + schedulerStation.width - 40;
  const crabY = schedulerStation.y + schedulerStation.height - 50;

  // Determine if we show walk or idle
  const cyclePhase = Math.floor(frame / 120) % 3; // 0,1 = idle, 2 = walk

  if (cyclePhase < 2) {
    // Idle: alternate between two idle frames
    const idle1 = getSprite("crab_idle1");
    const idle2 = getSprite("crab_idle2");

    if (idle1?.loaded && idle2?.loaded) {
      const idleSheet = (Math.floor(frame / 30) % 2 === 0) ? idle1 : idle2;
      // Crab is 64x64, draw at half scale so it fits in the station
      drawSprite(ctx, idleSheet, 0, crabX, crabY, 0.5);
    }
  } else {
    // Walk animation
    const walkSheet = getSprite("crab_walk");
    if (walkSheet?.loaded) {
      const walkFrame = Math.floor(frame / 10) % (walkSheet.cols * walkSheet.rows);
      drawSprite(ctx, walkSheet, walkFrame, crabX, crabY, 0.5);
    }
  }
}

// ---------------------------------------------------------------------------
// Status dot
// ---------------------------------------------------------------------------

function drawStatusDot(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  state: FloorAgent["state"],
  frame: number,
): void {
  let color: string;

  switch (state) {
    case "idle":
      color = "#00e436";
      break;
    case "busy":
      color = "#ffa300";
      break;
    case "error":
      color = "#ff004d";
      break;
    case "complete":
      color = "#00e436";
      break;
  }

  if (state === "busy") {
    const blink = Math.floor(frame / 10) % 2 === 0;
    if (blink) {
      ctx.fillStyle = rgba(color, 0.4);
      ctx.fillRect(x - STATUS_DOT_SIZE, y - STATUS_DOT_SIZE, STATUS_DOT_SIZE * 2, STATUS_DOT_SIZE * 2);
    }
  }

  ctx.fillStyle = color;
  ctx.fillRect(
    x - STATUS_DOT_SIZE / 2,
    y - STATUS_DOT_SIZE / 2,
    STATUS_DOT_SIZE,
    STATUS_DOT_SIZE,
  );
}

// ---------------------------------------------------------------------------
// Lock icon
// ---------------------------------------------------------------------------

function drawLockIcon(ctx: CanvasRenderingContext2D, x: number, y: number): void {
  const p = 2;
  ctx.fillStyle = LOCK_COLOR;
  ctx.fillRect(x - p * 2, y - p * 3, p, p * 2);
  ctx.fillRect(x + p, y - p * 3, p, p * 2);
  ctx.fillRect(x - p * 2, y - p * 3, p * 4, p);
  ctx.fillRect(x - p * 2, y - p, p * 5, p * 3);
}

// ---------------------------------------------------------------------------
// Speech bubble
// ---------------------------------------------------------------------------

function drawSpeechBubble(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  text: string,
): void {
  ctx.save();
  ctx.font = "9px monospace";
  ctx.imageSmoothingEnabled = false;
  const metrics = ctx.measureText(text);
  const tw = metrics.width;
  const bw = tw + SPEECH_PADDING * 2;
  const bh = 16;
  const bx = Math.floor(x - bw / 2);
  const by = Math.floor(y - bh - SPEECH_TAIL - 2);

  ctx.fillStyle = "#2a2a4a";
  ctx.fillRect(bx, by, bw, bh);

  ctx.strokeStyle = "#7a7a9a";
  ctx.lineWidth = 1;
  ctx.strokeRect(bx + 0.5, by + 0.5, bw - 1, bh - 1);

  ctx.fillStyle = "#2a2a4a";
  ctx.fillRect(x - 2, by + bh, 4, 2);
  ctx.fillRect(x - 1, by + bh + 2, 2, 2);

  ctx.fillStyle = TEXT_COLOR;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, x, by + bh / 2);
  ctx.restore();
}

// ---------------------------------------------------------------------------
// Progress bar
// ---------------------------------------------------------------------------

function drawProgressBar(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  progress: number,
  color: string,
): void {
  const retroColor = snapToRetro(color);
  const barH = 4;

  ctx.fillStyle = "#0f0f1f";
  ctx.fillRect(x, y, w, barH);

  ctx.strokeStyle = "#3a3a5a";
  ctx.lineWidth = 1;
  ctx.strokeRect(x + 0.5, y + 0.5, w - 1, barH - 1);

  const fillW = Math.max(2, Math.floor(w * Math.min(1, Math.max(0, progress))));
  const segmentW = 4;
  for (let sx = 0; sx < fillW; sx += segmentW) {
    const sw = Math.min(segmentW - 1, fillW - sx);
    ctx.fillStyle = retroColor;
    ctx.fillRect(x + sx, y, sw, barH);
  }
}

// ---------------------------------------------------------------------------
// Log strip — 2 lines of amber phosphor mono showing last messages.
// ---------------------------------------------------------------------------

const LOG_LINE_COLORS_PIXEL: Record<string, string> = {
  start:    "#7dd3fc",
  progress: "#a0b0cc",
  complete: "#34d399",
  error:    "#f87171",
  note:     "#e3b341", // amber phosphor
};

function truncatePixel(
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

function drawPixelLogStrip(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  history: FloorAgent["logHistory"],
  nowMs: number,
): void {
  if (!history || history.length === 0) return;

  ctx.save();
  ctx.imageSmoothingEnabled = false;

  // Dark strip background with pixel border
  ctx.fillStyle = "rgba(5,8,15,0.85)";
  ctx.fillRect(x, y, w, 18);
  ctx.strokeStyle = "rgba(227,179,65,0.18)";
  ctx.lineWidth = 1;
  ctx.strokeRect(x + 0.5, y + 0.5, w - 1, 17);

  ctx.font = "7px monospace";
  ctx.textAlign = "left";
  ctx.textBaseline = "top";

  const visible = history.slice(0, 2);
  const padX = 3;
  const textW = w - padX * 2;

  for (let i = 0; i < visible.length; i++) {
    const entry = visible[i];
    const yi = y + 2 + i * 8;
    const age = i;
    const fade = age === 0 ? 1 : 0.6;

    // Typewriter on newest
    let shown = entry.text;
    if (i === 0) {
      const elapsed = nowMs - entry.ts;
      const reveal = Math.floor(elapsed * 0.06);
      shown = entry.text.slice(0, Math.max(1, reveal));
    }

    const truncated = truncatePixel(ctx, shown, textW);
    const baseColor = LOG_LINE_COLORS_PIXEL[entry.kind] || "#e3b341";
    ctx.fillStyle = fade < 1 ? rgba(baseColor, fade) : baseColor;
    ctx.fillText(truncated, x + padX, yi);

    // Blinking block cursor on newest while typing
    if (i === 0 && shown.length < entry.text.length) {
      const cursorX = x + padX + ctx.measureText(truncated.replace(/…$/, "")).width + 1;
      if (Math.floor(nowMs / 200) % 2 === 0) {
        ctx.fillRect(cursorX, yi, 3, 6);
      }
    }
  }

  ctx.restore();
}

// ---------------------------------------------------------------------------
// Pixel sparkle effect (busy animation)
// ---------------------------------------------------------------------------

function drawPixelSparkles(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  color: string,
  frame: number,
): void {
  const retroColor = snapToRetro(color);
  const sparkleCount = 4;
  ctx.fillStyle = retroColor;

  for (let i = 0; i < sparkleCount; i++) {
    const phase = (frame * 3 + i * 37) % 60;
    if (phase > 30) continue;
    const sx = x + ((frame * 7 + i * 23) % w);
    const sy = y + ((frame * 5 + i * 17) % h);
    const size = (phase < 15) ? 2 : 1;
    ctx.fillRect(Math.floor(sx), Math.floor(sy), size, size);
  }
}

// ---------------------------------------------------------------------------
// Individual station
// ---------------------------------------------------------------------------

function drawStation(
  ctx: CanvasRenderingContext2D,
  station: StationConfig,
  agent: FloorAgent,
  isSelected: boolean,
  frame: number,
  lang: string,
  hasSprites: boolean,
): void {
  const { x, y, width: w, height: h } = station;
  const color = station.theme.color;
  const isLocked = agent.locked;
  const isBusy = agent.state === "busy";
  const isError = agent.state === "error";
  const isComplete = agent.state === "complete";
  const showLockedActivity = isLocked && (isBusy || isComplete || isError || !!agent.speechBubble);
  const allowRuntimeVisualization = !isLocked || showLockedActivity;

  ctx.save();
  ctx.imageSmoothingEnabled = false;

  if (isLocked) {
    ctx.globalAlpha = showLockedActivity ? 0.75 : 0.45;
  }

  // Station background — semi-transparent panel so furniture/floor shows through
  ctx.fillStyle = rgba("#1a1a2e", 0.35);
  ctx.fillRect(x, y, w, h);

  // Border
  ctx.strokeStyle = isSelected ? SELECTED_BORDER : "#2a2a4a";
  ctx.lineWidth = isSelected ? 2 : 1;
  ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);

  // Selected: dashed inner highlight
  if (isSelected) {
    ctx.strokeStyle = rgba(SELECTED_BORDER, 0.4);
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 2]);
    ctx.strokeRect(x + 3.5, y + 3.5, w - 7, h - 7);
    ctx.setLineDash([]);
  }

  // Error: flashing red border
  if (isError && !isLocked) {
    const flash = Math.floor(frame / 15) % 2 === 0;
    if (flash) {
      ctx.strokeStyle = "#ff004d";
      ctx.lineWidth = 2;
      ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
    }
  }

  // Furniture sprites (or fallback desk)
  if (!isLocked) {
    if (hasSprites) {
      drawStationFurniture(ctx, station);
    } else {
      drawFallbackDesk(ctx, x, y, w, h, color);
    }
  }

  // Agent character
  const avatarX = x + 20;
  const avatarY = y + 36;

  if (isLocked) {
    ctx.fillStyle = "#1a1f2e";
    ctx.fillRect(avatarX - 8, avatarY - 8, 16, 16);
    drawLockIcon(ctx, avatarX, avatarY);
  } else if (hasSprites) {
    // Sleeping pets feel softer and sit slightly lower.
    const isIdle = agent.state === "idle";
    ctx.save();
    if (isIdle) ctx.globalAlpha = 0.92;
    drawAgentCharacter(ctx, station, agent, frame);
    ctx.restore();
    // Species accent + shadow + state reactions + sleeping zzz.
    drawPixelPet(ctx, station, agent, frame, isSelected);
  } else {
    drawFallbackAvatar(ctx, avatarX, avatarY, color, station.theme.icon, agent.state, frame);
    drawPixelPet(ctx, station, agent, frame, isSelected);
  }

  // Status dot (top-right of avatar area)
  if (allowRuntimeVisualization) {
    drawStatusDot(ctx, x + 38, y + 20, agent.state, frame);
  }

  // Busy: sparkle effects + progress bar
  if (isBusy && allowRuntimeVisualization) {
    drawPixelSparkles(ctx, x + 8, y + 8, w - 16, h - 16, color, frame);
  }

  // Log strip inside station bottom (even when idle — shows history)
  if (allowRuntimeVisualization) {
    drawPixelLogStrip(ctx, x + 4, y + h - 22, w - 8, agent.logHistory || [], performance.now());
  }

  // Progress bar sits at the very bottom (above label), only when busy
  if (isBusy && allowRuntimeVisualization) {
    drawProgressBar(ctx, x + 10, y + h - 3, w - 20, agent.progress, color);
  }

  // Name label below station
  const label = getStationDisplayName(station, lang);
  ctx.fillStyle = "#000000";
  ctx.font = "9px monospace";
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  ctx.fillText(label, x + w / 2 + 1, y + h + 4);
  ctx.fillStyle = isLocked ? LOCK_COLOR : TEXT_COLOR;
  ctx.fillText(label, x + w / 2, y + h + 3);

  ctx.restore();

  // Speech bubble (outside locked opacity)
  if (agent.speechBubble && allowRuntimeVisualization) {
    drawSpeechBubble(ctx, x + w / 2, y, agent.speechBubble);
  }
}

// ---------------------------------------------------------------------------
// Fallback primitives (when sprites not loaded)
// ---------------------------------------------------------------------------

function drawFallbackDesk(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  color: string,
): void {
  const retroColor = snapToRetro(color);
  const deskH = 8;
  const deskY = y + h - deskH - 14;
  const deskX = x + 44;
  const deskW = w - 54;

  ctx.fillStyle = rgba(retroColor, 0.3);
  ctx.fillRect(deskX, deskY, deskW, deskH);

  ctx.fillStyle = rgba(retroColor, 0.2);
  ctx.fillRect(deskX + 2, deskY + deskH, 2, 6);
  ctx.fillRect(deskX + deskW - 4, deskY + deskH, 2, 6);

  ctx.fillStyle = rgba(retroColor, 0.4);
  ctx.fillRect(deskX + Math.floor(deskW / 2) - 8, deskY - 10, 16, 10);
  ctx.fillStyle = "#0a0a1a";
  ctx.fillRect(deskX + Math.floor(deskW / 2) - 6, deskY - 8, 12, 6);
}

function drawFallbackAvatar(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  color: string,
  icon: string,
  state: FloorAgent["state"],
  frame: number,
): void {
  const retroColor = snapToRetro(color);
  const size = 12;
  const half = size / 2;
  const px = Math.floor(cx - half);
  const bobOffset = state === "idle" ? (Math.floor(frame / 20) % 2 === 0 ? 0 : -1) : 0;
  const py = Math.floor(cy - half) + bobOffset;
  const p = 2;

  ctx.save();
  ctx.imageSmoothingEnabled = false;

  ctx.fillStyle = rgba("#000000", 0.3);
  ctx.fillRect(px + p, py + size, size - p * 2, p);

  ctx.fillStyle = retroColor;
  ctx.fillRect(px + p, py + p * 2, p * 4, p * 3);

  ctx.fillStyle = rgba(retroColor, 0.9);
  ctx.fillRect(px + p, py, p * 4, p * 2);

  ctx.fillStyle = "#ffffff";
  ctx.fillRect(px + p, py + p, p, p);
  ctx.fillRect(px + p * 3, py + p, p, p);

  ctx.fillStyle = rgba(retroColor, 0.7);
  ctx.fillRect(px + p, py + p * 5, p, p);
  ctx.fillRect(px + p * 3, py + p * 5, p, p);

  ctx.fillStyle = "#ffffff";
  ctx.font = "bold 7px monospace";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(icon, cx, cy + p);

  ctx.restore();
}

function drawFallbackBackground(ctx: CanvasRenderingContext2D, w: number, h: number): void {
  ctx.fillStyle = "#1a1a2e";
  ctx.fillRect(0, 0, w, h);

  for (let ty = 0; ty < h; ty += TILE_SIZE) {
    for (let tx = 0; tx < w; tx += TILE_SIZE) {
      const checker = ((tx / TILE_SIZE) + (ty / TILE_SIZE)) % 2 === 0;
      ctx.fillStyle = checker ? "#16213e" : "#0f3460";
      ctx.fillRect(tx, ty, TILE_SIZE, TILE_SIZE);
    }
  }

  ctx.strokeStyle = rgba("#ffffff", 0.04);
  ctx.lineWidth = 1;
  for (let x = 0; x < w; x += TILE_SIZE) {
    ctx.beginPath();
    ctx.moveTo(x + 0.5, 0);
    ctx.lineTo(x + 0.5, h);
    ctx.stroke();
  }
  for (let y = 0; y < h; y += TILE_SIZE) {
    ctx.beginPath();
    ctx.moveTo(0, y + 0.5);
    ctx.lineTo(w, y + 0.5);
    ctx.stroke();
  }
}

// ---------------------------------------------------------------------------
// Scanline overlay (retro CRT feel)
// ---------------------------------------------------------------------------

function drawScanlines(ctx: CanvasRenderingContext2D, w: number, h: number): void {
  ctx.fillStyle = rgba("#000000", 0.03);
  for (let y = 0; y < h; y += 2) {
    ctx.fillRect(0, y, w, 1);
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export function renderPixelFloor(
  ctx: CanvasRenderingContext2D,
  agents: ReadonlyArray<FloorAgent>,
  selectedAgent: string | null,
  frame: number,
  lang: string,
): void {
  const w = ctx.canvas.width;
  const h = ctx.canvas.height;
  const hasSprites = spritesReady();

  ctx.imageSmoothingEnabled = false;

  // Layer 1: Floor tiles
  if (hasSprites) {
    drawBackground(ctx, w, h);
  } else {
    drawFallbackBackground(ctx, w, h);
  }

  // Layer 2: Wall borders around zones
  if (hasSprites) {
    drawZoneWalls(ctx);
  }

  // Layer 3: Zone labels
  drawZoneLabels(ctx, lang);

  // Layer 4: Stations (furniture, characters, UI overlays)
  for (const agent of agents) {
    const station = getStationByName(agent.name);
    if (!station) continue;

    const isSelected = agent.name === selectedAgent;
    drawStation(ctx, station, agent, isSelected, frame, lang, hasSprites);
  }

  // Layer 5: Crab mascot near Scheduler
  if (hasSprites) {
    drawCrabMascot(ctx, frame);
  }

  // Layer 6: CRT scanline overlay
  drawScanlines(ctx, w, h);
}
