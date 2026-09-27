import { useCallback, useMemo, useState } from "react";
import { TOURS, type TourLang, type TourRole } from "./tourContent";
import { browserStorage, createTourPrefs } from "./tourPrefs";

// Tour state for one role's screen (FR-T3): opens by itself on the first
// visit in this browser; finishing or skipping turns the automatic start off;
// the header control reopens it or turns the automatic start back on.
export function useGuidedTour(role: TourRole) {
  const prefs = useMemo(
    () => createTourPrefs(browserStorage(), typeof navigator !== "undefined" ? navigator.language : undefined),
    [],
  );
  const [autoStart, setAutoStartState] = useState(() => prefs.autoStart(role));
  const [open, setOpen] = useState(() => prefs.autoStart(role));
  const [lang, setLangState] = useState<TourLang>(() => prefs.lang());

  const start = useCallback(() => setOpen(true), []);

  const close = useCallback(() => {
    setOpen(false);
    prefs.setAutoStart(role, false);
    setAutoStartState(false);
  }, [prefs, role]);

  const setAutoStart = useCallback(
    (value: boolean) => {
      prefs.setAutoStart(role, value);
      setAutoStartState(value);
    },
    [prefs, role],
  );

  const setLang = useCallback(
    (value: TourLang) => {
      prefs.setLang(value);
      setLangState(value);
    },
    [prefs],
  );

  return { steps: TOURS[role], open, start, close, autoStart, setAutoStart, lang, setLang };
}
