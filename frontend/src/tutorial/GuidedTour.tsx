import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { placeCard, spotlightRect, type CardPosition, type Rect } from "./placement";
import { stepCounter, UI_TEXT, type TourLang, type TourStep } from "./tourContent";

// How long to keep looking for a step's element - e.g. the planner's detail
// panel only renders after onStepEnter has selected a sensor.
const TARGET_WAIT_MS = 1500;
const TARGET_POLL_MS = 50;
const DEFAULT_CARD = { width: 400, height: 240 };

function findTarget(step: TourStep): HTMLElement | null {
  return step.target ? document.querySelector<HTMLElement>(`[data-tour="${step.target}"]`) : null;
}

function viewport() {
  return { width: window.innerWidth, height: window.innerHeight };
}

function toRect(el: HTMLElement): Rect {
  const r = el.getBoundingClientRect();
  return { top: r.top, left: r.left, width: r.width, height: r.height };
}

// A spotlight tour (UC-14, FR-T1): dims the page, frames one real element per
// step and shows a card explaining what it is and why it matters. Steps whose
// element is not on screen fall back to a centered card.
export default function GuidedTour({
  steps,
  lang,
  onLangChange,
  onClose,
  onStepEnter,
}: {
  steps: TourStep[];
  lang: TourLang;
  onLangChange: (lang: TourLang) => void;
  onClose: (completed: boolean) => void;
  onStepEnter?: (step: TourStep) => void;
}) {
  const [index, setIndex] = useState(0);
  const [target, setTarget] = useState<Rect | null>(null);
  const [cardSize, setCardSize] = useState(DEFAULT_CARD);
  const cardRef = useRef<HTMLDivElement | null>(null);
  const elementRef = useRef<HTMLElement | null>(null);
  const step = steps[index];
  const last = index === steps.length - 1;

  const next = useCallback(() => {
    if (last) onClose(true);
    else setIndex((i) => i + 1);
  }, [last, onClose]);
  const back = useCallback(() => setIndex((i) => Math.max(0, i - 1)), []);

  // Enter a step: let the host prepare the screen, then find, scroll to and
  // measure the step's element.
  useEffect(() => {
    onStepEnter?.(step);
    elementRef.current = null;
    setTarget(null);
    if (!step.target) return;

    // Polled with setTimeout, not requestAnimationFrame: rAF never fires while
    // the tab is hidden, so a user who switched tabs mid-tour came back to
    // steps stuck on a centered card (found live, D54).
    const started = Date.now();
    let timer = 0;
    const look = () => {
      const el = findTarget(step);
      if (el) {
        const tall = el.getBoundingClientRect().height > window.innerHeight * 0.6;
        el.scrollIntoView({ block: tall ? "start" : "center", inline: "nearest" });
        elementRef.current = el;
        setTarget(toRect(el));
      } else if (Date.now() - started < TARGET_WAIT_MS) {
        timer = window.setTimeout(look, TARGET_POLL_MS);
      }
    };
    look();
    return () => window.clearTimeout(timer);
    // onStepEnter is deliberately not a dependency: re-running a step because
    // the host re-rendered would re-scroll the page under the user.
  }, [step]);

  // Keep the frame on the element while the page scrolls or resizes.
  useEffect(() => {
    const remeasure = () => {
      if (elementRef.current) setTarget(toRect(elementRef.current));
    };
    window.addEventListener("resize", remeasure);
    window.addEventListener("scroll", remeasure, true);
    return () => {
      window.removeEventListener("resize", remeasure);
      window.removeEventListener("scroll", remeasure, true);
    };
  }, []);

  useLayoutEffect(() => {
    const el = cardRef.current;
    if (el) setCardSize({ width: el.offsetWidth, height: el.offsetHeight });
  }, [index, lang, target]);

  useEffect(() => {
    cardRef.current?.focus();
  }, [index]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose(false);
      else if (e.key === "ArrowRight") next();
      else if (e.key === "ArrowLeft") back();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [next, back, onClose]);

  const vp = viewport();
  const position: CardPosition = placeCard(target, cardSize, vp);
  const frame = target ? spotlightRect(target, vp) : null;
  const bullets = step.bullets?.[lang];

  return (
    <div className="tour-layer" aria-live="polite">
      {/* Blocks clicks on the page while the tour is open; the frame's
          shadow provides the dimming around the highlighted element. */}
      <div className={`tour-backdrop ${frame ? "" : "tour-backdrop-dim"}`} />
      {frame && (
        <div
          className="tour-spotlight"
          style={{ top: frame.top, left: frame.left, width: frame.width, height: frame.height }}
        />
      )}
      <div
        ref={cardRef}
        className={`tour-card tour-card-${position.placement}`}
        style={{ top: position.top, left: position.left }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="tour-title"
        tabIndex={-1}
      >
        <div className="tour-card-head">
          <span className="tour-counter">{stepCounter(lang, index + 1, steps.length)}</span>
          <div className="tour-lang" role="group" aria-label={UI_TEXT.language[lang]}>
            {(["en", "de"] as const).map((l) => (
              <button
                key={l}
                className={`tour-lang-btn ${lang === l ? "tour-lang-btn-active" : ""}`}
                onClick={() => onLangChange(l)}
                aria-pressed={lang === l}
              >
                {l.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
        <h3 id="tour-title">{step.title[lang]}</h3>
        <p>{step.body[lang]}</p>
        {bullets && (
          <ul className="tour-bullets">
            {bullets.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        )}
        <div className="tour-actions">
          <button className="btn btn-ghost tour-skip" onClick={() => onClose(false)}>
            {UI_TEXT.skip[lang]}
          </button>
          <div className="tour-nav">
            {index > 0 && (
              <button className="btn btn-ghost" onClick={back}>
                {UI_TEXT.back[lang]}
              </button>
            )}
            <button className="btn btn-accent" onClick={next}>
              {last ? UI_TEXT.finish[lang] : UI_TEXT.next[lang]}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
