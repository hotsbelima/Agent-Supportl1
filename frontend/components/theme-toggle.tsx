"use client";

import { useEffect, useSyncExternalStore } from "react";

type Theme = "dark" | "light";

const STORAGE_KEY = "agent-support-theme";
const CHANGE_EVENT = "agent-support-theme-change";

function getTheme(): Theme {
  return window.localStorage.getItem(STORAGE_KEY) === "light" ? "light" : "dark";
}

function subscribeTheme(onStoreChange: () => void) {
  const handleStorage = () => onStoreChange();
  window.addEventListener("storage", handleStorage);
  window.addEventListener(CHANGE_EVENT, handleStorage);
  return () => {
    window.removeEventListener("storage", handleStorage);
    window.removeEventListener(CHANGE_EVENT, handleStorage);
  };
}

export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribeTheme, getTheme, () => "dark");

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  function toggleTheme() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    window.localStorage.setItem(STORAGE_KEY, next);
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }

  return (
    <button
      className="theme-toggle"
      type="button"
      onClick={toggleTheme}
      aria-label={theme === "dark" ? "Включить светлую тему" : "Включить тёмную тему"}
      title={theme === "dark" ? "Светлая тема" : "Тёмная тема"}
    >
      <span aria-hidden="true">{theme === "dark" ? "☀" : "☾"}</span>
      <span>{theme === "dark" ? "Светлая" : "Тёмная"}</span>
    </button>
  );
}
