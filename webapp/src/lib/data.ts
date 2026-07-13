import {
  Backtest, Drilldown, Exclusions, FactorIC, MCSim, Meta, Overrides, ScoreRow,
  SectorDeciles, Torpedo, Transitions, Validation,
} from "./types";

async function getJSON<T>(path: string): Promise<T> {
  const resp = await fetch(path);
  if (!resp.ok) throw new Error(`Failed to fetch ${path}: ${resp.status}`);
  return (await resp.json()) as T;
}

export async function loadAll() {
  const [meta, scores, sectorDeciles, torpedo, factorIC, validation, backtest,
         mcSim, exclusions, drilldown, transitions, overrides] = await Promise.all([
    getJSON<Meta>("/meta.json"),
    getJSON<ScoreRow[]>("/data/scores.json"),
    getJSON<SectorDeciles>("/data/sector_deciles.json"),
    getJSON<Torpedo>("/data/torpedo.json"),
    getJSON<FactorIC>("/data/factor_ic.json"),
    getJSON<Validation>("/data/validation.json"),
    getJSON<Backtest>("/data/backtest.json"),
    getJSON<MCSim>("/data/mc_sim.json"),
    getJSON<Exclusions>("/data/exclusions.json"),
    getJSON<Drilldown>("/data/drilldown.json"),
    getJSON<Transitions>("/data/transitions.json"),
    getJSON<Overrides>("/data/overrides.json"),
  ]);
  return { meta, scores, sectorDeciles, torpedo, factorIC, validation, backtest,
           mcSim, exclusions, drilldown, transitions, overrides };
}

export type Bundle = Awaited<ReturnType<typeof loadAll>>;

// ---- formatting helpers ----
export function fmt(v: number | null | undefined, d = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v.toFixed(d);
}
export function fmtSigned(v: number | null | undefined, d = 3): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return (v >= 0 ? "+" : "") + v.toFixed(d);
}
export function fmtPct(v: number | null | undefined, d = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return (v >= 0 ? "+" : "") + (v * 100).toFixed(d) + "%";
}
export function decileColor(decile: number | null | undefined, n = 10): string {
  if (decile === null || decile === undefined || Number.isNaN(decile)) return "#cccccc";
  // green (best, 1) -> red (worst, n)
  const t = (decile - 1) / (n - 1);
  const r = Math.round(46 + t * (179 - 46));
  const g = Math.round(122 + t * (0 - 122));
  const b = Math.round(75 + t * (27 - 75));
  return `rgb(${r},${g},${b})`;
}
