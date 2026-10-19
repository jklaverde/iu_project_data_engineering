import * as echarts from "echarts";
import { useEffect, useRef } from "react";

// Chart for anything that may be printed (D55). Differs from EChartWrapper in
// three ways: SVG rendering (sharp in a PDF), a light palette while the
// browser prints (the app itself is dark; a dark chart on white paper loses
// its labels), and a fixed print width - the printed page is narrower than
// the screen, and ECharts does not resize itself for print.

export interface ChartPalette {
  text: string;
  axis: string;
  grid: string;
  series: string[];
  bad: string;
  band: string;
  heat: string[];
}

export const SCREEN_PALETTE: ChartPalette = {
  text: "#8d93b0",
  axis: "#2a3050",
  grid: "#232945",
  series: ["#5b8cff", "#8b6cff", "#34d399", "#fbbf24"],
  bad: "#fb6f84",
  band: "rgba(91, 140, 255, 0.10)",
  heat: ["#18203a", "#2f5fd0", "#a9c4ff"],
};

export const PRINT_PALETTE: ChartPalette = {
  text: "#374151",
  axis: "#9ca3af",
  grid: "#e5e7eb",
  series: ["#1d4ed8", "#6d28d9", "#047857", "#b45309"],
  bad: "#b91c1c",
  band: "rgba(29, 78, 216, 0.08)",
  heat: ["#f1f5ff", "#6d93f0", "#1e3a8a"],
};

// A4 portrait minus the print margins (styles.css @page), in CSS pixels.
const PRINT_WIDTH = 690;

export default function ReportChart({
  build,
  height = 260,
}: {
  build: (palette: ChartPalette) => echarts.EChartsOption;
  height?: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);
  const buildRef = useRef(build);
  buildRef.current = build;

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = echarts.init(containerRef.current, undefined, { renderer: "svg" });
    chartRef.current = chart;
    const onResize = () => chart.resize();
    const beforePrint = () => {
      chart.setOption({ ...buildRef.current(PRINT_PALETTE), animation: false }, true);
      chart.resize({ width: PRINT_WIDTH });
    };
    const afterPrint = () => {
      chart.setOption({ ...buildRef.current(SCREEN_PALETTE), animation: false }, true);
      chart.resize();
    };
    window.addEventListener("resize", onResize);
    window.addEventListener("beforeprint", beforePrint);
    window.addEventListener("afterprint", afterPrint);
    return () => {
      window.removeEventListener("resize", onResize);
      window.removeEventListener("beforeprint", beforePrint);
      window.removeEventListener("afterprint", afterPrint);
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(build(SCREEN_PALETTE), true);
  }, [build]);

  return <div ref={containerRef} className="report-chart" style={{ width: "100%", height }} />;
}

export function baseAxis(p: ChartPalette) {
  return {
    axisLine: { lineStyle: { color: p.axis } },
    axisLabel: { color: p.text, fontSize: 10 },
    splitLine: { lineStyle: { color: p.grid } },
  };
}
