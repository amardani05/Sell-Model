import { useEffect, useState } from "react";
import { Bundle, loadAll } from "./lib/data";
import { Overview } from "./components/Overview";
import { SectorDecilesView } from "./components/SectorDecilesView";
import { TorpedoView } from "./components/TorpedoView";
import { FactorICView } from "./components/FactorICView";
import { ValidationBacktestView } from "./components/ValidationBacktestView";
import { PortfolioOverlayView } from "./components/PortfolioOverlayView";
import { MethodologyView } from "./components/MethodologyView";
import { DrillDownProvider } from "./components/DrillDown";

type Tab = "overview" | "sectors" | "torpedo" | "factors" | "validation" | "portfolio" | "methodology";

const TABS: { key: Tab; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "portfolio", label: "Portfolio Overlay" },
  { key: "torpedo", label: "Torpedo Screener" },
  { key: "validation", label: "Validation / Backtest" },
  { key: "sectors", label: "Sector Deciles" },
  { key: "factors", label: "Factor IC" },
  { key: "methodology", label: "Methodology" },
];

export default function App() {
  const [data, setData] = useState<Bundle | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("overview");

  useEffect(() => {
    loadAll().then(setData).catch((e) => setErr(String(e)));
  }, []);

  if (err) {
    return (
      <div className="app">
        <header className="top-bar"><h1>Relative Sell Model</h1></header>
        <div className="content">
          <div className="card error">
            <strong>Failed to load pipeline data.</strong>
            <p>{err}</p>
            <p className="muted">
              Run <code>python main.py</code> (or <code>python main.py --synthetic</code>) from
              the repo root first, then reload. The dashboard reads
              <code>webapp/public/data/*.json</code>, populated by the <code>webapp_export</code> step.
            </p>
          </div>
        </div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="app">
        <header className="top-bar"><h1>Relative Sell Model</h1></header>
        <div className="loading">Loading pipeline data…</div>
      </div>
    );
  }

  const m = data.meta;
  return (
    <div className="app">
      <header className="top-bar">
        <div>
          <h1>Relative Sell Model</h1>
          <span className="tagline">Sector neutral ranking of expected <em>relative underperformance</em> · S&amp;P 600 + 400</span>
        </div>
        <span className="sub">
          {m.universe_size} names ({m.n_selection ?? "?"} in the {m.selection_index ?? "S&P 600"} selection universe) ·
          {" "}{m.n_sectors} sectors · {m.n_cross_sections} {m.rebalance_freq === "M" ? "monthly" : "quarterly"} cross sections ·
          horizon {m.horizon_q}Q · source <code>{m.source}</code> ·
          default score <code>{m.default_score}</code> ·
          generated {new Date(m.generated_at).toLocaleString()}
          <br />
          <span className="idx-legend">
            <span><span className="idx-flag idx-600">600</span> S&amp;P SmallCap 600{m.index_counts?.["S&P 600"] ? ` (${m.index_counts["S&P 600"]})` : ""}</span>
            <span><span className="idx-flag idx-400">400</span> S&amp;P MidCap 400{m.index_counts?.["S&P 400"] ? ` (${m.index_counts["S&P 400"]})` : ""}</span>
          </span>
        </span>
      </header>

      {!m.membership_point_in_time && (
        <div className="banner warn">
          ⚠ Universe is a <strong>current only</strong> membership snapshot (no point in time store):
          cross sections before today carry survivorship bias and backtest history is optimistic.
          Drop a true point in time export into <code>data/sp600_membership.csv</code> to fix.
        </div>
      )}

      <nav className="nav">
        {TABS.map((t) => (
          <button key={t.key} className={tab === t.key ? "active" : ""} onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </nav>

      <main className="content">
        <DrillDownProvider bundle={data}>
          {tab === "overview" && <Overview {...data} />}
          {tab === "sectors" && <SectorDecilesView {...data} />}
          {tab === "torpedo" && <TorpedoView {...data} />}
          {tab === "factors" && <FactorICView {...data} />}
          {tab === "validation" && <ValidationBacktestView {...data} />}
          {tab === "portfolio" && <PortfolioOverlayView {...data} />}
          {tab === "methodology" && <MethodologyView {...data} />}
        </DrillDownProvider>
      </main>
    </div>
  );
}
