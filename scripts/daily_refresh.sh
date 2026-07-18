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

if "$PY" main.py >> "$LOG" 2>&1; then
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
    echo "=== DEPLOY FAILED $(date); data committed locally ===" >> "$LOG"
    exit 1
  fi
else
  echo "=== PIPELINE FAILED $(date); site keeps previous data ===" >> "$LOG"
  exit 1
fi
