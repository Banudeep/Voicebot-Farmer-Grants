"use client";

import { Moon, Sun, Settings, Menu, Mic, FileText } from "lucide-react";
import ProfileMenu from "@/components/ProfileMenu";
import type { ConnectionStatus } from "@/hooks/useWebSocket";
import type { InteractionMode } from "@/lib/constants";
import { showToast } from "@/components/Toast";

interface HeaderProps {
  theme: "light" | "dark";
  onToggleTheme: () => void;
  onOpenSettings: () => void;
  connectionStatus: ConnectionStatus;
  sessionId: string | null;
  mode: InteractionMode;
  onSwitchMode: (mode: InteractionMode) => void;
  formActive?: boolean;
  formPanelOpen?: boolean;
  onToggleFormPanel?: () => void;
}

export default function Header({
  theme,
  onToggleTheme,
  onOpenSettings,
  connectionStatus,
  sessionId,
  mode,
  onSwitchMode,
  formActive,
  formPanelOpen,
  onToggleFormPanel,
}: HeaderProps) {
  const connectionLabel =
    connectionStatus === "connected"
      ? "Connected"
      : connectionStatus === "connecting"
        ? "Connecting"
        : "Disconnected";

  const copySessionId = () => {
    if (sessionId) {
      navigator.clipboard.writeText(sessionId);
      showToast("Session ID copied!", "success");
    }
  };

  return (
    <header
      className="w-full flex items-center justify-between bg-[var(--color-bg-primary)] z-[1] relative box-border"
      style={{ padding: "24px 16px 24px 16px" }}
    >
      {/* Left: App icon + Title */}
      <div className="flex items-center gap-3 w-[280px]">
        <div className="w-[36px] h-[36px] rounded-[10px] bg-[var(--color-accent-light)] flex items-center justify-center text-[var(--color-accent)] shrink-0">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="w-[22px] h-[22px]"
          >
            <circle cx="7" cy="17" r="3"></circle>
            <circle cx="17" cy="17" r="3"></circle>
            <path d="M5 17H3v-4l2-4h6v8"></path>
            <path d="M11 9h4l3 4v4h-2"></path>
            <path d="M14 17h-3"></path>
          </svg>
        </div>
        <div className="flex flex-col">
          <h1 className="text-[1.05rem] font-bold tracking-tight leading-[1.3] text-[var(--color-text-primary)] m-0">
            USDA Grant Assist
          </h1>
          <span className="text-[0.78rem] text-[var(--color-text-tertiary)] leading-[1.2]">
            Application Helper
          </span>
        </div>
      </div>

      {/* Center: Mode Toggle */}
      <div className="absolute left-1/2 -translate-x-1/2 z-10">
        <div className="mode-toggle-switch" data-mode={mode}>
          <div
            onClick={() => onSwitchMode("text")}
            className={`mode-toggle-option ${mode === "text" ? "active" : ""}`}
            data-mode="text"
          >
            <Menu size={14} /> Text
          </div>
          <div
            onClick={() => onSwitchMode("voice")}
            className={`mode-toggle-option ${mode === "voice" ? "active" : ""}`}
            data-mode="voice"
          >
            <Mic size={14} /> Voice
          </div>
          <div className="mode-toggle-slider" />
        </div>
      </div>

      {/* Right: Session ID + Settings + Theme + User */}
      <div className="flex items-center gap-3">
        {/* Connection Status Dot */}
        <div
          className="flex items-center gap-1.5"
          title={connectionLabel}
        >
          <div
            className={`w-2.5 h-2.5 rounded-full ${
              connectionStatus === "connected"
                ? "bg-green-500"
                : connectionStatus === "connecting"
                  ? "bg-yellow-400 animate-pulse"
                  : "bg-red-500"
            }`}
          />
          <span className="text-[0.75rem] text-[var(--color-text-tertiary)] hidden sm:inline">
            {connectionLabel}
          </span>
        </div>

        {sessionId && (
          <span
            onClick={copySessionId}
            title={`Session ID: ${sessionId} (click to copy)`}
            className="inline-flex items-center whitespace-nowrap text-[0.75rem] leading-none px-3.5 py-1.5 rounded-[12px] font-mono border-2 border-[var(--color-border)] bg-[var(--color-bg-secondary)] cursor-pointer hover:bg-[var(--color-bg-tertiary)] text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)] transition-colors"
          >
            ID: {sessionId.substring(0, 8)}
          </span>
        )}
        {/* Settings Button */}
        <button
          onClick={onOpenSettings}
          className="w-9 h-9 rounded-full flex items-center justify-center border border-[var(--color-border)] bg-transparent cursor-pointer text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)] hover:text-[var(--color-text-primary)] transition-all"
        >
          <Settings size={20} className="stroke-[1.5]" />
        </button>

        {/* Theme Toggle Button */}
        <button
          onClick={onToggleTheme}
          className="w-9 h-9 rounded-full flex items-center justify-center border border-[var(--color-border)] bg-transparent cursor-pointer text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)] hover:text-[var(--color-text-primary)] transition-all"
          title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
        >
          {theme === "dark" ? (
            <Sun size={20} className="stroke-[1.5]" />
          ) : (
            <Moon size={20} className="stroke-[1.5]" />
          )}
        </button>

        {/* Form Toggle Button */}
        {formActive && (
          <button
            onClick={onToggleFormPanel}
            className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-[20px] text-[0.85rem] font-medium cursor-pointer transition-all shadow-sm ${
              formPanelOpen
                ? "bg-[var(--color-bg-tertiary)] text-[var(--color-text-primary)] border border-[var(--color-border)]"
                : "bg-[var(--color-accent)] text-[var(--color-bg-primary)] border-none"
            }`}
            title="Toggle form preview"
          >
            <FileText size={14} />
            {formPanelOpen ? "Hide Form" : "Show Form"}
          </button>
        )}

        {/* Profile Menu */}
        <ProfileMenu />
      </div>
    </header>
  );
}
