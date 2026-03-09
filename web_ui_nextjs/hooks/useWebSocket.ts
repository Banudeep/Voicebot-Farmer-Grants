"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { KEEPALIVE_INTERVAL_MS } from "@/lib/constants";

export type ConnectionStatus =
  | "connecting"
  | "connected"
  | "disconnected"
  | "error";

export interface WsMessage {
  type: string;
  [key: string]: unknown;
}

interface UseWebSocketReturn {
  send: (msg: WsMessage) => void;
  status: ConnectionStatus;
  sessionId: string | null;
  /** Ref holding queued messages — drain in your effect and call .splice(0) to clear. */
  messageQueueRef: React.MutableRefObject<WsMessage[]>;
  /** Incremented on every incoming message; use as an effect dependency to trigger processing. */
  messageVersion: number;
}

export function useWebSocket(): UseWebSocketReturn {
  const wsRef = useRef<WebSocket | null>(null);
  const keepAliveRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const messageQueueRef = useRef<WsMessage[]>([]);
  const [messageVersion, setMessageVersion] = useState(0);

  const startKeepAlive = useCallback(() => {
    if (keepAliveRef.current) clearInterval(keepAliveRef.current);
    keepAliveRef.current = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "ping" }));
      }
    }, KEEPALIVE_INTERVAL_MS);
  }, []);

  const stopKeepAlive = useCallback(() => {
    if (keepAliveRef.current) {
      clearInterval(keepAliveRef.current);
      keepAliveRef.current = null;
    }
  }, []);

  const connect = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
      wsRef.current.close();
    }

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const hostname = window.location.hostname;
    let wsUrl: string;

    if (hostname === "localhost" || hostname === "127.0.0.1") {
      wsUrl = `${protocol}//${hostname}:8080/ws`;
    } else {
      const currentPort = window.location.port
        ? `:${window.location.port}`
        : "";
      wsUrl = `${protocol}//${hostname}${currentPort}/ws`;
    }

    console.log(`Connecting to WebSocket: ${wsUrl}`);
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    setStatus("connecting");

    ws.onopen = () => {
      console.log("✓ Connected to server");
      setStatus("connected");
      startKeepAlive();
    };

    ws.onmessage = (event) => {
      const data: WsMessage = JSON.parse(event.data);
      if (data.type === "session_id") {
        setSessionId(data.session_id as string);
      }
      // Push to queue instead of overwriting a single state value.
      // This prevents React 18 batching from dropping rapid messages
      // (e.g. back-to-back audio_chunk messages).
      messageQueueRef.current.push(data);
      setMessageVersion((v) => v + 1);
    };

    ws.onerror = () => {
      console.error("WebSocket error");
      setStatus("error");
    };

    ws.onclose = () => {
      console.log("Disconnected");
      stopKeepAlive();
      setStatus("disconnected");
      setSessionId(null);
      setTimeout(() => {
        if (!wsRef.current || wsRef.current.readyState === WebSocket.CLOSED) {
          connect();
        }
      }, 2000);
    };
  }, [startKeepAlive, stopKeepAlive]);

  const send = useCallback((msg: WsMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  useEffect(() => {
    connect();
    return () => {
      stopKeepAlive();
      if (wsRef.current) {
        wsRef.current.onclose = null; // prevent reconnect on unmount
        wsRef.current.close();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { send, status, sessionId, messageQueueRef, messageVersion };
}
