import { useState, useRef, useEffect, useCallback } from "react";
import { useWebSocket } from "./useWebSocket";
import { useAudioRecorder } from "./useAudioRecorder";
import { useAudioPlayer } from "./useAudioPlayer";
import {
  type InteractionMode,
  type ChatMessage,
  decodeBase64ToUint8,
  STREAM_RENDER_INTERVAL_MS,
} from "@/lib/constants";
import { showToast } from "@/components/Toast";

let messageIdCounter = 0;
function nextId() {
  return `msg-${++messageIdCounter}`;
}

export function useAppSession() {
  const { send, status, sessionId, lastMessage } = useWebSocket();

  const sessionStartedRef = useRef(false);
  const playbackSpeedRef = useRef(0.9);
  const currentModeRef = useRef<InteractionMode>("voice");

  const { isRecording, startRecording, stopRecording } = useAudioRecorder(
    send,
    sessionStartedRef,
  );
  const { enqueueChunk, stopPlayback, playChunks } = useAudioPlayer(
    send,
    playbackSpeedRef,
  );

  const [mode, setMode] = useState<InteractionMode>("text");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isTyping, setIsTyping] = useState(false);
  const [partialTranscript, setPartialTranscript] = useState<string | null>(
    null,
  );
  const [streamingText, setStreamingText] = useState<string | null>(null);
  const [playingMessageId, setPlayingMessageId] = useState<string | null>(null);

  // Form preview panel state
  const [formPanelOpen, setFormPanelOpen] = useState(false);
  const [currentFormName, setCurrentFormName] = useState<string | null>(null);
  const [formPdfVersion, setFormPdfVersion] = useState(0);
  const [formProgress, setFormProgress] = useState<{
    filled: number;
    total: number;
  } | null>(null);

  const pdfRefreshDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );

  // Settings state
  const [currentVoice, setCurrentVoice] = useState(() =>
    typeof window !== "undefined"
      ? localStorage.getItem("voiceName") || "en-US-JennyNeural"
      : "en-US-JennyNeural",
  );
  const [currentSpeed, setCurrentSpeed] = useState(() => {
    if (typeof window === "undefined") return 0.9;
    const saved = localStorage.getItem("playbackSpeed");
    return saved ? parseFloat(saved) : 0.9;
  });

  // Audio chunks buffer for current response
  const currentResponseChunksRef = useRef<Uint8Array[]>([]);
  const streamingRenderTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null,
  );
  const pendingStreamingTextRef = useRef("");

  // Keep mode ref in sync
  useEffect(() => {
    currentModeRef.current = mode;
  }, [mode]);

  // Load saved mode
  useEffect(() => {
    const saved = localStorage.getItem(
      "preferredMode",
    ) as InteractionMode | null;
    if (saved === "text" || saved === "voice") {
      setMode(saved);
    }
  }, []);

  // Send initial settings on connect
  useEffect(() => {
    if (status === "connected") {
      send({
        type: "update_settings",
        settings: { voice: currentVoice },
      });
    }
  }, [status, currentVoice, send]);

  // Process WebSocket messages
  useEffect(() => {
    if (!lastMessage) return;
    const data = lastMessage;

    switch (data.type) {
      case "transcript_partial": {
        if (!data.is_duplicate) {
          stopPlayback();
          setPartialTranscript(data.text as string);
        }
        break;
      }
      case "transcript": {
        setPartialTranscript(null);
        const msg: ChatMessage = {
          id: nextId(),
          role: "user",
          text: data.text as string,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, msg]);
        currentResponseChunksRef.current = [];
        break;
      }
      case "thinking": {
        setIsTyping(true);
        break;
      }
      case "response_text": {
        setIsTyping(false);
        if (data.is_streaming) {
          // Throttled streaming update
          pendingStreamingTextRef.current = data.text as string;
          if (!streamingRenderTimerRef.current) {
            streamingRenderTimerRef.current = setTimeout(() => {
              setStreamingText(pendingStreamingTextRef.current);
              streamingRenderTimerRef.current = null;
            }, STREAM_RENDER_INTERVAL_MS);
          }
        } else {
          // Final message
          if (streamingRenderTimerRef.current) {
            clearTimeout(streamingRenderTimerRef.current);
            streamingRenderTimerRef.current = null;
          }
          setStreamingText(null);
          const msg: ChatMessage = {
            id: nextId(),
            role: "assistant",
            text: data.text as string,
            timestamp: new Date(),
          };
          setMessages((prev) => [...prev, msg]);
        }
        break;
      }
      case "audio_chunk": {
        const bytes = decodeBase64ToUint8(data.audio as string);
        currentResponseChunksRef.current.push(bytes);
        if (currentModeRef.current === "voice") {
          enqueueChunk(bytes);
        }
        break;
      }
      case "audio_complete": {
        // Attach audio chunks to last assistant message
        if (currentResponseChunksRef.current.length > 0) {
          const chunks = [...currentResponseChunksRef.current];
          setMessages((prev) => {
            const updated = [...prev];
            for (let i = updated.length - 1; i >= 0; i--) {
              if (updated[i].role === "assistant") {
                updated[i] = { ...updated[i], audioChunks: chunks };
                break;
              }
            }
            return updated;
          });
        }
        break;
      }
      case "error": {
        setIsTyping(false);
        setStreamingText(null);
        const msg: ChatMessage = {
          id: nextId(),
          role: "system",
          text: "Error: " + (data.message as string),
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, msg]);
        showToast(data.message as string, "error");
        break;
      }
      case "form_panel": {
        if (data.action === "open") {
          setCurrentFormName(data.form_name as string);
          setFormPanelOpen(true);
          setFormPdfVersion((v) => v + 1);
          if (data.progress) {
            setFormProgress(data.progress as { filled: number; total: number });
          }
        } else if (data.action === "close") {
          setFormPanelOpen(false);
          setCurrentFormName(null);
          setFormProgress(null);
        }
        break;
      }
      case "form_update": {
        const updatedFormName = data.form_name as string;
        if (updatedFormName && updatedFormName !== currentFormName) {
          setCurrentFormName(updatedFormName);
        }
        if (!formPanelOpen) {
          setFormPanelOpen(true);
        }
        if (data.progress) {
          setFormProgress(data.progress as { filled: number; total: number });
        }
        // Debounce PDF refresh
        if (pdfRefreshDebounceRef.current) {
          clearTimeout(pdfRefreshDebounceRef.current);
        }
        pdfRefreshDebounceRef.current = setTimeout(() => {
          setFormPdfVersion((v) => v + 1);
        }, 500);
        break;
      }
    }
  }, [
    lastMessage,
    currentFormName,
    formPanelOpen,
    enqueueChunk,
    stopPlayback,
  ]);

  // Mode switching
  const handleSwitchMode = useCallback(
    (newMode: InteractionMode) => {
      if (newMode === mode) return;
      if (mode === "voice" && isRecording) {
        stopRecording();
      }
      stopPlayback();
      setMode(newMode);
      localStorage.setItem("preferredMode", newMode);
    },
    [mode, isRecording, stopRecording, stopPlayback],
  );

  // Send text
  const handleSendText = useCallback(
    (text: string) => {
      if (status !== "connected") {
        showToast("Not connected to server", "error");
        return;
      }
      const msg: ChatMessage = {
        id: nextId(),
        role: "user",
        text,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, msg]);
      send({ type: "text_message", text });
      currentResponseChunksRef.current = [];
    },
    [status, send],
  );

  // handleQuickAction is just an alias for handleSendText (no extra logic needed)
  const handleQuickAction = handleSendText;

  // Listen for quick suggestion clicks from empty state
  useEffect(() => {
    const handler = (e: Event) => {
      const text = (e as CustomEvent).detail as string;
      if (text) handleQuickAction(text);
    };
    window.addEventListener("quickSuggestion", handler);
    return () => window.removeEventListener("quickSuggestion", handler);
  }, [handleQuickAction]);

  // Email summary
  const handleEmailSummary = useCallback(() => {
    if (messages.length === 0) {
      showToast("Start a conversation first to get a summary", "error");
      return;
    }
    handleSendText("Please email me a summary of this conversation.");
  }, [messages.length, handleSendText]);

  // Listen to message audio
  const handleListen = useCallback(
    (msg: ChatMessage) => {
      if (playingMessageId === msg.id) {
        stopPlayback();
        setPlayingMessageId(null);
        return;
      }
      if (msg.audioChunks && msg.audioChunks.length > 0) {
        stopPlayback();
        playChunks(msg.audioChunks);
        setPlayingMessageId(msg.id);
      }
    },
    [playingMessageId, stopPlayback, playChunks],
  );

  // Save settings
  const handleSaveSettings = useCallback(
    (voice: string, speed: number) => {
      setCurrentVoice(voice);
      setCurrentSpeed(speed);
      playbackSpeedRef.current = speed;
      localStorage.setItem("voiceName", voice);
      localStorage.setItem("playbackSpeed", speed.toString());
      send({ type: "update_settings", settings: { voice } });
      // Clear cached audio from messages (force re-synthesis with new voice)
      setMessages((prev) =>
        prev.map((m) => ({ ...m, audioChunks: undefined })),
      );
      showToast("Settings saved", "success");
    },
    [send],
  );

  // Toggle form panel visibility (hide/show)
  const handleToggleFormPanel = useCallback(() => {
    setFormPanelOpen((prev) => !prev);
  }, []);

  // Close form panel (just hides, keeps form name for re-open)
  const handleCloseFormPanel = useCallback(() => {
    setFormPanelOpen(false);
  }, []);

  return {
    status,
    sessionId,
    mode,
    handleSwitchMode,
    currentVoice,
    currentSpeed,
    handleSaveSettings,
    messages,
    isTyping,
    partialTranscript,
    streamingText,
    handleListen,
    playingMessageId,
    currentFormName,
    formPanelOpen,
    formPdfVersion,
    formProgress,
    handleToggleFormPanel,
    handleCloseFormPanel,
    isRecording,
    startRecording,
    stopRecording,
    handleSendText,
    handleQuickAction,
    handleEmailSummary,
  };
}
