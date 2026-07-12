import { useMemo, useState } from "react";
import { Bundle, fmtSigned, decileColor } from "../lib/data";
import { DataTable } from "./DataTable";
import { Term } from "./Term";
import { Ticker } from "./TickerFlag";
import { ScoreRow } from "../lib/types";

// Default long only sleeve overlaid out of the box; user can paste their own.
const SAMPLE = [
  "TDS", "PRDO", "MCRI", "CVCO", "UNFI", "CRGY", "AX", "PFBC", "ENVA", "NEOG",
  "KRYS", "FSS", "GTES", "MYRG", "DOCN", "KLIC", "VIAV", "CE", "CTRE", "AVA",
].join(", ");

export function PortfolioOverlayView({ meta, scores }: Bundle) {
  const [text, setText] = useState(SAMPLE);
  const byTicker = useMemo(() => {
    const m = new Map<string, ScoreRow>();
    scores.forEach((r) => m.set(r.ticker.toUpperCase(), r));
    return m;
  }, [scores]);

  const tickers = text.split(/[\s,]+/).map((t) => t.trim().toUpperCase()).filter(Boolean);
  const held = tickers.map((t) => byTicker.get(t)).filter(Boolean) as ScoreRow[];
  const missing = tickers.filter((t) => !byTicker.has(t));
  const n = 10;

  const inWorst = held.filter((r) => r.decile === 10);
  const meanDecile = held.length ? held.reduce((a, r) => a + (r.decile ?? 0), 0) / held.length : 0;

  return (
    <div className="grid">
      <section className="card span-12">
        <h2>Portfolio overlay — where do my holdings sit on the sell model?</h2>
        <p className="muted">
          Paste your long only sleeve (tickers, any separator). Each holding is matched to its
          <Term id="sectorneutral"> sector neutral</Term> <Term id="decile">decile</Term> and
          <Term id="relativereturn"> relative risk</Term> score from the latest cross section. Holdings in the
          <strong> worst decile (10)</strong> are the ones the model says are most likely to underperform their
          sector peers over the next {meta.horizon_q}Q, the review or trim candidates.
        </p>
        <div className="help-note">
          <strong>What this tells you, and what it does not.</strong> Your holdings are matched to the same sector
          neutral ranking used everywhere else on the site. A holding in decile 10 is one the model considers a
          likely laggard against its sector peers over the next {meta.horizon_q} quarter(s), a prompt to review or
          trim rather than an automatic sell. Middle deciles are unremarkable, and deciles 1 to 3 look attractive
          relative to peers. The mean decile is a quick read on whether the whole sleeve leans cheap or rich on
          these signals. Keep in mind the score is <em>relative</em>: a decile 10 name can still rise in an up
          market, the model only expects it to rise less than its sector, so read this as a shortlist for a closer
          look, not a trade instruction.
        </div>
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} spellCheck={false} />
        <div className="overlay-summary">
          <span><strong>{held.length}</strong> matched</span>
          <span className={inWorst.length ? "neg" : "pos"}><strong>{inWorst.length}</strong> in worst decile</span>
          <span>mean decile <strong>{meanDecile.toFixed(1)}</strong> / {n}</span>
          {missing.length > 0 && <span className="muted">not in universe: {missing.join(", ")}</span>}
        </div>
      </section>

      <section className="card span-12">
        <h3>Holdings ranked by <Term id="relativereturn">relative risk</Term> score</h3>
        <DataTable<ScoreRow>
          rows={[...held].sort((a, b) => (b.score ?? -99) - (a.score ?? -99))}
          rowKey={(r) => r.ticker}
          columns={[
            { key: "ticker", label: "Ticker", render: (r) => <Ticker symbol={r.ticker} index={r.index_name} /> },
            { key: "gics_sector", label: "GICS Sector" },
            { key: "decile", label: "Decile", align: "right", render: (r) => (
              <span className="decile-pill" style={{ background: decileColor(r.decile, n) }}>{r.decile ?? "—"}</span>
            ) },
            { key: "score", label: "Score", align: "right", render: (r) => fmtSigned(r.score) },
            { key: "sell_rank", label: "Universe sell rank", align: "right", render: (r) => r.sell_rank ?? "—" },
            { key: "flag", label: "", render: (r) => r.decile === 10 ? <span className="badge fail">REVIEW</span> : "" },
          ]}
        />
      </section>
    </div>
  );
}
