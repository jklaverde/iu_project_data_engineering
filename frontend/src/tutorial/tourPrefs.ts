// Per-browser tour preferences: whether the tour starts by itself for a role,
// and the tour language. Browser storage, not the server - the two role
// accounts are shared, so a server-side switch would flip it for everyone
// using that account.
//
// Storage can be missing or throw (private windows, blocked site data), so
// every access is guarded and the defaults apply: the tour still works, it is
// just not remembered. Pure logic with an injected storage, unit-tested in
// frontend/tests.

import type { TourLang, TourRole } from "./tourContent.ts";

export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

const AUTO_START_KEY = (role: TourRole) => `tour.autostart.${role}`;
const LANG_KEY = "tour.lang";

export interface TourPrefs {
  autoStart(role: TourRole): boolean;
  setAutoStart(role: TourRole, value: boolean): void;
  lang(): TourLang;
  setLang(lang: TourLang): void;
}

function safeGet(storage: StorageLike | null, key: string): string | null {
  try {
    return storage ? storage.getItem(key) : null;
  } catch {
    return null;
  }
}

function safeSet(storage: StorageLike | null, key: string, value: string): void {
  try {
    storage?.setItem(key, value);
  } catch {
    // not remembered - acceptable, see header comment
  }
}

export function defaultLang(browserLanguage: string | undefined): TourLang {
  return browserLanguage?.toLowerCase().startsWith("de") ? "de" : "en";
}

export function createTourPrefs(storage: StorageLike | null, browserLanguage?: string): TourPrefs {
  // In-memory fallback so toggling still works within the page when storage fails.
  const memory = new Map<string, string>();
  const read = (key: string) => safeGet(storage, key) ?? memory.get(key) ?? null;
  const write = (key: string, value: string) => {
    memory.set(key, value);
    safeSet(storage, key, value);
  };

  return {
    autoStart(role) {
      // Default on: a browser that has never seen the tour starts it once.
      return read(AUTO_START_KEY(role)) !== "off";
    },
    setAutoStart(role, value) {
      write(AUTO_START_KEY(role), value ? "on" : "off");
    },
    lang() {
      const stored = read(LANG_KEY);
      return stored === "en" || stored === "de" ? stored : defaultLang(browserLanguage);
    },
    setLang(lang) {
      write(LANG_KEY, lang);
    },
  };
}

// The real browser storage, if the accessor itself does not throw.
export function browserStorage(): StorageLike | null {
  try {
    return typeof window !== "undefined" ? window.localStorage : null;
  } catch {
    return null;
  }
}
