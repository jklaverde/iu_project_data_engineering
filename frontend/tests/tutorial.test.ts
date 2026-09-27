// Unit tests for the guided tour (D54, UC-14, FR-T1-T6).
// Run with Node's built-in runner - no test dependency (NFR-10):
//   npm test        (= node --test tests/)
// Node >= 23.6 strips TypeScript types natively; these files import the pure
// tutorial modules with explicit .ts extensions for that reason. This folder
// is outside src/, so the production `tsc -b` build never sees it.

import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";

import { placeCard, spotlightRect, MARGIN } from "../src/tutorial/placement.ts";
import { TOURS, UI_TEXT, stepCounter, type TourStep } from "../src/tutorial/tourContent.ts";
import { createTourPrefs, defaultLang, type StorageLike } from "../src/tutorial/tourPrefs.ts";

const SRC = join(import.meta.dirname, "..", "src");
const allSteps: [string, TourStep][] = Object.entries(TOURS).flatMap(([role, steps]) =>
  steps.map((s) => [role, s] as [string, TourStep]),
);

function allText(step: TourStep): string[] {
  return [step.title.en, step.title.de, step.body.en, step.body.de, ...(step.bullets?.en ?? []), ...(step.bullets?.de ?? [])];
}

// ------------------------------------------------------------ content ---

test("every step is complete in English and German", () => {
  for (const [role, step] of allSteps) {
    for (const text of allText(step)) assert.ok(text.trim().length > 0, `${role}/${step.id} has empty text`);
    assert.notEqual(step.title.en, step.title.de, `${role}/${step.id} title is not translated`);
    assert.notEqual(step.body.en, step.body.de, `${role}/${step.id} body is not translated`);
    if (step.bullets) {
      assert.equal(step.bullets.en.length, step.bullets.de.length, `${role}/${step.id} bullet count differs`);
    }
  }
  for (const [key, text] of Object.entries(UI_TEXT)) {
    assert.ok(text.en && text.de, `UI text ${key} missing a language`);
  }
});

test("tour text never cites internal codes", () => {
  // User-facing rule: no decision/requirement ids in anything a user reads.
  const internal = /\b(D\d{1,3}|UC-\d+|FR-[A-Z]+\d*|NFR-\d+)\b|REQUIREMENTS\.md/;
  for (const [role, step] of allSteps) {
    for (const text of allText(step)) assert.doesNotMatch(text, internal, `${role}/${step.id}: "${text}"`);
  }
});

test("step ids are unique within each tour", () => {
  for (const [role, steps] of Object.entries(TOURS)) {
    const ids = steps.map((s) => s.id);
    assert.equal(new Set(ids).size, ids.length, `duplicate step id in ${role} tour`);
  }
});

test("every highlighted element exists in the UI source", () => {
  const files: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const path = join(dir, entry.name);
      if (entry.isDirectory()) walk(path);
      else if (path.endsWith(".tsx")) files.push(readFileSync(path, "utf8"));
    }
  };
  walk(SRC);
  const source = files.join("\n");
  for (const [role, step] of allSteps) {
    if (step.target) {
      assert.ok(source.includes(`data-tour="${step.target}"`), `${role}/${step.id}: no element with data-tour="${step.target}"`);
    }
  }
});

test("both tours start with an untargeted welcome and end at the tour controls", () => {
  for (const steps of Object.values(TOURS)) {
    assert.equal(steps[0].target, undefined);
    assert.equal(steps.at(-1)!.target, "tour-controls");
  }
});

test("the planner tour explains every sensor type", () => {
  const sensors = TOURS.planner.find((s) => s.id === "planner-sensors")!;
  const en = sensors.bullets!.en.join(" ");
  const de = sensors.bullets!.de.join(" ");
  for (const word of ["Carbon monoxide", "LPG", "Smoke", "Temperature", "Humidity", "Light and motion", "Pressure"]) {
    assert.ok(en.includes(word), `missing ${word}`);
  }
  for (const word of ["Kohlenmonoxid", "Flüssiggas", "Rauch", "Temperatur", "Luftfeuchte", "Licht und Bewegung", "Luftdruck"]) {
    assert.ok(de.includes(word), `missing ${word}`);
  }
});

test("the tours are honest about derived history and simulated pressure", () => {
  for (const [role, steps] of Object.entries(TOURS)) {
    const en = steps.flatMap(allText).join(" ");
    assert.match(en, /derived from a 2020 dataset/, `${role} tour does not say history is derived`);
    assert.match(en, /abgeleitet/, `${role} tour (German) does not say history is derived`);
    assert.match(en, /[Pp]ressure[^.]*simulated/, `${role} tour does not say pressure is simulated`);
  }
});

test("steps about a sensor's details are flagged as needing a selected sensor", () => {
  for (const step of TOURS.planner) {
    const insideDetail = ["planner-scores", "planner-gauges", "planner-timeline", "planner-compare", "planner-log"];
    if (step.target && insideDetail.includes(step.target)) assert.ok(step.needsSensor, step.id);
  }
});

test("step counter is localized", () => {
  assert.equal(stepCounter("en", 2, 9), "Step 2 of 9");
  assert.equal(stepCounter("de", 2, 9), "Schritt 2 von 9");
});

// -------------------------------------------------------- preferences ---

function memoryStorage(): StorageLike & { data: Map<string, string> } {
  const data = new Map<string, string>();
  return { data, getItem: (k) => data.get(k) ?? null, setItem: (k, v) => void data.set(k, v) };
}

const throwingStorage: StorageLike = {
  getItem() {
    throw new Error("blocked");
  },
  setItem() {
    throw new Error("blocked");
  },
};

test("a new browser starts the tour automatically", () => {
  const prefs = createTourPrefs(memoryStorage());
  assert.equal(prefs.autoStart("planner"), true);
  assert.equal(prefs.autoStart("admin"), true);
});

test("turning the automatic start off is remembered, per role", () => {
  const storage = memoryStorage();
  createTourPrefs(storage).setAutoStart("planner", false);
  const reloaded = createTourPrefs(storage); // a later page load
  assert.equal(reloaded.autoStart("planner"), false);
  assert.equal(reloaded.autoStart("admin"), true);
  reloaded.setAutoStart("planner", true);
  assert.equal(createTourPrefs(storage).autoStart("planner"), true);
});

test("blocked storage falls back to defaults and still toggles within the page", () => {
  const prefs = createTourPrefs(throwingStorage, "en-US");
  assert.equal(prefs.autoStart("admin"), true);
  prefs.setAutoStart("admin", false); // must not throw
  assert.equal(prefs.autoStart("admin"), false);
  assert.equal(prefs.lang(), "en");
});

test("no storage at all behaves like blocked storage", () => {
  const prefs = createTourPrefs(null, "de-DE");
  assert.equal(prefs.autoStart("planner"), true);
  assert.equal(prefs.lang(), "de");
});

test("language defaults to the browser language and is remembered", () => {
  assert.equal(defaultLang("de-AT"), "de");
  assert.equal(defaultLang("en-GB"), "en");
  assert.equal(defaultLang("fr-FR"), "en");
  assert.equal(defaultLang(undefined), "en");
  const storage = memoryStorage();
  createTourPrefs(storage, "en-US").setLang("de");
  assert.equal(createTourPrefs(storage, "en-US").lang(), "de");
});

test("an unknown stored language is ignored", () => {
  const storage = memoryStorage();
  storage.data.set("tour.lang", "fr");
  assert.equal(createTourPrefs(storage, "de-DE").lang(), "de");
});

// ---------------------------------------------------------- placement ---

const VIEWPORT = { width: 1200, height: 800 };
const CARD = { width: 400, height: 240 };

test("the card goes below the element when there is room", () => {
  const pos = placeCard({ top: 100, left: 500, width: 200, height: 50 }, CARD, VIEWPORT);
  assert.equal(pos.placement, "below");
  assert.ok(pos.top > 150);
  assert.equal(pos.left, 400); // centered under the element
});

test("the card goes above an element near the bottom", () => {
  const pos = placeCard({ top: 650, left: 500, width: 200, height: 50 }, CARD, VIEWPORT);
  assert.equal(pos.placement, "above");
  assert.ok(pos.top + CARD.height < 650);
});

test("a tall panel on the right gets the card beside it, not over it", () => {
  // the sensor-detail sidebar case: no room above or below, room to the left
  const panel = { top: 100, left: 800, width: 380, height: 650 };
  const pos = placeCard(panel, { width: 400, height: 600 }, VIEWPORT);
  assert.equal(pos.placement, "left");
  assert.ok(pos.left + 400 <= panel.left);
  assert.ok(pos.top >= MARGIN && pos.top + 600 <= VIEWPORT.height - MARGIN);
});

test("a tall panel on the left gets the card to its right", () => {
  const pos = placeCard({ top: 50, left: 20, width: 500, height: 700 }, CARD, VIEWPORT);
  assert.equal(pos.placement, "right");
  assert.equal(pos.left, 20 + 500 + 14);
});

test("a very tall element gets the card pinned to the bottom", () => {
  const pos = placeCard({ top: 0, left: 0, width: 1200, height: 790 }, CARD, VIEWPORT);
  assert.equal(pos.placement, "bottom");
  assert.equal(pos.top, VIEWPORT.height - CARD.height - MARGIN);
});

test("no element means a centered card", () => {
  const pos = placeCard(null, CARD, VIEWPORT);
  assert.equal(pos.placement, "center");
  assert.equal(pos.left, 400);
  assert.equal(pos.top, 280);
});

test("the card never leaves the viewport horizontally", () => {
  const left = placeCard({ top: 100, left: 0, width: 20, height: 20 }, CARD, VIEWPORT);
  const right = placeCard({ top: 100, left: 1190, width: 10, height: 20 }, CARD, VIEWPORT);
  assert.equal(left.left, MARGIN);
  assert.equal(right.left, VIEWPORT.width - CARD.width - MARGIN);
});

test("the spotlight frame is padded and clipped to the viewport", () => {
  assert.deepEqual(spotlightRect({ top: 100, left: 100, width: 50, height: 20 }, VIEWPORT, 6),
    { top: 94, left: 94, width: 62, height: 32 });
  assert.deepEqual(spotlightRect({ top: -50, left: -10, width: 2000, height: 2000 }, VIEWPORT, 6),
    { top: 0, left: 0, width: 1200, height: 800 });
});
