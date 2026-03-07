"use client";

import { useState, useEffect } from "react";
import { X, User, CheckCircle, Settings, Mic } from "lucide-react";
import { VOICE_OPTIONS } from "@/lib/constants";

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (voice: string, speed: number) => void;
  currentVoice: string;
  currentSpeed: number;
}

export default function SettingsModal({
  isOpen,
  onClose,
  onSave,
  currentVoice,
  currentSpeed,
}: SettingsModalProps) {
  const [selectedVoice, setSelectedVoice] = useState(() => currentVoice);
  const [speed, setSpeed] = useState(() => currentSpeed);

  // Reset local state when modal is opened so cancelled changes don't persist
  useEffect(() => {
    if (isOpen) {
      setSelectedVoice(currentVoice);
      setSpeed(currentSpeed);
    }
  }, [isOpen, currentVoice, currentSpeed]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 bg-black/55 backdrop-blur-[3px] flex items-center justify-center z-[9999]"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-[var(--settings-modal-bg)] border border-[var(--settings-modal-border)] shadow-[0_10px_40px_rgba(0,0,0,0.8)] w-[480px] max-w-[90vw] rounded-xl p-6 flex flex-col gap-6">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-2 text-xl font-bold text-[var(--color-text-primary)]">
            <Settings size={22} />
            Voice Settings
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 min-w-[32px] flex items-center justify-center rounded-full border-none bg-transparent text-[var(--color-text-tertiary)] cursor-pointer"
          >
            <X size={16} />
          </button>
        </div>

        {/* Voice Selection */}
        <div className="flex flex-col gap-3">
          <div className="text-[0.95rem] font-semibold text-[var(--color-text-primary)]">
            Assistant Voice
          </div>
          <div className="grid grid-cols-2 gap-3">
            {VOICE_OPTIONS.map((voice) => {
              const isSelected = selectedVoice === voice.value;
              return (
                <div
                  key={voice.id}
                  onClick={() => setSelectedVoice(voice.value)}
                  className={`border rounded-3xl py-2 pr-4 pl-2 flex items-center gap-3 cursor-pointer transition-all duration-200 ${
                    isSelected
                      ? "border-[var(--color-accent)] bg-[var(--settings-card-selected-bg)]"
                      : "border-[var(--settings-card-border)] bg-transparent"
                  }`}
                >
                  <div
                    className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0 ${
                      isSelected
                        ? "bg-[var(--color-accent)] text-white"
                        : "bg-[var(--settings-avatar-bg)] text-[var(--settings-avatar-color)]"
                    }`}
                  >
                    <User size={20} />
                  </div>
                  <div className="flex flex-col flex-1">
                    <div className="text-[0.95rem] font-semibold text-[var(--color-text-primary)]">
                      {voice.name}
                    </div>
                    <div className="text-[0.75rem] text-[var(--color-text-tertiary)]">
                      {voice.style}
                    </div>
                  </div>
                  {isSelected && (
                    <CheckCircle
                      size={18}
                      className="text-[var(--color-accent)]"
                    />
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Speaking Rate */}
        <div className="flex flex-col gap-3">
          <div className="flex justify-between items-center">
            <div className="text-[0.95rem] font-semibold text-[var(--color-text-primary)]">
              Speaking Rate
            </div>
            <span className="text-[var(--color-accent)] text-[0.95rem] font-semibold">
              {speed.toFixed(1)}x
            </span>
          </div>
          <div className="flex flex-col gap-2 mt-2">
            <div className="relative h-4 flex items-center">
              {/* Track with marks */}
              <div className="absolute top-1/2 left-0 right-0 -translate-y-1/2 h-2 rounded-full bg-[var(--settings-slider-track)] flex justify-between items-center px-[6px] pointer-events-none">
                <div className="w-1 h-1 bg-[var(--settings-slider-mark)] rounded-full" />
                <div className="w-1 h-1 bg-[var(--settings-slider-mark)] rounded-full" />
                <div className="w-1 h-1 bg-[var(--settings-slider-mark)] rounded-full" />
                <div className="w-1 h-1 bg-[var(--settings-slider-mark)] rounded-full" />
              </div>
              {/* Range input */}
              <input
                type="range"
                min="0.5"
                max="2.0"
                step="0.05"
                value={speed}
                onChange={(e) => setSpeed(parseFloat(e.target.value))}
                className="settings-range-input relative w-full"
              />
            </div>
            <div className="flex relative text-[0.75rem] text-[var(--color-text-tertiary)] h-4">
              <span className="absolute left-0">Slow</span>
              <span className="absolute left-[33.33%] -translate-x-1/2">
                Normal
              </span>
              <span className="absolute right-0">Fast</span>
            </div>
          </div>
        </div>

        {/* Input Device */}
        <div className="flex flex-col gap-3">
          <div className="text-[0.95rem] font-semibold text-[var(--color-text-primary)]">
            Input Device
          </div>
          <div className="w-full px-4 py-3 border border-[var(--settings-card-border)] rounded-[20px] bg-[var(--settings-input-bg)] text-[0.95rem] text-[var(--color-text-primary)] flex items-center justify-between">
            <span className="flex items-center gap-2">
              <Mic size={18} className="text-[var(--color-text-tertiary)]" />
              Default - System Microphone
            </span>
          </div>
          <span className="text-[0.75rem] text-[var(--color-text-tertiary)]">
            Uses your system&apos;s default microphone input.
          </span>
        </div>

        {/* Actions */}
        <div className="flex justify-end items-center gap-4 mt-2">
          <button
            onClick={onClose}
            className="bg-transparent border-none text-[var(--settings-cancel-color)] font-medium text-[0.95rem] cursor-pointer p-2"
          >
            Cancel
          </button>
          <button
            onClick={() => onSave(selectedVoice, speed)}
            className="bg-[var(--settings-save-bg)] text-[var(--settings-save-color)] border-none rounded-[20px] px-5 py-2.5 font-semibold text-[0.95rem] cursor-pointer"
          >
            Save Changes
          </button>
        </div>
      </div>
    </div>
  );
}
