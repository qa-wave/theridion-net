// ─── i18n React context ────────────────────────────────────────────────────

import { createContext, useContext, useState, useCallback, type ReactNode } from "react";
import type { Locale, Messages } from "./types";
import { LOCALE_KEY, DEFAULT_LOCALE, SUPPORTED_LOCALES } from "./types";
import { getDictionary, makeT } from "./index";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function loadLocale(): Locale {
  try {
    const stored = localStorage.getItem(LOCALE_KEY) as Locale | null;
    if (stored && SUPPORTED_LOCALES.includes(stored)) return stored;
  } catch { /* SSR / private browsing */ }
  return DEFAULT_LOCALE;
}

function persistLocale(locale: Locale): void {
  try {
    localStorage.setItem(LOCALE_KEY, locale);
  } catch { /* ignore */ }
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: keyof Messages, params?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(loadLocale);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    persistLocale(next);
  }, []);

  const t = useCallback(
    (key: keyof Messages, params?: Record<string, string | number>) =>
      makeT(getDictionary(locale))(key, params),
    [locale],
  );

  return (
    <I18nContext.Provider value={{ locale, setLocale, t }}>
      {children}
    </I18nContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used inside <I18nProvider>");
  return ctx;
}

/** Convenience alias — mirrors the Weave pattern. */
export function useT(): I18nContextValue["t"] {
  return useI18n().t;
}
