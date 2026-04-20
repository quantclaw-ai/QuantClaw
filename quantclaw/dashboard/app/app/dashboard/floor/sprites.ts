/**
 * Sprite loader and manager for the Trading Floor.
 * Loads sprite sheet PNGs and provides frame extraction.
 */

export interface SpriteSheet {
  image: HTMLImageElement;
  loaded: boolean;
  frameWidth: number;
  frameHeight: number;
  cols: number;
  rows: number;
}

const spriteCache: Record<string, SpriteSheet> = {};

export function loadSprite(
  key: string,
  src: string,
  frameWidth: number,
  frameHeight: number,
): SpriteSheet {
  if (spriteCache[key]?.loaded) return spriteCache[key];

  if (!spriteCache[key]) {
    const image = new Image();
    image.src = src;
    const sheet: SpriteSheet = {
      image,
      loaded: false,
      frameWidth,
      frameHeight,
      cols: 0,
      rows: 0,
    };
    image.onload = () => {
      sheet.loaded = true;
      sheet.cols = Math.floor(image.width / frameWidth);
      sheet.rows = Math.floor(image.height / frameHeight);
    };
    spriteCache[key] = sheet;
  }

  return spriteCache[key];
}

export function drawSprite(
  ctx: CanvasRenderingContext2D,
  sheet: SpriteSheet,
  frameIndex: number,
  x: number,
  y: number,
  scale: number = 1,
  flipX: boolean = false,
) {
  if (!sheet.loaded || sheet.cols === 0) return;

  const col = frameIndex % sheet.cols;
  const row = Math.floor(frameIndex / sheet.cols);
  const sx = col * sheet.frameWidth;
  const sy = row * sheet.frameHeight;
  const dw = sheet.frameWidth * scale;
  const dh = sheet.frameHeight * scale;

  ctx.save();
  if (flipX) {
    ctx.translate(x + dw, y);
    ctx.scale(-1, 1);
    ctx.drawImage(sheet.image, sx, sy, sheet.frameWidth, sheet.frameHeight, 0, 0, dw, dh);
  } else {
    ctx.drawImage(sheet.image, sx, sy, sheet.frameWidth, sheet.frameHeight, x, y, dw, dh);
  }
  ctx.restore();
}

/**
 * Draw a tile from a tileset at a grid position.
 */
export function drawTile(
  ctx: CanvasRenderingContext2D,
  sheet: SpriteSheet,
  tileIndex: number,
  x: number,
  y: number,
  scale: number = 1,
) {
  drawSprite(ctx, sheet, tileIndex, x, y, scale);
}

// Pre-load all trading floor sprites
let _spritesInitialized = false;

export function initFloorSprites() {
  if (_spritesInitialized) return;
  _spritesInitialized = true;

  // Interior tiles (16x16 each in a 256x256 sheet = 16 cols x 16 rows)
  loadSprite("tiles", "/sprites/tiles_interior.png", 16, 16);

  // Office tiles (32x32 each in 256x256 = 8x8)
  loadSprite("office", "/sprites/tiles_office.png", 32, 32);

  // Characters (expanded, 16x16 frames in 800x800 sheet)
  loadSprite("chars", "/sprites/characters.png", 16, 16);

  // Male characters (16x16 in 96x160 = 6 cols x 10 rows)
  loadSprite("chars_male", "/sprites/characters_male.png", 16, 16);

  // Crab walk (4 frames of 64x64 in 256x128 = 4 cols x 2 rows)
  loadSprite("crab_walk", "/sprites/crab_walk.png", 64, 64);

  // Crab idle frames
  loadSprite("crab_idle1", "/sprites/crab_idle1.png", 64, 64);
  loadSprite("crab_idle2", "/sprites/crab_idle2.png", 64, 64);
}

export function getSprite(key: string): SpriteSheet | undefined {
  return spriteCache[key];
}

/**
 * Check if all sprites are loaded.
 */
export function allSpritesLoaded(): boolean {
  return Object.values(spriteCache).every((s) => s.loaded);
}
