"use client";

import { marked } from "marked";
import { Copy, Volume2, Pause, Bot, User } from "lucide-react";
import { type ChatMessage } from "@/lib/constants";
import { showToast } from "./Toast";

interface MessageProps {
  message: ChatMessage;
  onListen?: (msg: ChatMessage) => void;
  isListenPlaying?: boolean;
}

const SVG_ASSISTANT = <Bot size={20} />;
const SVG_USER = <User size={20} />;

export default function Message({
  message,
  onListen,
  isListenPlaying,
}: MessageProps) {
  const isUser = message.role === "user";
  const isAssistant = message.role === "assistant";

  const handleCopy = () => {
    navigator.clipboard.writeText(message.text);
    showToast("Copied to clipboard", "success");
  };

  const htmlContent = marked.parse(message.text, { async: false });

  if (message.role === "system") {
    return (
      <div className="flex items-center">
        <div
          className="message-content rounded-xl px-4 py-3 text-[0.9rem]"
          style={{ background: "#fed7d7", color: "#c53030" }}
        >
          {message.text}
        </div>
      </div>
    );
  }

  return (
    <div
      className={`flex gap-4 py-4 ${isUser ? "flex-row-reverse msg-animate-right" : "msg-animate-left"}`}
    >
      {/* Avatar */}
      <div
        className={`w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 shadow-sm ${
          isAssistant
            ? "bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] text-[var(--color-accent)]"
            : "bg-[var(--color-accent)] text-white"
        }`}
      >
        {isUser ? SVG_USER : SVG_ASSISTANT}
      </div>

      {/* Content Wrapper */}
      <div
        className={`flex flex-col ${isUser ? "max-w-[80%] items-end" : "flex-1 min-w-0 items-start"}`}
      >
        {/* Message Bubble */}
        <div
          className={`flex items-start gap-2 ${isAssistant ? "w-full" : ""}`}
        >
          <div
            className={`message-content text-[0.95rem] leading-[1.6] ${
              isUser
                ? "bg-[var(--color-accent)] text-white bubble-user shadow-md"
                : "w-full pt-1.5 pb-2 text-[var(--color-text-primary)] bubble-assistant"
            }`}
            style={
              isUser
                ? {
                    padding: "10px 18px",
                    borderRadius: "20px 20px 4px 20px",
                  }
                : undefined
            }
            dangerouslySetInnerHTML={{ __html: htmlContent }}
          />
        </div>

        {/* Actions (assistant only) */}
        {isAssistant && (
          <div className="flex items-center gap-2 mt-2">
            <button
              onClick={handleCopy}
              className="flex items-center gap-1.5 text-[0.8rem] font-medium text-[var(--color-text-tertiary)] hover:text-[var(--color-accent)] bg-[var(--color-bg-secondary)] hover:bg-[var(--color-accent-light)] border border-[var(--color-border)] hover:border-[var(--color-accent)] cursor-pointer py-1.5 px-3 rounded-full transition-all shadow-sm"
            >
              <Copy size={13} /> Copy
            </button>
            {message.audioChunks && message.audioChunks.length > 0 && (
              <button
                onClick={() => onListen?.(message)}
                className={`flex items-center gap-1.5 text-[0.8rem] font-medium border cursor-pointer py-1.5 px-3 rounded-full transition-all shadow-sm ${
                  isListenPlaying
                    ? "bg-[var(--color-accent)] text-white border-[var(--color-accent)]"
                    : "text-[var(--color-text-tertiary)] hover:text-[var(--color-accent)] bg-[var(--color-bg-secondary)] hover:bg-[var(--color-accent-light)] border-[var(--color-border)] hover:border-[var(--color-accent)]"
                }`}
              >
                {isListenPlaying ? <Pause size={13} /> : <Volume2 size={13} />}
                {isListenPlaying ? "Stop" : "Listen"}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
