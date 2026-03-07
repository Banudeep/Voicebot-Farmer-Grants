"use client";

import { Bot, User } from "lucide-react";

/**
 * Shared avatar components used across ChatContainer and ChatMessage.
 * Eliminates duplicate inline SVGs for assistant/user avatars.
 */

export function AssistantAvatar({ size = 20, className = "" }: { size?: number; className?: string }) {
  return (
    <div
      className={`rounded-full flex items-center justify-center bg-[var(--color-accent-light)] text-[var(--color-accent)] flex-shrink-0 ${className}`}
    >
      <Bot size={size} />
    </div>
  );
}

export function UserAvatar({ size = 20, className = "" }: { size?: number; className?: string }) {
  return (
    <div
      className={`rounded-full flex items-center justify-center flex-shrink-0 ${className}`}
    >
      <User size={size} />
    </div>
  );
}
