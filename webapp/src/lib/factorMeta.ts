// Human readable metadata for every factor: what it measures, the exact
// formula the pipeline computes, and which direction is the red flag.
// This is the transparency contract behind the per name drill down: an analyst
// must be able to answer "why is this name flagged" without reading Python.

export interface FactorMeta {
  label: string;          // short display name
  family: string;
  formula: string;        // the actual computation, plain notation
  redFlag: string;        // which direction is unfavorable, in words
  anomaly: string;        // the documented effect behind it
}

export const FACTOR_META: Record<string, FactorMeta> = {
  pe_ratio: {
    label: "P/E (trailing)", family: "Valuation",
    formula: "market cap ÷ trailing 12m net income (only when income > 0)",
    redFlag: "High P/E vs sector peers: priced richly",
    anomaly: "Value premium (Fama French HML)",
  },
  ev_to_ebitda: {
    label: "EV / EBITDA", family: "Valuation",
    formula: "(market cap + total debt − cash) ÷ trailing 12m EBITDA",
    redFlag: "High EV/EBITDA vs sector peers: priced richly",
    anomaly: "Value premium (enterprise value form)",
  },
  ps_ratio: {
    label: "Price / Sales", family: "Valuation",
    formula: "market cap ÷ trailing 12m revenue",
    redFlag: "High P/S vs sector peers: priced richly",
    anomaly: "Value premium (works when earnings are noisy)",
  },
  fcf_yield: {
    label: "FCF yield", family: "Valuation",
    formula: "(operating cash flow − capex, trailing 12m) ÷ enterprise value",
    redFlag: "LOW free cash flow yield vs sector peers",
    anomaly: "Cash flow yield / value premium",
  },
  mom_12_1: {
    label: "12−1 momentum", family: "Momentum",
    formula: "total return from 12 months ago to 1 month ago (skips the last month)",
    redFlag: "LOW momentum vs sector peers: a persistent laggard",
    anomaly: "Jegadeesh Titman momentum (losers keep losing)",
  },
  reversal_1m: {
    label: "1m reversal", family: "Momentum",
    formula: "total return over the most recent ~21 trading days",
    redFlag: "HIGH last month return: recent pops tend to give some back",
    anomaly: "Short term reversal effect",
  },
  high_52w: {
    label: "52 week high proximity", family: "Momentum",
    formula: "price ÷ trailing 252 day maximum price",
    redFlag: "FAR below the 52 week high: beaten down names keep lagging",
    anomaly: "52 week high effect (George & Hwang 2004)",
  },
  ivol_63d: {
    label: "Idiosyncratic volatility", family: "Volatility",
    formula: "std of daily return residuals vs the benchmark, trailing ~63 days",
    redFlag: "HIGH stock specific volatility vs sector peers",
    anomaly: "IVOL puzzle (Ang, Hodrick, Xing, Zhang 2006)",
  },
  max_ret_1m: {
    label: "MAX (lottery)", family: "Volatility",
    formula: "largest single day return over the trailing ~21 days",
    redFlag: "HIGH recent single day pop: lottery like names disappoint",
    anomaly: "MAX effect (Bali, Cakici, Whitelaw 2011)",
  },
  beta_252d: {
    label: "Market beta", family: "Volatility",
    formula: "rolling 252 day beta of daily returns vs the benchmark",
    redFlag: "HIGH beta vs sector peers",
    anomaly: "Betting against beta (Frazzini & Pedersen 2014)",
  },
  roe: {
    label: "ROE", family: "Quality",
    formula: "trailing 12m net income ÷ shareholders' equity",
    redFlag: "LOW return on equity vs sector peers",
    anomaly: "Profitability premium (Novy Marx, RMW)",
  },
  roa: {
    label: "ROA", family: "Quality",
    formula: "trailing 12m net income ÷ total assets",
    redFlag: "LOW return on assets vs sector peers",
    anomaly: "Profitability premium",
  },
  gross_margin: {
    label: "Gross margin", family: "Quality",
    formula: "trailing 12m gross profit ÷ revenue",
    redFlag: "LOW gross margin vs sector peers",
    anomaly: "Gross profitability (Novy Marx)",
  },
  fcf_margin: {
    label: "FCF margin", family: "Quality",
    formula: "trailing 12m free cash flow ÷ revenue",
    redFlag: "LOW free cash flow margin vs sector peers",
    anomaly: "Cash profitability",
  },
  roe_yoy: {
    label: "ROE trend (YoY)", family: "Quality",
    formula: "ROE this quarter − ROE four quarters ago",
    redFlag: "DECLINING profitability year over year",
    anomaly: "Deteriorating fundamentals precede underperformance",
  },
  gross_margin_yoy: {
    label: "Gross margin trend (YoY)", family: "Quality",
    formula: "gross margin this quarter − gross margin four quarters ago",
    redFlag: "DECLINING gross margin year over year",
    anomaly: "Margin erosion precedes underperformance",
  },
  asset_growth_yoy: {
    label: "Asset growth (YoY)", family: "Investment",
    formula: "total assets ÷ total assets four quarters ago − 1",
    redFlag: "HIGH asset growth: aggressive expansion / empire building",
    anomaly: "Asset growth anomaly (Cooper Gulen Schill)",
  },
  net_issuance_yoy: {
    label: "Net share issuance (YoY)", family: "Investment",
    formula: "shares outstanding ÷ shares four quarters ago − 1",
    redFlag: "HIGH issuance: dilution of existing holders",
    anomaly: "Net issuance anomaly (Daniel Titman, Pontiff Woodgate)",
  },
  accruals_ocf_ni: {
    label: "Accruals (OCF/NI)", family: "Earnings Quality",
    formula: "trailing 12m operating cash flow ÷ trailing 12m net income",
    redFlag: "LOW OCF/NI: earnings not backed by cash (high accruals)",
    anomaly: "Sloan (1996) accruals anomaly",
  },
  short_vol_ratio: {
    label: "Short volume share (3m)", family: "Short Activity",
    formula: "trailing 63 trading day mean of (daily short sale volume ÷ total volume), FINRA Reg SHO consolidated off exchange file, history from Oct 2018",
    redFlag: "HIGH share of trading sold short: heavy shorting flow tends to precede underperformance",
    anomaly: "Informed shorting flow (Boehmer, Jones and Zhang 2008)",
  },
  short_vol_chg: {
    label: "Short volume share change (3m)", family: "Short Activity",
    formula: "current 63 day mean short volume share minus the same mean 63 trading days earlier",
    redFlag: "RISING shorting activity versus the prior quarter",
    anomaly: "Daily shorting activity predicts weak returns (Diether, Lee and Werner 2009)",
  },
  insider_npr_6m: {
    label: "Insider net purchase ratio (6m)", family: "Insider Activity",
    formula: "(insider open market buy shares − sell shares) ÷ (buys + sells), trailing 126 sessions, from the SEC Form 4 data sets (plan flagged trades excluded; stamped by filing date)",
    redFlag: "NET SELLING by insiders: purchases are the informative side, so a low or negative ratio flags risk",
    anomaly: "Insider trading predicts returns, strongest in small caps (Lakonishok and Lee 2001)",
  },
  earn_react_1q: {
    label: "Earnings reaction (latest print)", family: "Earnings Surprise",
    formula: "benchmark adjusted return from the close before to the close after the latest earnings 8-K reaction day (item 2.02 from EDGAR; the value expires 70 sessions after the print)",
    redFlag: "WEAK or negative market reaction to the latest print: bad surprises drift further down",
    anomaly: "Post earnings announcement drift (Bernard and Thomas 1989); the free SUE proxy",
  },
  est_revision_3m: {
    label: "Estimate revision (3m)", family: "Estimates",
    formula: "3 month change in consensus forward EPS (gated source)",
    redFlag: "DOWNWARD revisions",
    anomaly: "Post revision drift",
  },
  sue: {
    label: "SUE", family: "Estimates",
    formula: "(actual EPS − consensus) ÷ std of surprises (gated source)",
    redFlag: "LOW / negative earnings surprise",
    anomaly: "Post earnings announcement drift",
  },
};

// Family display order + colors shared with the Factor IC tab.
export const FAMILY_COLOR: Record<string, string> = {
  Valuation: "#4e79a7", Momentum: "#f28e2b", Volatility: "#17becf",
  Quality: "#59a14f", Investment: "#b07aa1", "Earnings Quality": "#e15759",
  "Short Activity": "#8c564b", "Insider Activity": "#e377c2",
  "Earnings Surprise": "#bcbd22", Estimates: "#9c755f",
};

export function factorLabel(f: string): string {
  return FACTOR_META[f]?.label ?? f;
}
