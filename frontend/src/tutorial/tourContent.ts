// Guided-tour content for both roles, in English and German.
//
// Pure data, no imports: unit-tested directly by frontend/tests (node --test),
// which also checks the rules the text must follow - every step translated,
// every `target` present as a data-tour attribute in the UI, and no internal
// codes (decision/requirement ids) in anything a user reads.

export type TourRole = "planner" | "admin";
export type TourLang = "en" | "de";

export interface Localized {
  en: string;
  de: string;
}

export interface TourStep {
  id: string;
  // Value of the data-tour attribute to highlight; absent = centered card.
  target?: string;
  // The step's element only exists once a sensor is selected (planner).
  needsSensor?: boolean;
  title: Localized;
  body: Localized;
  bullets?: { en: string[]; de: string[] };
}

export const UI_TEXT = {
  next: { en: "Next", de: "Weiter" },
  back: { en: "Back", de: "Zurück" },
  skip: { en: "Skip tour", de: "Tour überspringen" },
  finish: { en: "Finish", de: "Fertig" },
  stepOf: { en: "Step {n} of {total}", de: "Schritt {n} von {total}" },
  language: { en: "Language", de: "Sprache" },
} as const;

const PLANNER: TourStep[] = [
  {
    id: "planner-welcome",
    title: {
      en: "Welcome to the Lingen (Ems) sensor overview",
      de: "Willkommen bei der Sensorübersicht Lingen (Ems)",
    },
    body: {
      en: "This screen answers two questions for planning decisions: is the air safe right now where people live and work, and is a problem a one-off or a persistent pattern? This short tour shows where each answer comes from.",
      de: "Diese Ansicht beantwortet zwei Fragen für Planungsentscheidungen: Ist die Luft dort, wo Menschen leben und arbeiten, gerade unbedenklich – und ist ein Problem ein Einzelfall oder ein dauerhaftes Muster? Diese kurze Tour zeigt, woher die Antworten kommen.",
    },
  },
  {
    id: "planner-status",
    target: "planner-status",
    title: { en: "Status at a glance", de: "Status auf einen Blick" },
    body: {
      en: "How many sensors are OK, in warning or critical right now. The first question of the day, answered in a second – and a reason to look closer when anything is not green.",
      de: "Wie viele Sensoren gerade in Ordnung, in Warnung oder kritisch sind. Die erste Frage des Tages in einer Sekunde beantwortet – und ein Anlass, genauer hinzusehen, sobald etwas nicht grün ist.",
    },
  },
  {
    id: "planner-map",
    target: "planner-map",
    title: { en: "Where it happens", de: "Wo es passiert" },
    body: {
      en: "Each pin is a sensor, colored by its current status. Location matters: a warning next to a main road or a school calls for a different response than one in an open field. Click a pin to open its details.",
      de: "Jeder Pin ist ein Sensor, eingefärbt nach seinem aktuellen Status. Der Ort ist entscheidend: Eine Warnung an einer Hauptstraße oder Schule verlangt eine andere Reaktion als auf freiem Feld. Ein Klick auf einen Pin öffnet die Details.",
    },
  },
  {
    id: "planner-detail",
    target: "planner-detail",
    needsSensor: true,
    title: { en: "One sensor, explained", de: "Ein Sensor im Detail" },
    body: {
      en: "The status badge says whether this location is fine, worth watching or critical, and names the reason. The line below it says where the reading comes from – live from the pipeline or replayed from the source dataset – so you always know how far to trust a number.",
      de: "Das Statusabzeichen zeigt, ob der Standort unauffällig, beobachtungswürdig oder kritisch ist, und nennt den Grund. Die Zeile darunter sagt, woher der Messwert stammt – live aus der Pipeline oder aus dem Quelldatensatz wiedergegeben –, damit klar ist, wie belastbar eine Zahl ist.",
    },
  },
  {
    id: "planner-scores",
    target: "planner-scores",
    needsSensor: true,
    title: { en: "Scores that support a decision", de: "Kennzahlen für Entscheidungen" },
    body: {
      en: "Three numbers summarize the location for non-specialists:",
      de: "Drei Zahlen fassen den Standort auch für Nicht-Fachleute zusammen:",
    },
    bullets: {
      en: [
        "Air quality score (0–100, higher is better): how close the worst pollutant is to its safety limit.",
        "Comfort index (0–100): how pleasant temperature and humidity are together – relevant for heat stress and indoor climate.",
        "Chronic exposure: the share of recent hours with an out-of-range reading. High means a persistent problem worth an intervention, not a passing spike.",
      ],
      de: [
        "Luftqualitätswert (0–100, höher ist besser): wie nah der kritischste Schadstoff an seinem Sicherheitsgrenzwert liegt.",
        "Komfortindex (0–100): wie angenehm Temperatur und Luftfeuchte zusammen sind – wichtig für Hitzebelastung und Raumklima.",
        "Dauerbelastung: der Anteil der letzten Stunden mit einem Wert außerhalb des Normalbereichs. Ein hoher Wert bedeutet ein dauerhaftes Problem, das eine Maßnahme rechtfertigt – keine kurze Spitze.",
      ],
    },
  },
  {
    id: "planner-sensors",
    target: "planner-gauges",
    needsSensor: true,
    title: { en: "What each sensor type tells you", de: "Was jeder Sensortyp aussagt" },
    body: {
      en: "Each gauge compares the current value with its normal range. Temperature and humidity ranges follow the season, so a cold January day is not reported as a problem. What each measurement is good for:",
      de: "Jede Anzeige vergleicht den aktuellen Wert mit seinem Normalbereich. Die Bereiche für Temperatur und Luftfeuchte folgen der Jahreszeit, sodass ein kalter Januartag nicht als Problem gemeldet wird. Wofür jede Messung nützlich ist:",
    },
    bullets: {
      en: [
        "Carbon monoxide (CO): an invisible, odorless gas from traffic and heating. Elevated values show where people are exposed and support traffic and ventilation decisions.",
        "LPG: bottled gas used for heating and cooking. A rise is an early warning of a leak near storage or appliances – a safety matter, not a comfort one.",
        "Smoke: combustion particles from fires, wood burning or exhaust. Separates a single event from a recurring hotspot.",
        "Temperature: comfort and heat stress. Because the normal range follows the season, a real heat spell stands out – useful for finding urban heat islands.",
        "Humidity: comfort and mold risk; combined with temperature it drives the comfort index.",
        "Light and motion: daylight and activity around the sensor. They explain when readings rise, for example CO during busy hours.",
        "Pressure: simulated, for weather context only – not a basis for decisions.",
      ],
      de: [
        "Kohlenmonoxid (CO): ein unsichtbares, geruchloses Gas aus Verkehr und Heizungen. Erhöhte Werte zeigen, wo Menschen belastet sind, und stützen Entscheidungen zu Verkehr und Lüftung.",
        "Flüssiggas (LPG): Gas für Heizung und Kochen aus Flaschen oder Tanks. Ein Anstieg ist eine Frühwarnung vor einem Leck an Lager oder Geräten – eine Sicherheitsfrage, keine Komfortfrage.",
        "Rauch: Verbrennungspartikel aus Bränden, Holzfeuerung oder Abgasen. Unterscheidet ein einzelnes Ereignis von einem wiederkehrenden Brennpunkt.",
        "Temperatur: Komfort und Hitzebelastung. Da der Normalbereich der Jahreszeit folgt, fällt eine echte Hitzeperiode auf – hilfreich, um städtische Wärmeinseln zu finden.",
        "Luftfeuchte: Komfort und Schimmelrisiko; zusammen mit der Temperatur ergibt sie den Komfortindex.",
        "Licht und Bewegung: Tageslicht und Aktivität am Sensor. Sie erklären, wann Werte steigen, etwa CO zu Stoßzeiten.",
        "Luftdruck: simuliert, nur als Wetterkontext – keine Entscheidungsgrundlage.",
      ],
    },
  },
  {
    id: "planner-timeline",
    target: "planner-timeline",
    needsSensor: true,
    title: { en: "Behavior over time", de: "Verlauf über die Zeit" },
    body: {
      en: "The same metric at five resolutions, from minutes to months; shaded areas mark periods outside the normal range. This is where a one-off spike and a persistent problem look different – and a persistent one is what justifies spending money on a fix. Note: history from before this system went live is derived from a 2020 dataset (its 8 days repeated, adjusted for the season); it is illustrative, not measured.",
      de: "Dieselbe Messgröße in fünf Auflösungen, von Minuten bis Monaten; schattierte Flächen markieren Zeiträume außerhalb des Normalbereichs. Hier unterscheiden sich eine einmalige Spitze und ein dauerhaftes Problem – und nur ein dauerhaftes rechtfertigt Ausgaben für eine Maßnahme. Hinweis: Der Verlauf vor dem Start dieses Systems ist aus einem Datensatz von 2020 abgeleitet (seine 8 Tage wiederholt, an die Jahreszeit angepasst); er ist illustrativ, nicht gemessen.",
    },
  },
  {
    id: "planner-compare",
    target: "planner-compare",
    needsSensor: true,
    title: { en: "Is today typical?", de: "Ist heute typisch?" },
    body: {
      en: "Overlay an earlier period – an hour, a day, a week, a month or a year ago – on every chart. It tells you whether current conditions are normal for this time of day, week or year, or a real departure worth acting on.",
      de: "Blendet einen früheren Zeitraum – vor einer Stunde, einem Tag, einer Woche, einem Monat oder einem Jahr – in jedes Diagramm ein. So sehen Sie, ob die aktuelle Lage für diese Tages-, Wochen- oder Jahreszeit normal ist oder eine echte Abweichung, die Handeln erfordert.",
    },
  },
  {
    id: "planner-log",
    target: "planner-log",
    needsSensor: true,
    title: { en: "The evidence", de: "Die Belege" },
    body: {
      en: "The out-of-range log lists each period that fell outside its normal range, newest first, with the actual reading and how far it was off. Charts show how often; this log gives the exact numbers for a report or a conversation with residents.",
      de: "Das Protokoll der Grenzwertüberschreitungen listet jeden Zeitraum außerhalb seines Normalbereichs, neueste zuerst, mit dem tatsächlichen Messwert und der Abweichung. Die Diagramme zeigen, wie oft; dieses Protokoll liefert die genauen Zahlen für einen Bericht oder ein Gespräch mit Anwohnern.",
    },
  },
  {
    id: "planner-dataset",
    target: "dataset-explorer",
    title: { en: "Where the history comes from", de: "Woher der Verlauf stammt" },
    body: {
      en: "The Dataset Explorer lets you scrub through the historical data behind the charts. Each reading names the original 2020 measurement it was derived from, so the history is transparent rather than a black box.",
      de: "Im Dataset Explorer können Sie die historischen Daten hinter den Diagrammen durchblättern. Jeder Wert nennt die ursprüngliche Messung von 2020, aus der er abgeleitet wurde – der Verlauf ist nachvollziehbar statt einer Blackbox.",
    },
  },
  {
    id: "planner-controls",
    target: "tour-controls",
    title: { en: "Come back any time", de: "Jederzeit wieder aufrufbar" },
    body: {
      en: "Reopen this tour from here, and choose whether it starts by itself when you log in. The setting is remembered in this browser only.",
      de: "Hier können Sie diese Tour erneut öffnen und festlegen, ob sie beim Anmelden automatisch startet. Die Einstellung wird nur in diesem Browser gespeichert.",
    },
  },
];

const ADMIN: TourStep[] = [
  {
    id: "admin-welcome",
    title: { en: "Welcome to the Pipeline Console", de: "Willkommen in der Pipeline-Konsole" },
    body: {
      en: "Planners decide on air quality from what this pipeline delivers, so their decisions are only as good as the data flow. This console shows whether data is arriving, being processed and stored – and gives you the tools to act before users notice a problem.",
      de: "Planerinnen und Planer entscheiden über Luftqualität auf Basis dessen, was diese Pipeline liefert – ihre Entscheidungen sind nur so gut wie der Datenfluss. Diese Konsole zeigt, ob Daten ankommen, verarbeitet und gespeichert werden, und bietet die Werkzeuge, um zu handeln, bevor Nutzer ein Problem bemerken.",
    },
  },
  {
    id: "admin-connection",
    target: "admin-connection",
    title: { en: "Is this console live?", de: "Ist diese Konsole live?" },
    body: {
      en: "Shows how this page receives updates: a live connection, or a polling fallback. If it says connecting, the numbers below may be stale – check this before drawing conclusions.",
      de: "Zeigt, wie diese Seite Aktualisierungen erhält: über eine Live-Verbindung oder ersatzweise per Abfrage. Steht hier „verbinden“, können die Zahlen darunter veraltet sein – prüfen Sie das, bevor Sie Schlüsse ziehen.",
    },
  },
  {
    id: "admin-flow",
    target: "admin-flow",
    title: { en: "The whole flow in one picture", de: "Der gesamte Fluss in einem Bild" },
    body: {
      en: "Sensor data moves from the producer through Kafka and Spark into Cassandra, with Grafana watching. The live state of each stage is drawn here, so a stalled stage is visible at a glance instead of after a user complains.",
      de: "Sensordaten fließen vom Producer über Kafka und Spark nach Cassandra, überwacht von Grafana. Der Live-Zustand jeder Stufe ist hier dargestellt – eine stockende Stufe fällt sofort auf, nicht erst nach einer Beschwerde.",
    },
  },
  {
    id: "admin-steps",
    target: "admin-stepper",
    title: { en: "Six checks, one per stage", de: "Sechs Prüfungen, eine pro Stufe" },
    body: {
      en: "Walk through the pipeline stage by stage. Each step proves one thing:",
      de: "Gehen Sie die Pipeline Stufe für Stufe durch. Jeder Schritt belegt eine Sache:",
    },
    bullets: {
      en: [
        "Deployment: every service is up and healthy.",
        "Ingestion: events are being produced, at what rate, and whether from the dataset or generated.",
        "Kafka: messages are buffered and consumers are keeping up.",
        "Spark: processing is progressing and anomalies are being detected.",
        "Cassandra: results are stored – and how full each node is, with a control to add capacity before it runs out.",
        "Summary: the end-to-end picture, with a link to the Grafana dashboards.",
      ],
      de: [
        "Deployment: Alle Dienste laufen und sind gesund.",
        "Ingestion: Ereignisse werden erzeugt – mit welcher Rate und ob aus dem Datensatz oder generiert.",
        "Kafka: Nachrichten werden gepuffert und die Verbraucher kommen hinterher.",
        "Spark: Die Verarbeitung schreitet voran und Anomalien werden erkannt.",
        "Cassandra: Ergebnisse werden gespeichert – und wie voll jeder Knoten ist, mit einer Steuerung, um rechtzeitig Kapazität hinzuzufügen.",
        "Zusammenfassung: das Gesamtbild, mit Link zu den Grafana-Dashboards.",
      ],
    },
  },
  {
    id: "admin-alerts",
    target: "admin-tab-alerts",
    title: { en: "Alerts, with the logs behind them", de: "Alarme mit den zugehörigen Logs" },
    body: {
      en: "Alerts raised by Grafana arrive here, each one click away from the log lines that explain it – from alert to root cause without searching. It also holds the action to free disk space safely when storage runs low.",
      de: "Von Grafana ausgelöste Alarme erscheinen hier, jeweils einen Klick von den erklärenden Logzeilen entfernt – vom Alarm zur Ursache ohne Suchen. Hier liegt auch die Aktion, um bei knappem Speicher sicher Platz freizugeben.",
    },
  },
  {
    id: "admin-kubernetes",
    target: "admin-tab-kubernetes",
    title: { en: "Health of every container", de: "Zustand jedes Containers" },
    body: {
      en: "Every pod's phase, readiness and restart count. It tells a service that is still starting apart from one that keeps crashing – without opening a terminal.",
      de: "Phase, Bereitschaft und Neustartzahl jedes Pods. So lässt sich ein Dienst, der noch startet, von einem unterscheiden, der immer wieder abstürzt – ohne Terminal.",
    },
  },
  {
    id: "admin-docs",
    target: "admin-tab-docs",
    title: { en: "The runbook, inside the app", de: "Das Betriebshandbuch in der App" },
    body: {
      en: "Architecture, deployment and troubleshooting documentation, including past incidents and how they were fixed. When something breaks, the answer is often already written down here.",
      de: "Dokumentation zu Architektur, Bereitstellung und Fehlerbehebung, einschließlich früherer Störungen und ihrer Lösung. Wenn etwas ausfällt, steht die Antwort oft schon hier.",
    },
  },
  {
    id: "admin-dataset",
    target: "dataset-explorer",
    title: { en: "Where the history comes from", de: "Woher der Verlauf stammt" },
    body: {
      en: "The Dataset Explorer shows the historical data behind the stored history. Data from before go-live is derived from a 2020 dataset (repeated and adjusted for the season), and pressure is simulated – useful to know when a planner asks where a number comes from.",
      de: "Der Dataset Explorer zeigt die historischen Daten hinter dem gespeicherten Verlauf. Daten vor dem Start sind aus einem Datensatz von 2020 abgeleitet (wiederholt und an die Jahreszeit angepasst), und der Luftdruck ist simuliert – gut zu wissen, wenn jemand fragt, woher eine Zahl stammt.",
    },
  },
  {
    id: "admin-controls",
    target: "tour-controls",
    title: { en: "Come back any time", de: "Jederzeit wieder aufrufbar" },
    body: {
      en: "Reopen this tour from here, and choose whether it starts by itself when you log in. The setting is remembered in this browser only.",
      de: "Hier können Sie diese Tour erneut öffnen und festlegen, ob sie beim Anmelden automatisch startet. Die Einstellung wird nur in diesem Browser gespeichert.",
    },
  },
];

export const TOURS: Record<TourRole, TourStep[]> = { planner: PLANNER, admin: ADMIN };

export function stepCounter(lang: TourLang, n: number, total: number): string {
  return UI_TEXT.stepOf[lang].replace("{n}", String(n)).replace("{total}", String(total));
}
