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
  return (
    <PlotComponent
      data={data as any}
      layout={{ ...BASE_LAYOUT, ...layout, autosize: true, height } as any}
      config={{ displayModeBar: true, responsive: true, displaylogo: false } as any}
      style={{ width: "100%", height }}
      useResizeHandler
    />
  );
}
