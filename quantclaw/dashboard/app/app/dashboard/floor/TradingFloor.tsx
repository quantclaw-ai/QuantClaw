"use client";
import { useRef, useEffect, useCallback } from "react";
import type { FloorAgent, VisualMode } from "./types";
import { renderModernFloor, hitTestStation } from "./renderers/modern";
import { renderPixelFloor } from "./renderers/pixel";
import { initFloorSprites } from "./sprites";
import { useLang } from "../../lang-context";

interface TradingFloorProps {
  agents: FloorAgent[];
  mode: VisualMode;
  onAgentClick: (agentName: string) => void;
  selectedAgent: string | null;
}

export function TradingFloor({ agents, mode, onAgentClick, selectedAgent }: TradingFloorProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frameRef = useRef(0);
  const animRef = useRef<number>(0);
  const { lang } = useLang();

  // Initialize sprites on mount
  useEffect(() => {
    initFloorSprites();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Handle DPI scaling
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);

    const render = () => {
      frameRef.current += 1;
      ctx.save();
      ctx.clearRect(0, 0, rect.width, rect.height);

      // Scale to fit canvas
      const scaleX = rect.width / 920;
      const scaleY = rect.height / 640;
      const scale = Math.min(scaleX, scaleY);
      const offsetX = (rect.width - 920 * scale) / 2;
      const offsetY = (rect.height - 640 * scale) / 2;
      ctx.translate(offsetX, offsetY);
      ctx.scale(scale, scale);

      // Render based on mode (modern is default)
      if (mode === "pixel") {
        renderPixelFloor(ctx, agents, selectedAgent, frameRef.current, lang);
      } else {
        renderModernFloor(ctx, agents, selectedAgent, frameRef.current, lang);
      }

      ctx.restore();
      animRef.current = requestAnimationFrame(render);
    };

    render();
    return () => cancelAnimationFrame(animRef.current);
  }, [agents, mode, selectedAgent, lang]);

  // Handle resize
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const observer = new ResizeObserver(() => {
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
    });
    observer.observe(canvas);
    return () => observer.disconnect();
  }, []);

  const handleClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const rawX = e.clientX - rect.left;
    const rawY = e.clientY - rect.top;

    // Reverse the scaling transform
    const scaleX = rect.width / 920;
    const scaleY = rect.height / 640;
    const scale = Math.min(scaleX, scaleY);
    const offsetX = (rect.width - 920 * scale) / 2;
    const offsetY = (rect.height - 640 * scale) / 2;
    const x = (rawX - offsetX) / scale;
    const y = (rawY - offsetY) / scale;

    const agentName = hitTestStation(x, y, agents);
    if (agentName) {
      onAgentClick(agentName);
    }
  }, [agents, onAgentClick]);

  return (
    <canvas
      ref={canvasRef}
      onClick={handleClick}
      className="w-full h-full cursor-pointer"
      style={{ imageRendering: mode === "pixel" ? "pixelated" : "auto" }}
    />
  );
}
