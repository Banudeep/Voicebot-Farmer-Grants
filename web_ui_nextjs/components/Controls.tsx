"use client";

import { useRef, useCallback, useState, useEffect } from "react";
import { Send, Mic, Mail, Search, FileText } from "lucide-react";
import type { InteractionMode } from "@/lib/constants";
import { QUICK_ACTIONS } from "@/lib/constants";

interface ControlsProps {
  mode: InteractionMode;
  isConnected: boolean;
  isRecording: boolean;
  onStartRecording: () => void;
  onStopRecording: () => void;
  onSendText: (text: string) => void;
  onQuickAction: (text: string) => void;
  onEmailSummary: () => void;
  hasMessages: boolean;
}

export default function Controls({
  mode,
  isConnected,
  isRecording,
  onStartRecording,
  onStopRecording,
  onSendText,
  onQuickAction,
  onEmailSummary,
  hasMessages,
}: ControlsProps) {
  const textInputRef = useRef<HTMLTextAreaElement>(null);
  const textInputWrapperRef = useRef<HTMLDivElement>(null);
  const [text, setText] = useState("");
  const [isMultiline, setIsMultiline] = useState(false);
  const [isScrollable, setIsScrollable] = useState(false);

  const MIN_INPUT_HEIGHT = 54;
  const MAX_INPUT_HEIGHT = 270;

  const resizeTextInput = useCallback(() => {
    const input = textInputRef.current;
    if (!input) return;

    if (textInputWrapperRef.current) {
      textInputWrapperRef.current.classList.remove("multiline");
    }

    input.style.height = "auto";
    const naturalHeight = input.scrollHeight;
    const nextHeight = Math.max(
      MIN_INPUT_HEIGHT,
      Math.min(naturalHeight, MAX_INPUT_HEIGHT),
    );
    input.style.height = `${nextHeight}px`;

    setIsScrollable(naturalHeight > MAX_INPUT_HEIGHT);
    setIsMultiline(naturalHeight > MIN_INPUT_HEIGHT + 2);
  }, []);

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed) return;
    onSendText(trimmed);
    setText("");
    if (textInputRef.current) {
      textInputRef.current.style.height = `${MIN_INPUT_HEIGHT}px`;
    }
    setIsMultiline(false);
    setIsScrollable(false);
  }, [text, onSendText]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Auto-resize textarea
  useEffect(() => {
    resizeTextInput();
  }, [text, resizeTextInput]);

  const handleMicClick = () => {
    if (isRecording) {
      onStopRecording();
    } else {
      onStartRecording();
    }
  };

  return (
    <div className="flex flex-col items-center gap-3 w-full px-6 relative z-[1] pb-5 bg-[var(--color-bg-primary)]">
      {/* Voice Mode Panel */}
      {mode === "voice" && (
        <div className="flex flex-col items-center gap-5 w-full py-2.5">
          <div className="flex items-center justify-center gap-8">
            <button
              onClick={handleMicClick}
              disabled={!isConnected}
              title={
                isRecording
                  ? "Tap to stop recording"
                  : "Tap to start the Audio call"
              }
              className={`mic-btn-large ${isRecording ? "recording" : ""}`}
            >
              <Mic size={28} />
            </button>
          </div>
        </div>
      )}

      {/* Text Input */}
      {mode === "text" && (
        <div className="text-input-container active max-w-[850px] mx-auto w-full">
          <div
            ref={textInputWrapperRef}
            className={`text-input-wrapper ${isMultiline ? "multiline" : ""}`}
          >
            <textarea
              ref={textInputRef}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={!isConnected}
              placeholder="Ask about grants, programs, eligibility..."
              rows={1}
              className={`text-input ${isScrollable ? "is-scrollable" : ""}`}
            />
            <button
              onClick={handleSend}
              disabled={!isConnected || !text.trim()}
              className="send-text-btn"
            >
              <Send
                size={18}
                className="translate-x-[-1px] translate-y-[1px]"
              />
            </button>
          </div>
        </div>
      )}

      {/* Quick Actions */}
      <div className="quick-actions max-w-[850px] mx-auto mt-2">
        {QUICK_ACTIONS.map((qa, idx) => {
          const icons = [Search, FileText];
          const Icon = icons[idx] || Search;
          return (
            <button
              key={qa.action}
              onClick={() => onQuickAction(qa.action)}
              className="quick-action-btn"
            >
              <Icon size={16} />
              {qa.label}
            </button>
          );
        })}
        <button
          onClick={onEmailSummary}
          disabled={!hasMessages}
          className="quick-action-btn"
        >
          <Mail size={16} />
          Email summary
        </button>
      </div>
    </div>
  );
}
