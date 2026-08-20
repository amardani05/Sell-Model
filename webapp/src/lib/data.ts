import {
  Backtest, DecilePaths, Drilldown, Exclusions, FactorIC, Holdings, MCSim, Meta, Overrides,
  ScoreRow, SectorDeciles, Torpedo, Transitions, Validation,
} from "./types";

async function getJSONOptional<T>(path: string, fallback: T): Promise<T> {
  // Optional payloads must never take the whole dashboard down: a file added
  // after the last pipeline run simply falls back until the next refresh.
  try {
    const resp = await fetch(path);
    if (!resp.ok) return fallback;
    return (await resp.json()) as T;
  } catch {
    return fallback;
  }
}

async function getJSON<T>(path: string): Promise<T> {
  const resp = await fetch(path);
  if (!resp.ok) throw new Error(`Failed to fetch ${path}: ${resp.status}`);
  return (await resp.json()) as T;
}

export async function loadAll() {
  const [meta, scores, sectorDeciles, torpedo, factorIC, validation, backtest,
         mcSim, exclusions, transitions, overrides, holdings,
         decilePaths] = await Promise.all([
    getJSON<Meta>("/meta.json"),
    getJSON<ScoreRow[]>("/data/scores.json"),
    getJSON<SectorDeciles>("/data/sector_deciles.json"),
    getJSON<Torpedo>("/data/torpedo.json"),
    getJSON<FactorIC>("/data/factor_ic.json"),
    getJSON<Validation>("/data/validation.json"),
    getJSON<Backtest>("/data/backtest.json"),
    getJSON<MCSim>("/data/mc_sim.json"),
    getJSON<Exclusions>("/data/exclusions.json"),
    getJSON<Transitions>("/data/transitions.json"),
    getJSON<Overrides>("/data/overrides.json"),
    getJSONOptional<Holdings>("/data/holdings.json",
      { as_of: null, source: "", holdings: [] }),
    getJSON<DecilePaths>("/data/decile_paths.json").catch(
      () => ({ date: null, horizon: null, benchmark_adjusted: false, series: [] } as DecilePaths)),
  ]);
  return { meta, scores, sectorDeciles, torpedo, factorIC, validation, backtest,
           mcSim, exclusions, transitions, overrides, holdings, decilePaths };
}

export type Bundle = Awaited<ReturnType<typeof loadAll>>;

// The per name drill down is the largest payload on the site (about 1.9 MB
// raw, 330 KB gzipped, roughly 45% of the initial transfer) and most sessions
// never open a profile, so it is fetched the first time someone actually opens
// one and then kept for the rest of the session. The promise itself is cached,
// so two fast clicks share one request rather than racing.
let drilldownPromise: Promise<Drilldown> | null = null;

export function loadDrilldown(): Promise<Drilldown> {
  if (!drilldownPromise) {
    drilldownPromise = getJSON<Drilldown>("/data/drilldown.json").catch((e) => {
      drilldownPromise = null;   // let a later click retry a failed fetch
      throw e;
    });
  }
  return drilldownPromise;
}

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
