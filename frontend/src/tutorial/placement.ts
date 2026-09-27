// Where the tour card goes relative to the highlighted element. Pure geometry,
// unit-tested in frontend/tests.

export interface Rect {
  top: number;
  left: number;
  width: number;
  height: number;
}

export interface Size {
  width: number;
  height: number;
}

export type Placement = "below" | "above" | "right" | "left" | "bottom" | "center";

export interface CardPosition {
  top: number;
  left: number;
  placement: Placement;
}

export const GAP = 14;
export const MARGIN = 16;

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(value, Math.max(min, max)));
}

// Below the target if the card fits there, else above, else beside it (right,
// then left) - a long card next to a tall panel must not cover the panel it
// describes (found live with the sensor-type step). A target with no room on
// any side (the full-width chart grid) is scrolled to the top by the
// component, so the card is pinned to the bottom of the viewport, covering
// only the target's lower part. No target at all: centered. The card always
// stays fully inside the viewport, MARGIN from the edges.
export function placeCard(target: Rect | null, card: Size, viewport: Size): CardPosition {
  const centered: CardPosition = {
    top: clamp((viewport.height - card.height) / 2, MARGIN, viewport.height - card.height - MARGIN),
    left: clamp((viewport.width - card.width) / 2, MARGIN, viewport.width - card.width - MARGIN),
    placement: "center",
  };
  if (!target) return centered;

  const left = clamp(
    target.left + target.width / 2 - card.width / 2,
    MARGIN,
    viewport.width - card.width - MARGIN,
  );
  const below = target.top + target.height + GAP;
  if (below + card.height <= viewport.height - MARGIN) {
    return { top: below, left, placement: "below" };
  }
  const above = target.top - GAP - card.height;
  if (above >= MARGIN) {
    return { top: above, left, placement: "above" };
  }
  const sideTop = clamp(target.top, MARGIN, viewport.height - card.height - MARGIN);
  const right = target.left + target.width + GAP;
  if (right + card.width <= viewport.width - MARGIN) {
    return { top: sideTop, left: right, placement: "right" };
  }
  const leftSide = target.left - GAP - card.width;
  if (leftSide >= MARGIN) {
    return { top: sideTop, left: leftSide, placement: "left" };
  }
  return { top: Math.max(MARGIN, viewport.height - card.height - MARGIN), left, placement: "bottom" };
}

// The highlighted area: the element's box plus a little padding, clipped to
// the viewport so a huge element does not produce an off-screen frame.
export function spotlightRect(target: Rect, viewport: Size, padding = 6): Rect {
  const top = Math.max(0, target.top - padding);
  const left = Math.max(0, target.left - padding);
  const bottom = Math.min(viewport.height, target.top + target.height + padding);
  const right = Math.min(viewport.width, target.left + target.width + padding);
  return { top, left, width: Math.max(0, right - left), height: Math.max(0, bottom - top) };
}
