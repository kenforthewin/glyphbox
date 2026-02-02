import { useState, useEffect, useRef } from "react";
import type { TurnRecord, RunRecord, WsMessage } from "../types/api";
import { ENDPOINTS } from "../api/endpoints";

export function useLiveStream(runId: string, enabled: boolean) {
  const [turns, setTurns] = useState<TurnRecord[]>([]);
  const [connected, setConnected] = useState(false);
  const [runEnded, setRunEnded] = useState<RunRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!enabled) return;

    const ws = new WebSocket(ENDPOINTS.wsLive(runId));
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setError("WebSocket connection failed");

    ws.onmessage = (event: MessageEvent) => {
      const msg: WsMessage = JSON.parse(event.data as string);
      switch (msg.type) {
        case "turn":
          setTurns((prev) => [...prev, msg.data]);
          break;
        case "run_ended":
          setRunEnded(msg.data);
          break;
        case "error":
          setError(msg.message);
          break;
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [runId, enabled]);

  return { turns, connected, runEnded, error };
}
