import { useEffect, useState } from "react";
import { fetchSensors } from "../api";
import type { SensorEntry } from "../types";

const POLL_INTERVAL_MS = Number(import.meta.env.VITE_SENSORS_POLL_INTERVAL_MS ?? 5000);

export function useSensors() {
  const [sensors, setSensors] = useState<SensorEntry[]>([]);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const res = await fetchSensors();
        if (!cancelled) setSensors(res.sensors);
      } catch {
        // transient - next tick retries
      }
    };
    poll();
    const timer = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  return sensors;
}
