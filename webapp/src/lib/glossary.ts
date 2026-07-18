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
  ridge: {
    label: "ridge regression",
    def: "A linear regression with a penalty on large coefficients. The penalty shrinks every factor weight toward zero, so a factor only earns influence by predicting consistently; this is the standard guard against overfitting in linear models.",
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
    def: "Whether higher scores really did earn worse relative returns. Score buckets are cut within each quarter, then the per bucket outcomes are averaged across quarters with error bars, so no single period or outlier decides the curve.",
  },
  reliability: {
    label: "reliability curve",
    def: "For each score bucket, the fraction of names that actually underperformed their sector median. It turns the score into a probability statement: decile 10 names trailed their sector X percent of the time.",
  },
  eventstudy: {
    label: "event study",
    def: "Track what happened in the quarters AFTER a name entered the worst decile: its average sector relative return 1, 2, 3, 4 quarters later. The clearest picture of what a flag has historically meant.",
  },
  standarderror: {
    label: "standard error",
    def: "How uncertain an average is. A band of about two standard errors around a point is the range where the true value plausibly sits; if the band includes zero, the result may be noise.",
  },
  winsorizedmean: {
    label: "winsorized mean",
    def: "An average computed after clipping the most extreme values (here the top and bottom 1 percent). If the plain mean and the winsorized mean disagree sharply, a few outliers were carrying the plain mean.",
  },
  coveragera: {
    label: "coverage era",
    def: "The data source only provides recent fundamentals, so older cross sections were scored by the two price factors alone. History splits into a price only era and a full factor era, and stats are reported per era so a 2 factor past is never passed off as evidence about the 15 factor model.",
  },
  montecarlo: {
    label: "Monte Carlo simulation",
    def: "Instead of one simulated portfolio (which is mostly luck at 20 names), draw thousands of random portfolios under each screening rule and compare the whole distributions of outcomes.",
  },
  trackingerror: {
    label: "tracking error",
    def: "The annualized volatility of the return DIFFERENCE between a strategy and its base portfolio. Together with the excess return it gives the information ratio of the screen itself.",
  },
  splice: {
    label: "splice artifact",
    def: "A data error where two different securities are joined under one ticker (for example a bankruptcy emergence), creating a fake giant one day return. Flagged windows are excluded from labels and logged, never used.",
  },
  transitionmatrix: {
    label: "transition matrix",
    def: "For names in decile X this quarter, where did they land next quarter? Row 10 shows how sticky the sell flag is: a flag that immediately melts away means something different from one that persists.",
  },
  baserate: {
    label: "base rate",
    def: "The historical frequency of an outcome, for example how often decile 10 names went on to trail their sector. Research notes should cite base rates only once there is enough full factor history to estimate them honestly.",
  },
  horizon: {
    label: "forward horizon",
    def: "How far ahead the label looks. 1Q judges every score by the stock's sector relative return over the NEXT quarter; 2Q over the next two quarters. The toggle recomputes the page at the other horizon. Slower signals like value and quality often need the longer window to pay off.",
  },
  familybalanced: {
    label: "family balanced",
    def: "Factors are averaged within their family first (valuation, momentum, volatility, quality, investment, earnings quality), then the family scores are averaged. Four overlapping valuation ratios cast one vote, not four, and adding more price factors can never let price signals swamp the fundamentals.",
  },
  selectionuniverse: {
    label: "selection universe",
    def: "The S&P 600, the index IMA actually picks from. S&P 400 graduates stay scored for monitoring, but they are ranked against 400 peers only and every headline statistic (IC, calibration, backtest, simulation) is computed on the 600 alone.",
  },
  overlapping: {
    label: "overlapping observations",
    def: "Scoring monthly while the label looks a quarter ahead means adjacent observations share part of the same forward window. That is legitimate (it is the standard construction) as long as the t statistic corrects for the overlap, which the Newey West lags here do.",
  },
  ivol: {
    label: "idiosyncratic volatility",
    def: "The part of a stock's daily wiggle that the market cannot explain. High IVOL names have historically gone on to underperform (the volatility puzzle), and they are also the hardest names to hold with conviction.",
  },
  maxeffect: {
    label: "MAX effect",
    def: "Stocks with a recent huge single day gain attract lottery seeking buyers and then tend to disappoint. Measured as the biggest daily return over the last month.",
  },
  beta: {
    label: "beta",
    def: "How much a stock moves per unit of market move. High beta names have historically delivered poor risk adjusted returns (betting against beta).",
  },
  high52w: {
    label: "52 week high",
    def: "Price as a fraction of the trailing one year high. Names far below their high have tended to keep lagging peers; names near the high tend to keep performing.",
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
