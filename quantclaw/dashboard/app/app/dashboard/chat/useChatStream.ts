"use client";
import { useEffect, useRef } from "react";

const WS_URL = "ws://localhost:24120/ws/events";

export interface ChatNarrative {
  message: string;
  role: string;
  timestamp?: string;
}

/**
 * Hook that subscribes to WebSocket for chat.narrative events.
 * Appends narrative messages to the chat panel in real-time.
 *
 * Usage:
 *   useChatStream(
 *     (narrative) => appendMessage(narrative),
 *     () => setIsOrchestrating(false)
 *   );
 */
export function useChatStream(
  onNarrative: (narrative: ChatNarrative) => void,
  onCycleComplete: () => void,
) {
  const onNarrativeRef = useRef(onNarrative);
  const onCycleCompleteRef = useRef(onCycleComplete);

  useEffect(() => {
    onNarrativeRef.current = onNarrative;
    onCycleCompleteRef.current = onCycleComplete;
  }, [onNarrative, onCycleComplete]);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimeout: ReturnType<typeof setTimeout>;

    function connect() {
      try {
        ws = new WebSocket(WS_URL);

        ws.onmessage = (e) => {
          try {
            const event = JSON.parse(e.data);

            if (event.type === "chat.narrative") {
              onNarrativeRef.current({
                message: event.payload?.message || "",
                role: event.payload?.role || "scheduler",
                timestamp: event.timestamp,
              });
            }

            if (event.type === "orchestration.cycle_complete") {
              onCycleCompleteRef.current();
            }
          } catch {}
        };

        ws.onclose = () => {
          ws = null;
          reconnectTimeout = setTimeout(connect, 2000);
        };
      } catch {
        reconnectTimeout = setTimeout(connect, 2000);
      }
    }

    connect();

    return () => {
      clearTimeout(reconnectTimeout);
      if (ws) {
        ws.close();
      }
    };
  }, []);
}
