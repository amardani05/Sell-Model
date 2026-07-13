import { ReactNode, createContext, useContext, useMemo, useState } from "react";
import { Bundle, fmt, fmtSigned, decileColor } from "../lib/data";
import { DrilldownName } from "../lib/types";
import { FACTOR_META, FAMILY_COLOR, factorLabel } from "../lib/factorMeta";
import { Plot } from "./Plot";
import { Term } from "./Term";
import { TickerFlag } from "./TickerFlag";

// ---------------------------------------------------------------------------
// Context: any table in the app can open the drill down for a ticker.
// ---------------------------------------------------------------------------
interface DrillDownAPI {
  open: (ticker: string) => void;
  close: () => void;
  hoverSummary: (ticker: string) => string;
  has: (ticker: string) => boolean;
}
const Ctx = createContext<DrillDownAPI>({
  open: () => {}, close: () => {}, hoverSummary: () => "", has: () => false,
});
export const useDrillDown = () => useContext(Ctx);

function topDrivers(d: DrilldownName, k = 3): { f: string; z: number }[] {
  return Object.entries(d.factors)
    .filter(([, v]) => v && v.z != null)
    .map(([f, v]) => ({ f, z: v!.z as number }))
    .sort((a, b) => b.z - a.z)
    .slice(0, k);
}

export function DrillDownProvider({ bundle, children }: { bundle: Bundle; children: ReactNode }) {
  const [ticker, setTicker] = useState<string | null>(null);
  const dd = bundle.drilldown;

  const api = useMemo<DrillDownAPI>(() => ({
    open: (tk) => setTicker(dd.names[tk.toUpperCase()] ? tk.toUpperCase() : null),
    close: () => setTicker(null),
    has: (tk) => !!dd.names[tk.toUpperCase()],
    hoverSummary: (tk) => {
      const d = dd.names[tk.toUpperCase()];
      if (!d) return "";
      const tops = topDrivers(d).map((t) => `${factorLabel(t.f)} ${fmtSigned(t.z, 1)}σ`);
      return `decile ${d.decile ?? "—"} · top flags: ${tops.join(", ")} · click for full breakdown`;
    },
  }), [dd]);

  const sel = ticker ? dd.names[ticker] : null;
  return (
    <Ctx.Provider value={api}>
      {children}
      {sel && ticker && <DrillDownPanel ticker={ticker} d={sel} bundle={bundle} onClose={api.close} />}
    </Ctx.Provider>
  );
}

// ---------------------------------------------------------------------------
// The risks section paragraph an analyst can paste into an ER note.
// Base rate claims are GATED: they only appear once the full factor era is
// long enough to estimate them honestly (>= 12 quarters).
// ---------------------------------------------------------------------------
const BASE_RATE_MIN_PERIODS = 12;

function riskParagraph(ticker: string, d: DrilldownName, bundle: Bundle): string {
  const meta = bundle.meta;
  const total = meta.n_factors;
  const drivers = Object.entries(d.factors)
    .filter(([, v]) => v && v.z != null)
    .map(([f, v]) => ({ f, z: v!.z as number }));
  const reds = drivers.filter((x) => x.z >= 0.5).sort((a, b) => b.z - a.z).slice(0, 3);
  const greens = drivers.filter((x) => x.z <= -0.5).sort((a, b) => a.z - b.z).slice(0, 2);

  const redTxt = reds.length
    ? reds.map((x) => {
        const m = FACTOR_META[x.f];
        return `${m?.label ?? x.f} (${fmt(Math.abs(x.z), 1)}σ ${m?.redFlag?.toLowerCase().startsWith("low") || m?.redFlag?.toLowerCase().startsWith("decl") ? "below" : "above"} sector peers)`;
      }).join("; ")
    : "no factor exceeds +0.5σ; the flag reflects breadth of mild weakness rather than a single driver";
  const greenTxt = greens.length
    ? ` Partially offset by ${greens.map((x) => `${FACTOR_META[x.f]?.label ?? x.f} (${fmt(Math.abs(x.z), 1)}σ favorable)`).join(" and ")}.`
    : "";

  const torp = d.torpedo_pct != null
    ? ` On the absolute risk lens the name sits at the ${Math.round(d.torpedo_pct)}th torpedo percentile (${d.torpedo_tier ?? "—"}).`
    : "";

  const era = bundle.validation.era_ic?.find((e) => e.era === "full-factor");
  const gate = (era?.n_periods ?? 0) >= BASE_RATE_MIN_PERIODS;
  let baseRate = "";
  if (gate) {
    const ev = bundle.validation.event_study?.filter((e) => e.cohort === "entrant");
    const last = ev && ev.length ? ev[ev.length - 1] : null;
    if (last && last.cum_mean != null) {
      baseRate = ` Historically, names entering the worst decile went on to lag their sector median by a cumulative ${(last.cum_mean * 100).toFixed(1)}% over the following ${ev!.length} quarters (n=${ev![0].n}).`;
    }
  } else {
    baseRate = ` [Base rates omitted: the full factor era spans only ${era?.n_periods ?? 0} quarter(s) — not yet enough history to cite honestly.]`;
  }

  return `${ticker} screens in risk decile ${d.decile ?? "—"} of 10 versus ${d.sector} peers on the Relative Sell Model (${d.n_factors_used}/${total} factors populated). Primary quantitative red flags: ${redTxt}.${greenTxt}${torp}${baseRate}`;
}

// ---------------------------------------------------------------------------
// The panel
// ---------------------------------------------------------------------------
function DrillDownPanel({ ticker, d, bundle, onClose }: {
  ticker: string; d: DrilldownName; bundle: Bundle; onClose: () => void;
}) {
  const dd = bundle.drilldown;
  const [copied, setCopied] = useState(false);

  const rows = dd.factor_order
    .map((f) => ({ f, v: d.factors[f] }))
    .filter((r) => r.v !== undefined);
  const present = rows.filter((r) => r.v && r.v.z != null) as { f: string; v: NonNullable<DrilldownName["factors"][string]> }[];
  const missing = rows.filter((r) => !r.v || r.v.z == null).map((r) => r.f);
  const sorted = [...present].sort((a, b) => (b.v.z ?? 0) - (a.v.z ?? 0));

  const deltaDecile = d.prev_decile != null && d.decile != null ? d.decile - d.prev_decile : null;
  const para = riskParagraph(ticker, d, bundle);

  const copy = async () => {
    try { await navigator.clipboard.writeText(para); setCopied(true); setTimeout(() => setCopied(false), 1600); }
    catch { /* clipboard unavailable */ }
  };

  return (
    <>
      <div className="dd-backdrop" onClick={onClose} />
      <aside className="dd-panel" role="dialog" aria-label={`${ticker} factor breakdown`}>
        <div className="dd-head">
          <div>
            <h2 className="dd-title">{ticker} <TickerFlag index={d.index_name} /></h2>
            <span className="muted">{d.sector} · as of {dd.as_of}</span>
          </div>
          <button className="dd-close" onClick={onClose} aria-label="close">✕</button>
        </div>

        <div className="metric-row">
          <div className="metric"><span className="metric-label">Sell decile</span>
            <span className="metric-value"><span className="decile-pill" style={{ background: decileColor(d.decile) }}>{d.decile ?? "—"}</span></span></div>
          <div className="metric"><span className="metric-label">Score</span>
            <span className="metric-value">{fmtSigned(d.score)}</span></div>
          <div className="metric"><span className="metric-label">QoQ decile</span>
            <span className={"metric-value" + (deltaDecile == null ? "" : deltaDecile > 0 ? " neg" : deltaDecile < 0 ? " pos" : "")}>
              {deltaDecile == null ? "—" : deltaDecile > 0 ? `▲ +${deltaDecile}` : deltaDecile < 0 ? `▼ ${deltaDecile}` : "="}
              {d.prev_decile != null && <span className="muted small"> (was {d.prev_decile})</span>}
            </span></div>
          <div className="metric"><span className="metric-label">Coverage</span>
            <span className={"metric-value" + (d.n_factors_used < 6 ? " neg" : "")}>{d.n_factors_used}/{bundle.meta.n_factors}</span></div>
          <div className="metric"><span className="metric-label"><Term id="torpedo">Torpedo</Term></span>
            <span className="metric-value">{d.torpedo_pct != null ? `${Math.round(d.torpedo_pct)}` : "—"}
              {d.torpedo_tier && <span className="tier-pill" style={{ background: bundle.meta.torpedo_tier_colors[d.torpedo_tier] ?? "#999", marginLeft: 6 }}>{d.torpedo_tier}</span>}
            </span></div>
        </div>

        <p className="muted small">
          The score is the plain average of the direction aligned sector neutral factor
          <Term id="zscore"> z scores</Term> below (over the {d.n_factors_used} populated factors). Bars right of
          zero push the name toward the sell sleeve; bars left of zero defend it. The within sector percentile
          says how extreme the reading is among {d.sector} peers (100 = worst).
        </p>

        {sorted.length > 0 && (
          <Plot height={Math.max(200, sorted.length * 26)}
            data={[{
              type: "bar", orientation: "h",
              x: sorted.map((r) => r.v.z).reverse(),
              y: sorted.map((r) => factorLabel(r.f)).reverse(),
              marker: { color: sorted.map((r) => ((r.v.z ?? 0) >= 0 ? "#b3001b" : "#2c7a4b")).reverse() },
              customdata: sorted.map((r) => [FACTOR_META[r.f]?.family ?? "", r.v.pct ?? NaN]).reverse() as any,
              hovertemplate: "%{y}: z=%{x:.2f} · sector %ile %{customdata[1]:.0f}<extra></extra>",
            }]}
            layout={{ xaxis: { title: "direction aligned z (right = red flag)", zeroline: true }, yaxis: { automargin: true }, margin: { l: 150, r: 16, t: 8, b: 44 } }} />
        )}

        <div className="table-wrap">
          <table className="data-table dd-table">
            <thead><tr>
              <th>Factor</th><th>Family</th><th style={{ textAlign: "right" }}>Raw value</th>
              <th style={{ textAlign: "right" }}>Aligned z</th>
              <th style={{ textAlign: "right" }}>Sector %ile</th>
              <th style={{ textAlign: "right" }}>Δ QoQ (z)</th>
            </tr></thead>
            <tbody>
              {sorted.map(({ f, v }) => {
                const m = FACTOR_META[f];
                const dz = v.prev_z != null && v.z != null ? v.z - v.prev_z : null;
                return (
                  <tr key={f}>
                    <td>
                      <span className="term" tabIndex={0}>{m?.label ?? f}
                        <span className="term-tip" role="tooltip">
                          <strong>{m?.label ?? f}</strong>
                          {m ? `${m.formula}. Red flag: ${m.redFlag}. Basis: ${m.anomaly}.` : ""}
                        </span>
                      </span>
                    </td>
                    <td><span className="group-pill" style={{ background: FAMILY_COLOR[m?.family ?? ""] ?? "#999" }}>{m?.family ?? ""}</span></td>
                    <td style={{ textAlign: "right" }}>{v.raw != null ? formatRaw(f, v.raw) : "—"}</td>
                    <td style={{ textAlign: "right", fontWeight: 650, color: (v.z ?? 0) >= 0 ? "#b3001b" : "#2c7a4b" }}>{fmtSigned(v.z, 2)}</td>
                    <td style={{ textAlign: "right" }}>{v.pct != null ? Math.round(v.pct) : "—"}</td>
                    <td style={{ textAlign: "right" }}>{dz == null ? "—" : fmtSigned(dz, 2)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {missing.length > 0 && (
          <p className="muted small">
            Not populated ({missing.length}): {missing.map((f) => factorLabel(f)).join(", ")} — dropped from this
            name's average, never imputed. {d.fund_as_of ? `Fundamentals as of ${d.fund_as_of} (statement date + reporting lag).` : "No fundamental statement available for this name."}
          </p>
        )}
        {d.fund_as_of && missing.length === 0 && (
          <p className="muted small">Fundamentals as of {d.fund_as_of} (statement date + reporting lag); price factors as of {dd.as_of}.</p>
        )}

        <div className="dd-para">
          <div className="row-between">
            <h3>Risks section draft</h3>
            <button className="dd-copy" onClick={copy}>{copied ? "Copied ✓" : "Copy"}</button>
          </div>
          <p className="small">{para}</p>
          <p className="muted small">Evidence, not a verdict: pair it with the fundamental thesis. Every number
            above is traceable to a formula (hover the factor names).</p>
        </div>

        <AnalystView ticker={ticker} d={d} bundle={bundle} />
      </aside>
    </>
  );
}

// ---------------------------------------------------------------------------
// Analyst override view: active overrides for this name + a form that DRAFTS a
// valid CSV row. Overrides never touch the score (docs/override-layer-design.md)
// — the site is static, so filing = appending the drafted row to
// data/overrides.csv and re-running the pipeline.
// ---------------------------------------------------------------------------
function AnalystView({ ticker, d, bundle }: { ticker: string; d: DrilldownName; bundle: Bundle }) {
  const active = (bundle.overrides?.active ?? []).filter((o) => o.ticker === ticker);
  const reasons = bundle.overrides?.reason_codes ?? [];
  const populated = Object.entries(d.factors).filter(([, v]) => v && v.z != null).map(([f]) => f);

  const [analyst, setAnalyst] = useState("");
  const [direction, setDirection] = useState<"less_risky" | "more_risky">("less_risky");
  const [reason, setReason] = useState(reasons[0] ?? "corporate_action");
  const [factor, setFactor] = useState("");
  const [note, setNote] = useState("");
  const [copied, setCopied] = useState(false);
  const [open, setOpen] = useState(false);

  const today = new Date().toISOString().slice(0, 10);
  const csvNote = `"${note.replace(/"/g, '""')}"`;
  const row = `${today},${ticker},${analyst || "?"},${direction},${reason},${factor},${csvNote},`;
  const valid = analyst.trim().length > 0 && note.trim().length > 0;

  const copyRow = async () => {
    try { await navigator.clipboard.writeText(row); setCopied(true); setTimeout(() => setCopied(false), 1600); }
    catch { /* clipboard unavailable */ }
  };

  return (
    <div className="dd-para">
      <div className="row-between">
        <h3>Analyst view</h3>
        <button className="copy-btn" onClick={() => setOpen(!open)}>{open ? "Close form" : "Add override"}</button>
      </div>
      {active.length ? active.map((o, i) => (
        <div key={i} className="ov-item">
          <span className={"flag-chip " + (o.direction === "less_risky" ? "ov-less" : "ov-more")}>
            {o.direction === "less_risky" ? "⚑ LESS RISKY" : "⚑ MORE RISKY"}</span>
          <span className="small"><b>{o.reason_code}</b>{o.factor ? <> · disputes <code>{o.factor}</code></> : null} — {o.note}</span>
          <span className="muted small"> ({o.analyst}, filed {o.date}, expires {o.expires})</span>
        </div>
      )) : <p className="muted small">No active overrides. The model's view stands unchallenged for this name.</p>}

      {open && (
        <div className="ov-form">
          <p className="muted small">
            Overrides are annotations — the score never changes. They expire (default two quarters) and are
            scored on the Validation tab: did the name behave your way or the model's? State what the model
            <em> cannot see</em>, not that you disagree with what it sees.
          </p>
          <div className="ov-grid">
            <label>Analyst<input value={analyst} onChange={(e) => setAnalyst(e.target.value)} placeholder="initials" /></label>
            <label>Direction
              <select value={direction} onChange={(e) => setDirection(e.target.value as any)}>
                <option value="less_risky">less risky than the model says</option>
                <option value="more_risky">more risky than the model says</option>
              </select>
            </label>
            <label>Reason
              <select value={reason} onChange={(e) => setReason(e.target.value)}>
                {reasons.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
            </label>
            <label>Disputed factor (optional)
              <select value={factor} onChange={(e) => setFactor(e.target.value)}>
                <option value="">—</option>
                {populated.map((f) => <option key={f} value={f}>{factorLabel(f)}</option>)}
              </select>
            </label>
          </div>
          <label className="ov-note">Why (what can't the model see?)
            <textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. OCF/NI distorted by the Q1 divestiture; cash conversion normal ex-item" />
          </label>
          <div className="row-between">
            <code className="ov-row">{row}</code>
            <button className="dd-copy" disabled={!valid} onClick={copyRow}>{copied ? "Copied ✓" : "Copy CSV row"}</button>
          </div>
          <p className="muted small">Append the row to <code>data/overrides.csv</code> and re-run
            <code> python main.py</code> — it will appear here and enter the scoreboard.</p>
        </div>
      )}
    </div>
  );
}

function formatRaw(f: string, v: number): string {
  const pctFactors = new Set(["roe", "roa", "gross_margin", "fcf_margin", "roe_yoy", "gross_margin_yoy",
                              "asset_growth_yoy", "net_issuance_yoy", "mom_12_1", "reversal_1m", "fcf_yield"]);
  if (pctFactors.has(f)) return (v * 100).toFixed(1) + "%";
  return v >= 100 ? v.toFixed(0) : v.toFixed(2);
}
