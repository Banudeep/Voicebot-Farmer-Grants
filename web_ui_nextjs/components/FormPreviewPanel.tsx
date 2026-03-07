"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { X, Download, FileText } from "lucide-react";

interface FormPreviewPanelProps {
  isOpen: boolean;
  formName: string | null;
  onClose: () => void;
}

export default function FormPreviewPanel({
  isOpen,
  formName,
  onClose,
}: FormPreviewPanelProps) {
  const [loading, setLoading] = useState(true);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const resizerRef = useRef<HTMLDivElement>(null);
  const [panelWidth, setPanelWidth] = useState<number | null>(null);

  const getPdfUrl = useCallback((name: string) => {
    const hostname = window.location.hostname;
    const port =
      hostname === "localhost" || hostname === "127.0.0.1" ? ":8080" : "";
    return `${window.location.protocol}//${hostname}${port}/pdf/filled_${name}?t=${Date.now()}`;
  }, []);

  // Reload PDF when formName changes
  useEffect(() => {
    if (!isOpen || !formName) return;
    setLoading(true);
    if (iframeRef.current) {
      iframeRef.current.src = getPdfUrl(formName);
    }
  }, [isOpen, formName, getPdfUrl]);

  const handleIframeLoad = () => {
    setLoading(false);
  };

  const handleDownload = () => {
    if (!formName) return;
    window.open(getPdfUrl(formName), "_blank");
  };

  // Resizer drag logic
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = panelRef.current?.offsetWidth ?? 500;

    // Disable iframe pointer events during resize
    if (iframeRef.current) {
      iframeRef.current.style.pointerEvents = "none";
    }
    if (resizerRef.current) {
      resizerRef.current.classList.add("resizing");
    }

    const onMouseMove = (ev: MouseEvent) => {
      const delta = startX - ev.clientX;
      const newWidth = Math.max(
        350,
        Math.min(startWidth + delta, window.innerWidth * 0.7),
      );
      setPanelWidth(newWidth);
    };

    const onMouseUp = () => {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
      if (iframeRef.current) {
        iframeRef.current.style.pointerEvents = "auto";
      }
      if (resizerRef.current) {
        resizerRef.current.classList.remove("resizing");
      }
    };

    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  }, []);

  if (!isOpen) return null;

  return (
    <>
      {/* Resizer */}
      <div
        ref={resizerRef}
        onMouseDown={handleMouseDown}
        className="w-2 cursor-col-resize bg-[var(--color-border)] hover:bg-[var(--color-accent-light)] transition-colors z-[15] flex-shrink-0"
        style={{ minHeight: "100%" }}
      />

      {/* Panel */}
      <div
        ref={panelRef}
        className="flex flex-col bg-[var(--color-bg-secondary)] border-l border-[var(--color-border)] z-10 flex-shrink-0"
        style={{
          width: panelWidth ?? "50%",
          minWidth: 350,
          animation: "slideInRight 0.3s ease-out",
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--color-border)]">
          <div className="flex items-center gap-2 text-[1rem] font-semibold text-[var(--color-text-primary)]">
            <FileText size={18} className="text-[var(--color-accent)]" />
            <span>Form Preview</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleDownload}
              className="flex items-center gap-1 px-2.5 py-1.5 text-[0.8rem] rounded-md bg-[var(--color-bg-tertiary)] border border-[var(--color-border)] text-[var(--color-text-primary)] cursor-pointer hover:bg-[var(--color-accent-light)] transition-colors"
              title="Download PDF"
            >
              <Download size={14} />
              Download
            </button>
            <button
              onClick={onClose}
              className="w-7 h-7 flex items-center justify-center rounded bg-transparent border-none text-[var(--color-text-tertiary)] cursor-pointer hover:text-[var(--color-text-primary)] hover:bg-[var(--color-bg-tertiary)] transition-all"
              title="Close panel"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* Form name */}
        <div className="px-5 py-3 bg-[var(--color-bg-tertiary)] text-[0.85rem] font-medium text-[var(--color-text-secondary)] border-b border-[var(--color-border)]">
          {formName ?? "No form selected"}
        </div>

        {/* Disclaimer */}
        <div
          className="flex items-center gap-1.5 px-4 py-2 text-[0.75rem] border-b border-[var(--color-border)]"
          style={{
            background: "rgba(255, 193, 7, 0.1)",
            color: "#f59e0b",
          }}
        >
          <span>⚠️</span>
          <span>
            Preview only — manual edits here won&apos;t be saved. Use the voice
            assistant to fill the form.
          </span>
        </div>

        {/* PDF iframe */}
        <div className="flex-1 relative overflow-hidden bg-[var(--color-bg-tertiary)]">
          <iframe
            ref={iframeRef}
            className="w-full h-full border-none bg-white"
            src="about:blank"
            onLoad={handleIframeLoad}
            title="PDF Preview"
          />
          {loading && (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-[var(--color-bg-secondary)] text-[var(--color-text-tertiary)] gap-3 text-[0.9rem]">
              <div
                className="w-8 h-8 border-[3px] border-[var(--color-border)] rounded-full"
                style={{
                  borderTopColor: "var(--color-accent)",
                  animation: "spin 1s linear infinite",
                }}
              />
              <div>Loading PDF...</div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
