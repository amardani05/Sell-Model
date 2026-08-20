#!/bin/zsh
# Unattended daily refresh for the Relative Sell Model.
#
# Run by launchd every weekday morning (see scripts/com.ima.sellmodel.daily.plist):
#   1. full pipeline run (fresh caches, ~30 minutes)
#   2. on success: commit the regenerated dashboard data (data files only,
#      never source code), best effort push, deploy to Vercel production
#   3. on failure: log and stop; the site keeps yesterday's data
#
# Everything is logged to output/daily/refresh_YYYYMMDD_HHMM.log. A lock
# directory prevents overlapping runs (e.g. a laptop waking twice).

set -u
REPO="/Users/amardani/Sell-Model"
PY="/Users/amardani/anaconda3/bin/python3"
VERCEL="/Users/amardani/.npm-global/bin/vercel"
LOG_DIR="$REPO/output/daily"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/refresh_$(date +%Y%m%d_%H%M).log"
LOCK="/tmp/ima_sellmodel_daily.lock"

if ! mkdir "$LOCK" 2>/dev/null; then
  echo "$(date) another refresh is already running; exiting" >> "$LOG"
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

cd "$REPO" || exit 1
echo "=== daily refresh started $(date) ===" >> "$LOG"

# NETWORK PREFLIGHT (added after the 2026-07-20 incident): launchd fires on
# wake before WiFi and DNS are up, and a pipeline started without network
# fetches a gutted universe. Wait up to 10 minutes for real DNS resolution;
# abort (keeping yesterday's site data) if it never comes.
NET_OK=0
for i in $(seq 1 30); do
  if /usr/bin/curl -s --max-time 5 "https://query2.finance.yahoo.com/" >/dev/null 2>&1; then
    NET_OK=1; break
  fi
  echo "network not ready (attempt $i/30); sleeping 20s" >> "$LOG"
  sleep 20
done
if [ "$NET_OK" -ne 1 ]; then
  echo "=== NO NETWORK after 10 minutes $(date); aborting, site keeps previous data ===" >> "$LOG"
  exit 1
fi

# Normal runs top up the price cache with a short recent window. Once a week
# (Monday) do a full rebuild as a safety net: incremental merges already
# reconcile split and dividend adjustments, but a periodic clean pull removes
# any chance of drift accumulating unnoticed. Re downloading 16 years EVERY
# day is what got this job rate limited into a month of stale data.
REFRESH_FLAG=""
if [ "$(date +%u)" -eq 1 ]; then
  REFRESH_FLAG="--refresh"
  echo "Monday: full price history rebuild (--refresh)" >> "$LOG"
fi

if "$PY" main.py $REFRESH_FLAG >> "$LOG" 2>&1; then
  STATUS="OK"
  echo "--- pipeline OK, committing data $(date) ---" >> "$LOG"
  git add webapp/public data/promotion_state.json data/insider_quarters.json >> "$LOG" 2>&1
  if ! git diff --cached --quiet; then
    git commit -m "Daily data refresh $(date +%Y-%m-%d)" >> "$LOG" 2>&1
    git push origin main >> "$LOG" 2>&1 \
      || echo "push failed (credentials?); commit stays local" >> "$LOG"
  else
    echo "no data changes to commit" >> "$LOG"
  fi
  cd "$REPO/webapp" || exit 1
  if "$VERCEL" --prod --yes >> "$LOG" 2>&1; then
    echo "=== DEPLOYED OK $(date) ===" >> "$LOG"
  else
    STATUS="DEPLOY FAILED"
    echo "=== DEPLOY FAILED $(date); data committed locally ===" >> "$LOG"
  fi
  cd "$REPO" || exit 1
else
  STATUS="PIPELINE FAILED"
  echo "=== PIPELINE FAILED $(date); site keeps previous data ===" >> "$LOG"
fi

# ---------------------------------------------------------------------------
# Prepend a summary block so one glance at the top of the log answers the only
# question that matters: did the prices actually move? (Added 2026-08-20 after
# a month of runs that "succeeded" every morning while silently rebuilding on
# July prices.)
# ---------------------------------------------------------------------------
SUMMARY_LINE=$(grep -m1 "^RUN SUMMARY:" "$LOG" 2>/dev/null)
STALE_LINE=$(grep -m1 "price data ends" "$LOG" 2>/dev/null)
INCR_LINE=$(grep -m1 "Incremental price refresh: [0-9]* new trading days" "$LOG" 2>/dev/null)
DEGRADED=$(grep -c "PRICE REFRESH DEGRADED\|PRICE DOWNLOAD DEGRADED\|PRICE REFRESH FAILED" "$LOG" 2>/dev/null)
{
  echo "========================================================================"
  echo "RUN $(date '+%Y-%m-%d %H:%M')  STATUS: ${STATUS}${REFRESH_FLAG:+ (full rebuild)}"
  [ -n "$SUMMARY_LINE" ] && echo "$SUMMARY_LINE"
  [ -n "$INCR_LINE" ]    && echo "PRICES: ${INCR_LINE#*INFO }"
  [ "$DEGRADED" -gt 0 ]  && echo "WARNING: price fetch was degraded ${DEGRADED}x; cache kept, see below"
  [ -n "$STALE_LINE" ]   && echo "ABORTED ON STALE PRICES: ${STALE_LINE#*StalePriceData: }"
  echo "========================================================================"
  echo
  cat "$LOG"
} > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"

if [ "$STATUS" != "OK" ]; then
  exit 1
fi
