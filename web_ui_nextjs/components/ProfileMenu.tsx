"use client";

import { useSession, signIn, signOut } from "next-auth/react";
import { useState, useRef, useEffect } from "react";
import { LogIn, LogOut, ChevronDown } from "lucide-react";

export default function ProfileMenu() {
  const { data: session, status } = useSession();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close dropdown on click outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  // Loading state
  if (status === "loading") {
    return (
      <div className="w-9 h-9 rounded-full bg-[var(--color-bg-tertiary)] animate-pulse" />
    );
  }

  // Not signed in
  if (!session) {
    return (
      <button
        onClick={() => signIn("microsoft-entra-id")}
        className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-[20px] text-[0.85rem] font-medium cursor-pointer transition-all bg-[var(--color-accent)] text-[var(--color-bg-primary)] border-none shadow-sm hover:opacity-90"
        title="Sign in with Microsoft"
      >
        <LogIn size={14} />
        Sign In
      </button>
    );
  }

  // Signed in — avatar + dropdown
  const userName = session.user?.name || "User";
  const userEmail = session.user?.email || "";
  const initials = userName
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  return (
    <div className="relative" ref={menuRef}>
      {/* Avatar button */}
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 cursor-pointer bg-transparent border-none p-0"
        title={userName}
      >
        {session.user?.image ? (
          <img
            src={session.user.image}
            alt={userName}
            className="w-9 h-9 rounded-full object-cover border-2 border-[var(--color-border)]"
          />
        ) : (
          <div className="w-9 h-9 rounded-full flex items-center justify-center border-2 border-[var(--color-border)] bg-[var(--color-accent-light)] text-[var(--color-accent)] text-[0.8rem] font-semibold select-none">
            {initials}
          </div>
        )}
        <ChevronDown
          size={14}
          className={`text-[var(--color-text-tertiary)] transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        />
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute top-[calc(100%+8px)] right-0 w-[260px] rounded-[14px] bg-[var(--color-bg-secondary)] border border-[var(--color-border)] shadow-lg z-50 overflow-hidden animate-[fadeInScale_0.15s_ease-out]">
          {/* User info */}
          <div className="px-4 py-3 border-b border-[var(--color-border)]">
            <p className="text-[0.9rem] font-semibold text-[var(--color-text-primary)] m-0 leading-snug truncate">
              {userName}
            </p>
            {userEmail && (
              <p className="text-[0.78rem] text-[var(--color-text-tertiary)] m-0 mt-0.5 leading-snug truncate">
                {userEmail}
              </p>
            )}
          </div>

          {/* Sign Out */}
          <div className="p-2">
            <button
              onClick={() => {
                setOpen(false);
                signOut();
              }}
              className="w-full flex items-center gap-2.5 px-3 py-2 rounded-[10px] text-[0.85rem] font-medium cursor-pointer bg-transparent border-none text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-tertiary)] hover:text-[var(--color-text-primary)] transition-colors text-left"
            >
              <LogOut size={16} />
              Sign Out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
