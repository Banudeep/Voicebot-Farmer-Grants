"use client";

import { useEffect, useRef, useState, useMemo } from "react";
import { ChevronDown, FileText } from "lucide-react";
import { marked } from "marked";
import type { ChatMessage as ChatMessageType } from "@/lib/constants";
import ChatMessageComponent from "./ChatMessage";
import { AssistantAvatar, UserAvatar } from "./icons";

interface ChatContainerProps {
  messages: ChatMessageType[];
  isTyping: boolean;
  partialTranscript: string | null;
  streamingText: string | null;
  onListen: (msg: ChatMessageType) => void;
  playingMessageId: string | null;
  formProgress?: { filled: number; total: number } | null;
  formName?: string | null;
}

function getTimeGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

export default function ChatContainer({
  messages,
  isTyping,
  partialTranscript,
  streamingText,
  onListen,
  playingMessageId,
  formProgress,
  formName,
}: ChatContainerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [showScrollBtn, setShowScrollBtn] = useState(false);
  const [newMsgCount, setNewMsgCount] = useState(0);
  const isAutoScrollPinned = useRef(true);
  const prevMsgCountRef = useRef(messages.length);

  const greeting = useMemo(() => getTimeGreeting(), []);

  const updateScrollControls = () => {
    const el = containerRef.current;
    if (!el) return;
    const isAtBottom = el.scrollHeight - el.scrollTop <= el.clientHeight + 50;
    isAutoScrollPinned.current = isAtBottom;
    if (isAtBottom) {
      setNewMsgCount(0);
    }
    setShowScrollBtn(!isAtBottom);
  };

  const scrollToBottom = (force = false) => {
    if (!force && !isAutoScrollPinned.current) return;
    const el = containerRef.current;
    if (el) {
      requestAnimationFrame(() => {
        el.scrollTop = el.scrollHeight;
        updateScrollControls();
      });
    }
  };

  // Track new messages when scrolled up
  useEffect(() => {
    const newCount = messages.length - prevMsgCountRef.current;
    if (newCount > 0 && !isAutoScrollPinned.current) {
      setNewMsgCount((c) => c + newCount);
    }
    prevMsgCountRef.current = messages.length;
  }, [messages.length]);

  useEffect(() => {
    scrollToBottom();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages, isTyping, partialTranscript, streamingText]);

  const isEmpty = messages.length === 0 && !partialTranscript && !streamingText;

  return (
    <div className="flex-1 flex flex-col min-h-0 relative items-center w-full px-6">
      <div
        ref={containerRef}
        onScroll={updateScrollControls}
        className="flex-1 overflow-y-auto bg-[var(--color-bg-secondary)] rounded-2xl border border-[var(--color-border)] relative w-full max-w-[1000px] z-[1]"
        style={{
          marginTop: 8,
          marginBottom: 16,
          boxShadow: "0 2px 12px rgba(0,0,0,0.04)",
          padding: "24px 40px",
        }}
      >
        {isEmpty && (
          <div className="flex flex-col items-center justify-center h-full text-center text-[var(--color-text-tertiary)]">
            <div className="mb-5 w-20 h-20 rounded-full bg-[var(--color-accent-light)] flex items-center justify-center welcome-icon-pop">
              <svg
                width="40"
                height="40"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                style={{ color: "var(--color-accent)" }}
              >
                <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"></path>
                <path d="M19 10v2a7 7 0 0 1-14 0v-2"></path>
                <line x1="12" x2="12" y1="19" y2="22"></line>
              </svg>
            </div>
            <div
              className="text-xl font-bold text-[var(--color-text-primary)] mb-1.5 welcome-fade-in"
              style={{ animationDelay: "0.15s" }}
            >
              {greeting}, Farmer!
            </div>
            <div
              className="text-sm text-[var(--color-text-secondary)] mb-6 max-w-[320px] leading-relaxed welcome-fade-in"
              style={{ animationDelay: "0.35s" }}
            >
              I can help with USDA grants, programs, eligibility, and local
              offices. Try asking something below!
            </div>
            <div
              className="flex flex-wrap gap-2 justify-center max-w-[420px] welcome-fade-in"
              style={{ animationDelay: "0.55s" }}
            >
              {[
                "What grants am I eligible for?",
                "Find my local USDA office",
                "Help me fill out a form",
              ].map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => {
                    // Bubble up via the ChatContainer's parent — we'll use a custom event
                    window.dispatchEvent(
                      new CustomEvent("quickSuggestion", {
                        detail: suggestion,
                      }),
                    );
                  }}
                  className="quick-action-btn text-[0.78rem]"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <ChatMessageComponent
            key={msg.id}
            message={msg}
            onListen={onListen}
            isListenPlaying={playingMessageId === msg.id}
          />
        ))}

        {/* Partial Transcript (live user speech) */}
        {partialTranscript && (
          <div className="flex gap-3 py-2.5 flex-row-reverse opacity-60">
            <UserAvatar className="w-8 h-8 bg-[var(--color-accent-light)] text-[var(--color-accent)] border-2 border-[var(--color-border)]" />
            <div className="flex flex-col items-end max-w-[75%]">
              <div
                className="message-content text-[0.9rem] leading-[1.65] bg-[var(--color-accent)] text-white bubble-user"
                style={{
                  padding: "4px 15px",
                  borderRadius: "9999px 4px 9999px 9999px",
                }}
              >
                {partialTranscript}
              </div>
            </div>
          </div>
        )}

        {/* Streaming response */}
        {streamingText && (
          <div className="flex gap-3 py-2.5">
            <AssistantAvatar className="w-8 h-8" />
            <div className="flex flex-col items-start max-w-[75%]">
              <div
                className="message-content rounded-2xl rounded-bl-sm px-5 py-3.5 text-[0.9rem] leading-[1.6] bg-[var(--color-bg-tertiary)] text-[var(--color-text-primary)] border border-[var(--color-border)]"
                dangerouslySetInnerHTML={{
                  __html: marked.parse(streamingText, { async: false }),
                }}
              />
            </div>
          </div>
        )}

        {/* Typing Indicator - Shimmer */}
        {isTyping && (
          <div className="flex gap-3 py-2.5">
            <AssistantAvatar className="w-8 h-8" />
            <div className="typing-shimmer-container">
              <div className="typing-shimmer-line" style={{ width: "75%" }} />
              <div className="typing-shimmer-line" style={{ width: "50%" }} />
              <div className="typing-shimmer-line" style={{ width: "30%" }} />
            </div>
          </div>
        )}

        {/* Form Progress Bar (sticky inside chat) */}
        {formProgress && formProgress.total > 0 && (
          <div className="form-progress-bar sticky bottom-0 z-[5] mt-4">
            <div className="form-progress-inner">
              <div className="flex items-center gap-2 text-[0.8rem] font-medium text-[var(--color-text-secondary)]">
                <FileText size={14} className="text-[var(--color-accent)]" />
                <span>{formName ?? "Form"}</span>
              </div>
              <div className="flex items-center gap-3 flex-1">
                <div className="form-progress-track">
                  <div
                    className="form-progress-fill"
                    style={{
                      width: `${Math.min(100, (formProgress.filled / formProgress.total) * 100)}%`,
                    }}
                  />
                </div>
                <span className="text-[0.75rem] font-semibold text-[var(--color-accent)] whitespace-nowrap">
                  {formProgress.filled}/{formProgress.total}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Scroll-to-bottom badge */}
      {showScrollBtn && (
        <button
          onClick={() => {
            containerRef.current?.scrollTo({
              top: containerRef.current.scrollHeight,
              behavior: "smooth",
            });
            setNewMsgCount(0);
          }}
          className="scroll-badge-btn"
        >
          {newMsgCount > 0 ? (
            <>
              <span className="scroll-badge-count">{newMsgCount}</span>
              <span className="text-[0.75rem]">
                new {newMsgCount === 1 ? "message" : "messages"}
              </span>
              <ChevronDown size={14} />
            </>
          ) : (
            <ChevronDown size={20} />
          )}
        </button>
      )}
    </div>
  );
}
