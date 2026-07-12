// Small badge indicating whether a name is an S&P 600 (SmallCap) or S&P 400
// (MidCap) constituent. The S&P 400 is unioned into the universe so names that
// graduated up out of the 600 are still scored; the flag makes that visible.

export function TickerFlag({ index }: { index?: string | null }) {
  const is600 = index === "S&P 600";
  const is400 = index === "S&P 400";
  if (!is600 && !is400) return null;
  return (
    <span
      className={"idx-flag " + (is600 ? "idx-600" : "idx-400")}
      title={is600 ? "S&P SmallCap 600 constituent" : "S&P MidCap 400 constituent"}
    >
      {is600 ? "600" : "400"}
    </span>
  );
}

// Ticker cell = symbol plus its index flag, used in every table with a ticker.
export function Ticker({ symbol, index }: { symbol: string; index?: string | null }) {
  return (
    <span className="ticker-cell">
      <strong>{symbol}</strong>
      <TickerFlag index={index} />
    </span>
  );
}
