export type AgentState = "idle" | "busy" | "complete" | "error";
export type VisualMode = "pixel" | "modern";

export type LogKind = "start" | "progress" | "complete" | "error" | "note";

export interface AgentLogEntry {
  text: string;
  kind: LogKind;
  ts: number;  // Date.now() when captured
}

export interface FloorAgent {
  name: string;
  displayName: string;
  enabled: boolean;
  locked: boolean;
  state: AgentState;
  progress: number;
  speechBubble: string | null;
  speechBubbleTimeout?: ReturnType<typeof setTimeout>;
  logHistory: AgentLogEntry[];  // newest-first, capped (see MAX_LOG per agent)
  zone: string;
  x: number;
  y: number;
}

export interface FloorEvent {
  type: string;
  agent?: string;
  source_agent?: string;
  targets?: string[];
  payload?: Record<string, unknown>;
  progress?: number;
  message?: string;
  timestamp?: string;
}
