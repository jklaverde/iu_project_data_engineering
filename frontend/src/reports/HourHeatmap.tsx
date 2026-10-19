import { useCallback } from "react";
import type { Heatmap } from "../types";
import ReportChart, { baseAxis, type ChartPalette } from "./ReportChart";
import { fmtHour, fmtShortMonth } from "./reportFormat";

const HOURS = Array.from({ length: 24 }, (_, h) => String(h).padStart(2, "0"));

// Month x hour-of-day heatmap (D55). Not weekday x hour: the history before
// go-live repeats an 8-day source, so weekdays would all look the same.
export default function HourHeatmap({
  heatmap,
  label,
  unit,
  height = 300,
}: {
  heatmap: Heatmap;
  label: string;
  unit: string;
  height?: number;
}) {
  const build = useCallback(
    (p: ChartPalette) => {
      const data: [number, number, number][] = [];
      heatmap.values.forEach((row, y) =>
        row.forEach((v, x) => {
          if (v !== null) data.push([x, y, v]);
        }),
      );
      const digits = unit === "°C" ? 1 : unit === "%" ? 0 : 4;
      return {
        animation: false,
        grid: { left: 54, right: 16, top: 8, bottom: 62 },
        tooltip: {
          formatter: (params: unknown) => {
            const [x, y, v] = (params as { value: [number, number, number] }).value;
            return `${fmtShortMonth(heatmap.months[y])}, ${fmtHour(x)}<br/>${label}: ${v.toFixed(digits)} ${unit}`;
          },
        },
        xAxis: { type: "category" as const, data: HOURS, name: "hour of day", nameLocation: "middle" as const, nameGap: 22, nameTextStyle: { color: p.text, fontSize: 10 }, ...baseAxis(p), splitArea: { show: false } },
        yAxis: { type: "category" as const, data: heatmap.months.map(fmtShortMonth), ...baseAxis(p) },
        visualMap: {
          min: heatmap.min ?? 0,
          max: heatmap.max ?? 1,
          orient: "horizontal" as const,
          left: "center",
          bottom: 0,
          itemHeight: 140,
          itemWidth: 10,
          calculable: false,
          precision: digits,
          inRange: { color: p.heat },
          textStyle: { color: p.text, fontSize: 10 },
          text: [`high ${unit}`, "low"],
        },
        series: [{ type: "heatmap" as const, data, itemStyle: { borderColor: "transparent" } }],
      };
    },
    [heatmap, label, unit],
  );

  if (heatmap.min === null) return <p className="waiting">Not enough stored history for a daily rhythm yet.</p>;
  return <ReportChart build={build} height={height} />;
}
