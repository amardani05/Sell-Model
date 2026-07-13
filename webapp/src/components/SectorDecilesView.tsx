import { useState } from "react";
import { Bundle, fmtSigned, decileColor } from "../lib/data";
import { Plot } from "./Plot";
import { DataTable } from "./DataTable";
import { Term } from "./Term";
import { Ticker, UniverseToggle, inUniverse } from "./TickerFlag";
import { ScoreRow } from "../lib/types";

export function SectorDecilesView({ meta, scores, sectorDeciles }: Bundle) {
  const sectors = sectorDeciles.sectors;
  const n = sectorDeciles.n_deciles;
  const [sector, setSector] = useState<string>(sectors[0] ?? "");
  const [universe, setUniverse] = useState<string>(meta.selection_index ?? "S&P 600");

  const inU = scores.filter((r) => r.decile != null && inUniverse(r.index_name, universe));
  // heatmap z[sectorIdx][decileIdx] = count, computed client side so the
  // universe filter applies (deciles are cut per index, so counts stay exact).
  const z: number[][] = sectors.map((s) =>
    Array.from({ length: n }, (_, di) =>
      inU.filter((r) => r.gics_sector === s && r.decile === di + 1).length
    )
  );

  const inSector = inU
    .filter((r) => r.gics_sector === sector && r.score !== null)
    .sort((a, b) => (b.score ?? -99) - (a.score ?? -99));

  return (
    <div className="grid">
      <section className="card span-12">
        <div className="row-between">
          <h2><Term id="sectorneutral">Sector neutral</Term> decile map</h2>
          <UniverseToggle value={universe} onChange={setUniverse} counts={meta.index_counts} />
        </div>
        <p className="muted">
          <Term id="decile">Deciles</Term> are formed <strong>within each <Term id="gics">GICS</Term> sector and
          index at each date</strong> — S&amp;P 600 names against 600 peers only — so every sector contributes
          its own worst names and the model never just flags whole cheap or expensive sectors. Decile 1 = best
          expected relative return, decile {n} = the sell sleeve. Counts are the latest cross section for the
          <Term id="selectionuniverse"> selection universe</Term> shown in the toggle.
        </p>
        <div className="help-note">
          <strong>Why compare inside a sector.</strong> Whole sectors move together and trade at very different
          valuations, so a raw market wide ranking would mostly tell you that, say, software is pricier than
          banks. Ranking each name only against its own sector strips that out and asks the sharper question,
          which names look weak <em>relative to the companies they most resemble</em>. That is what makes the
          signal about the stock rather than about the sector it happens to sit in.
        </div>
        <div className="help-note">
          <strong>Reading the map.</strong> Each row is a sector and each column is a decile from best (1) to
          worst ({n}); darker cells hold more names. Because deciles are formed inside each sector, every row
          spreads its names across all ten columns, so no sector is entirely a buy or entirely a sell. Pick a
          sector below to see its names ranked, alongside the individual factor readings that drove each score,
          where a larger positive number is more unfavorable.
        </div>
        <Plot height={Math.max(280, sectors.length * 36)}
          data={[{
            type: "heatmap",
            x: Array.from({ length: n }, (_, i) => `D${i + 1}`),
            y: sectors,
            z,
            colorscale: [[0, "#f3f6f9"], [1, "#34516b"]],
            showscale: true,
            hovertemplate: "%{y}<br>%{x}: %{z} names<extra></extra>",
          }]}
          layout={{ xaxis: { title: "sector neutral decile" }, yaxis: { automargin: true } }} />
      </section>

      <section className="card span-12">
        <div className="row-between">
          <h3>Names by sector</h3>
          <select value={sector} onChange={(e) => setSector(e.target.value)}>
            {sectors.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <DataTable<ScoreRow>
          rows={inSector}
          rowKey={(r) => r.ticker}
          columns={[
            { key: "ticker", label: "Ticker", render: (r) => <Ticker symbol={r.ticker} index={r.index_name} /> },
            { key: "decile", label: "Decile", align: "right", render: (r) => (
              <span className="decile-pill" style={{ background: decileColor(r.decile, n) }}>{r.decile ?? "—"}</span>
            ) },
            { key: "score", label: <Term id="relativereturn">Relative risk score</Term>, align: "right", render: (r) => fmtSigned(r.score) },
            { key: "mom_12_1__n", label: <Term id="momentum">Momentum</Term>, align: "right", render: (r) => fmtSigned(r["mom_12_1__n"] as number) },
            { key: "pe_ratio__n", label: <Term id="pe">Valuation P/E</Term>, align: "right", render: (r) => fmtSigned(r["pe_ratio__n"] as number) },
            { key: "accruals_ocf_ni__n", label: <Term id="accruals">Accruals</Term>, align: "right", render: (r) => fmtSigned(r["accruals_ocf_ni__n"] as number) },
          ]}
        />
      </section>
    </div>
  );
}
