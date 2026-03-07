"use client";

import { useEffect, useState } from "react";

interface Toast {
  id: number;
  message: string;
  type: "success" | "error";
}

let toastId = 0;
const listeners: Array<(toast: Toast) => void> = [];

export function showToast(message: string, type: "success" | "error" = "success") {
  const toast: Toast = { id: ++toastId, message, type };
  listeners.forEach((fn) => fn(toast));
}

export default function ToastContainer() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    const handler = (toast: Toast) => {
      setToasts((prev) => [...prev, toast]);
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== toast.id));
      }, 3000);
    };
    listeners.push(handler);
    return () => {
      const idx = listeners.indexOf(handler);
      if (idx >= 0) listeners.splice(idx, 1);
    };
  }, []);

  return (
    <div className="fixed bottom-5 right-5 flex flex-col gap-2 z-[10000]">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`flex items-center gap-3 px-5 py-3 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-xl shadow-lg max-w-[300px] animate-[slideInRight_0.3s_ease] ${
            toast.type === "success" ? "border-l-4 border-l-[#38a169]" : "border-l-4 border-l-[#e53e3e]"
          }`}
        >
          <span className="text-lg">{toast.type === "success" ? "✓" : "✕"}</span>
          <span className="flex-1 text-[var(--color-text-primary)] text-[0.9rem]">{toast.message}</span>
        </div>
      ))}
    </div>
  );
}
