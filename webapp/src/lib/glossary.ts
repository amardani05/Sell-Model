// Definitions surfaced on hover across the platform. Keep every definition
// hyphen free and plain enough to read in a tooltip.
export interface GlossaryEntry { label: string; def: string; }

export const GLOSSARY: Record<string, GlossaryEntry> = {
  ic: {
    label: "IC",
    def: "Information Coefficient. The rank correlation between the model score and the return that actually followed. We sign it so that positive means skill. 0 means no predictive power.",
  },
  ir: {
    label: "IR",
    def: "Information Ratio. The mean IC divided by how much the IC bounces around period to period. Higher means the edge is more consistent, not just large on average.",
  },
  famamacbeth: {
    label: "Fama MacBeth",
    def: "A way to average a statistic across many time periods and get a t statistic on the average. Here we measure the IC in each quarter, then average those quarterly ICs.",
  },
  neweywest: {
    label: "Newey West",
    def: "A correction to the t statistic that stays honest when nearby periods are correlated. We allow for 5 quarters of overlap.",
  },
  tstat: {
    label: "t statistic",
    def: "How many standard errors the estimate sits above zero. Roughly above 2 is the usual bar for statistically convincing.",
  },
  spearman: {
    label: "Spearman correlation",
    def: "A correlation based on ranks rather than raw values, so it is not thrown off by a few extreme numbers.",
  },
  decile: {
    label: "decile",
    def: "One of ten equal size buckets. Here names are split into deciles inside each sector by score: decile 1 is the best expected relative return, decile 10 is the sell sleeve.",
  },
  sectorneutral: {
    label: "sector neutral",
    def: "Every comparison is made only among peers in the same GICS sector, so the ranking is not just flagging whole cheap or expensive sectors.",
  },
  relativereturn: {
    label: "relative return",
    def: "A stock return minus the median return of its sector peers over the same window. This is the target the sell model is built to rank.",
  },
  equalweight: {
    label: "equal weight composite",
    def: "The baseline score: the plain average of the direction aligned sector neutral factors, giving each factor the same weight.",
  },
  learnedweight: {
    label: "learned weight",
    def: "An optional model (ridge, logistic, or gradient boosted trees) that fits factor weights from history. It only becomes the default if it beats the equal weight baseline out of sample.",
  },
  walkforward: {
    label: "walk forward",
    def: "Training only on data before each prediction date and never after, so the test never peeks at the future.",
  },
  oos: {
    label: "out of sample",
    def: "Measured on data the model was not trained on. In sample results flatter the model; out of sample is the honest test.",
  },
  placebo: {
    label: "placebo test",
    def: "Shuffle the scores within each date and re measure the IC. A real edge collapses toward zero under the shuffle. If it survives, the edge was an artifact.",
  },
  lookahead: {
    label: "look ahead",
    def: "Accidentally using information that was not knowable yet at the time. We assert the factors do not change when future data is removed.",
  },
  survivorship: {
    label: "survivorship bias",
    def: "The distortion from only studying names that survived to today. Delisted or acquired names must be kept, or backtests look better than reality.",
  },
  pointintime: {
    label: "point in time",
    def: "Using the universe and data exactly as they were on each historical date, not as they look today.",
  },
  delistingaware: {
    label: "delisting aware",
    def: "A name that stops trading during the forward window is carried to its terminal value (about minus 100 percent), the strongest possible underperformer, rather than dropped.",
  },
  sharpe: {
    label: "Sharpe ratio",
    def: "Annualized return divided by annualized volatility. A rough measure of return earned per unit of risk taken.",
  },
  cagr: {
    label: "CAGR",
    def: "Compound Annual Growth Rate. The single annual growth rate that would produce the observed total return.",
  },
  maxdd: {
    label: "max drawdown",
    def: "The worst peak to trough loss along the equity curve. A gut check on how painful the strategy got.",
  },
  turnover: {
    label: "turnover",
    def: "How much of the portfolio is traded at each rebalance. Higher turnover means more transaction cost.",
  },
  hitrate: {
    label: "hit rate",
    def: "The fraction of periods the metric was positive (for IC, the share of quarters with a positive IC).",
  },
  monotonicity: {
    label: "monotonicity",
    def: "Whether the deciles line up in order. A good sell model slopes down: higher sell decile means lower realized relative return. Reported as a rank correlation near minus 1.",
  },
  calibration: {
    label: "calibration",
    def: "Whether higher scores really did earn worse relative returns, checked by bucketing names by score and reading off the average outcome.",
  },
  winsorize: {
    label: "winsorize",
    def: "Clip extreme values to a high and low percentile before scoring, so a single outlier does not dominate.",
  },
  zscore: {
    label: "z score",
    def: "Value minus the group average, divided by the group standard deviation. It puts every factor on a common scale.",
  },
  pe: { label: "P/E", def: "Price to Earnings. Share price divided by earnings per share. High can mean richly valued." },
  evebitda: { label: "EV/EBITDA", def: "Enterprise Value to EBITDA. A valuation multiple that accounts for debt and cash. High can mean expensive." },
  ps: { label: "P/S", def: "Price to Sales. Market value divided by revenue. Useful when earnings are noisy or negative." },
  fcfyield: { label: "FCF yield", def: "Free Cash Flow divided by enterprise value. Low free cash flow yield is the red flag here." },
  momentum: { label: "12 minus 1 momentum", def: "Total return over the past twelve months excluding the most recent month. Persistent losers tend to keep lagging." },
  reversal: { label: "short term reversal", def: "The most recent one month return, kept separately because very recent winners often give some back next." },
  roe: { label: "ROE", def: "Return on Equity. Profit relative to shareholder equity. Low or falling is a quality red flag." },
  roa: { label: "ROA", def: "Return on Assets. Profit relative to total assets." },
  grossmargin: { label: "gross margin", def: "Gross profit divided by revenue. Falling margins can signal deteriorating economics." },
  fcfmargin: { label: "FCF margin", def: "Free cash flow divided by revenue." },
  assetgrowth: { label: "asset growth", def: "Year over year growth in total assets. Aggressive asset growth tends to precede weaker returns (the asset growth anomaly)." },
  netissuance: { label: "net issuance", def: "Year over year growth in shares outstanding. Heavy issuance dilutes holders and tends to precede weaker returns." },
  accruals: { label: "accruals", def: "Here measured as operating cash flow divided by net income. Low values mean earnings are not backed by cash (the Sloan accruals effect)." },
  sue: { label: "SUE", def: "Standardized Unexpected Earnings. How far actual earnings landed from expectations, scaled by their variability. Gated off unless a real estimate source is wired in." },
  estrevision: { label: "estimate revision", def: "The change in analyst forward earnings estimates. Downgrades are the red flag. Gated off unless a real estimate source is wired in." },
  shortinterest: { label: "short interest", def: "Short percent of float: the share of tradable stock currently sold short. Crowded shorts can flag blow up risk." },
  gics: { label: "GICS", def: "Global Industry Classification Standard. The sector taxonomy used to define peer groups." },
  torpedo: { label: "torpedo screener", def: "The absolute risk view. It ranks a name against the whole universe (not its sector) and targets blow up or drawdown risk, the opposite framing to the sector neutral sell model." },
  absoluterisk: { label: "absolute risk", def: "Risk measured against the entire universe, so whole sectors can screen as risky together. Contrast with sector relative risk." },
  percentile: { label: "percentile", def: "A rank from 0 to 100. A torpedo percentile of 90 means riskier than 90 percent of the universe." },
  tier: { label: "tier", def: "A coarse label on top of the percentile: Stable (0 to 30), Mainstream (30 to 70), Elevated (70 to 100)." },
  benchmark: { label: "benchmark", def: "IJR, the iShares S&P Small Cap 600 ETF, the long only yardstick for the avoid the worst sleeve." },
};
