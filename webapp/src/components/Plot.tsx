import createPlotlyComponent from "react-plotly.js/factory";
// @ts-ignore — plotly.js-dist-min ships no types but is the browser bundle
import Plotly from "plotly.js-dist-min";

const PlotComponent = createPlotlyComponent(Plotly);

const BASE_LAYOUT: Partial<Plotly.Layout> = {
  paper_bgcolor: "transparent",
  plot_bgcolor: "transparent",
  font: { family: "Inter, system-ui, sans-serif", size: 12, color: "#1d2733" },
  margin: { l: 56, r: 24, t: 36, b: 48 },
  legend: { orientation: "h", y: -0.18 },
};

interface Props {
  data: Partial<Plotly.PlotData>[];
  layout?: Partial<Plotly.Layout>;
  height?: number;
}

export function Plot({ data, layout = {}, height = 420 }: Props) {
  const lay = layout as any;
  const merged: any = { ...BASE_LAYOUT, ...layout, autosize: true, height };
  merged.margin = { ...(BASE_LAYOUT.margin as any), ...lay.margin };
  merged.legend = { ...(BASE_LAYOUT.legend as any), ...lay.legend };
  // An x axis title and a bottom legend share the same band by default and
  // render on top of each other; give them separate bands whenever both exist.
  const hasXTitle = Boolean(lay?.xaxis?.title);
  const showsLegend = lay?.showlegend !== false
    && (data as any[]).filter((d) => d && d.name).length > 1;
  if (hasXTitle && showsLegend) {
    merged.margin.b = Math.max(merged.margin.b ?? 48, 112);
    merged.legend.y = Math.min(lay.legend?.y ?? -0.38, -0.38);
  }
  return (
    <PlotComponent
      data={data as any}
      layout={merged as any}
      config={{ displayModeBar: true, responsive: true, displaylogo: false } as any}
      style={{ width: "100%", height }}
      useResizeHandler
    />
  );
}
