"use client";

import { useState } from "react";
import Header from "@/components/Header";
import ChatContainer from "@/components/ChatContainer";
import Controls from "@/components/Controls";
import SettingsModal from "@/components/SettingsModal";
import FormPreviewPanel from "@/components/FormPreviewPanel";
import ToastContainer from "@/components/Toast";
import { useTheme } from "@/hooks/useTheme";
import { useAppSession } from "@/hooks/useAppSession";

export default function Home() {
  const { theme, toggleTheme } = useTheme();

  const {
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
    audioLevel,
    startRecording,
    stopRecording,
    handleSendText,
    handleQuickAction,
    handleEmailSummary,
  } = useAppSession();

  const [settingsOpen, setSettingsOpen] = useState(false);

  return (
    <div className="w-full h-screen bg-[var(--color-bg-primary)] flex flex-col transition-colors duration-300">
      <Header
        theme={theme}
        onToggleTheme={toggleTheme}
        onOpenSettings={() => setSettingsOpen(true)}
        connectionStatus={status}
        sessionId={sessionId}
        mode={mode}
        onSwitchMode={handleSwitchMode}
        formActive={currentFormName !== null}
        formPanelOpen={formPanelOpen}
        onToggleFormPanel={handleToggleFormPanel}
      />

      <div className="flex-1 flex min-h-0 w-full">
        {/* Left: Chat + Controls */}
        <div className="flex-1 flex flex-col items-center min-w-0">
          <ChatContainer
            messages={messages}
            isTyping={isTyping}
            partialTranscript={partialTranscript}
            streamingText={streamingText}
            onListen={handleListen}
            playingMessageId={playingMessageId}
            formProgress={formProgress}
            formName={currentFormName}
          />

          <Controls
            mode={mode}
            isConnected={status === "connected"}
            isRecording={isRecording}
            audioLevel={audioLevel}
            onStartRecording={startRecording}
            onStopRecording={stopRecording}
            onSendText={handleSendText}
            onQuickAction={handleQuickAction}
            onEmailSummary={handleEmailSummary}
            hasMessages={messages.length > 0}
          />
        </div>

        {/* Right: Form Preview Panel */}
        <FormPreviewPanel
          key={formPdfVersion}
          isOpen={formPanelOpen}
          formName={currentFormName}
          onClose={handleCloseFormPanel}
        />
      </div>

      <SettingsModal
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onSave={(voice, speed) => {
          handleSaveSettings(voice, speed);
          setSettingsOpen(false);
        }}
        currentVoice={currentVoice}
        currentSpeed={currentSpeed}
      />

      <ToastContainer />
    </div>
  );
}
