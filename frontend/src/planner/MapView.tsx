import * as L from "leaflet";
import "leaflet/dist/leaflet.css";
import { useEffect, useRef, useState } from "react";
import AboutModal from "../about/AboutModal";
import { useSensors } from "../state/useSensors";
import type { SensorEntry } from "../types";
import AlertFeed from "./AlertFeed";
import SensorDetailPanel from "./SensorDetailPanel";

const LINGEN_CENTER: [number, number] = [52.523, 7.322];
const LINGEN_ZOOM = 13;

const STATUS_COLOR: Record<string, string> = {
  ok: "#3ecf8e",
  warning: "#f5a623",
  critical: "#ff5d6c",
  unknown: "#9298b3",
};

function markerIcon(status: string): L.DivIcon {
  const color = STATUS_COLOR[status] ?? STATUS_COLOR.unknown;
  return L.divIcon({
    className: "sensor-marker",
    html: `<span style="background:${color}"></span>`,
    iconSize: [18, 18],
  });
}

function popupHtml(sensor: SensorEntry): string {
  const r = sensor.reading;
  const readingHtml = r
    ? `<div>CO ${r.co.toFixed(4)} · LPG ${r.lpg.toFixed(4)} · Smoke ${r.smoke.toFixed(4)}</div>
       <div>Temp ${r.temp.toFixed(1)}°C · Humidity ${r.humidity.toFixed(0)}%</div>`
    : "<div>No data yet</div>";
  const reasonHtml = sensor.status.reason ? `<div class="popup-reason">${sensor.status.reason}</div>` : "";
  return `<strong>${sensor.name}</strong><div class="popup-area">${sensor.area}</div>${readingHtml}${reasonHtml}`;
}

export default function MapView({ onLogout }: { onLogout: () => void }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markersRef = useRef<Record<string, L.Marker>>({});
  const sensors = useSensors();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showAbout, setShowAbout] = useState(false);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current).setView(LINGEN_CENTER, LINGEN_ZOOM);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap contributors",
      maxZoom: 19,
    }).addTo(map);
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    for (const sensor of sensors) {
      const icon = markerIcon(sensor.status.overall);
      const existing = markersRef.current[sensor.device_id];
      if (existing) {
        existing.setIcon(icon);
        existing.setPopupContent(popupHtml(sensor));
      } else {
        const marker = L.marker([sensor.lat, sensor.lon], { icon }).addTo(map);
        marker.bindPopup(popupHtml(sensor));
        marker.bindTooltip(sensor.name);
        marker.on("click", () => setSelectedId(sensor.device_id));
        markersRef.current[sensor.device_id] = marker;
      }
    }
  }, [sensors]);

  const selectedSensor = sensors.find((s) => s.device_id === selectedId) ?? null;

  return (
    <div className="planner-shell">
      <header>
        <h1>Environmental Overview — Lingen (Ems)</h1>
        <div className="header-right">
          <button className="btn btn-accent" onClick={() => setShowAbout(true)}>
            About the project
          </button>
          <button className="btn btn-ghost" onClick={onLogout}>
            Log out
          </button>
        </div>
      </header>

      {showAbout && <AboutModal onClose={() => setShowAbout(false)} />}

      <div className="planner-body">
        <div className="map-container" ref={containerRef} />
        <div className="planner-sidebar">
          <SensorDetailPanel sensor={selectedSensor} />
          <AlertFeed sensors={sensors} />
        </div>
      </div>
    </div>
  );
}
