"use client";

import { useState, useEffect, useCallback } from "react";

export function useTheme() {
  const [theme, setTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    const saved = localStorage.getItem("theme");
    const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const initial = (saved as "light" | "dark") || (systemDark ? "dark" : "light");
    setTheme(initial);
    document.documentElement.setAttribute("data-theme", initial);

    const listener = (e: MediaQueryListEvent) => {
      if (!localStorage.getItem("theme")) {
        const t = e.matches ? "dark" : "light";
        setTheme(t);
        document.documentElement.setAttribute("data-theme", t);
      }
    };
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", listener);
    return () => {
      window.matchMedia("(prefers-color-scheme: dark)").removeEventListener("change", listener);
    };
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next = prev === "dark" ? "light" : "dark";
      // Force all elements to transition at the same rate
      document.documentElement.classList.add("theme-transitioning");
      document.documentElement.setAttribute("data-theme", next);
      localStorage.setItem("theme", next);
      // Remove the class after the transition completes
      setTimeout(() => {
        document.documentElement.classList.remove("theme-transitioning");
      }, 350);
      return next;
    });
  }, []);

  return { theme, toggleTheme };
}
