#!/bin/zsh
# Alert channel for the unattended daily refresh.
#
# Why this exists: the refresh has now failed silently twice for weeks at a
# time (2026-07-20 to 09-16, descriptor limit; 2026-10-09 to 10-28, expired
# Vercel token). Both were written plainly at the top of every log and nobody
# reads logs. A failure has to reach a human somewhere other than the site,
# because a deploy failure means the site itself cannot report it.
#
# Usage: notify.sh "subject" "body"
# Sends mail via SMTP using credentials in .env (never committed). If those
# are absent or the send fails, it falls back to a macOS desktop notification
# so an alert is never silently dropped. Exit status is always 0: alerting
# must never be the thing that fails a healthy run.
set -u
REPO="/Users/amardani/Sell-Model"
ENV_FILE="$REPO/.env"
SUBJECT="${1:-Sell Model}"
BODY="${2:-}"

# Read one key from .env without sourcing it: values can contain spaces,
# quotes and '#', and sourcing arbitrary lines in a cron context is asking
# for trouble.
envget() {
  [ -f "$ENV_FILE" ] || return 0
  sed -n "s/^[[:space:]]*$1=//p" "$ENV_FILE" | head -1 | sed 's/^"//; s/"$//'
}

SMTP_HOST=$(envget SMTP_HOST)
SMTP_PORT=$(envget SMTP_PORT)
SMTP_USER=$(envget SMTP_USER)
SMTP_PASS=$(envget SMTP_PASS)
ALERT_TO=$(envget ALERT_TO)
ALERT_FROM=$(envget ALERT_FROM)
[ -n "$SMTP_PORT" ]  || SMTP_PORT=587
[ -n "$ALERT_FROM" ] || ALERT_FROM="$SMTP_USER"
[ -n "$ALERT_TO" ]   || ALERT_TO="$SMTP_USER"

if [ -n "$SMTP_HOST" ] && [ -n "$SMTP_USER" ] && [ -n "$SMTP_PASS" ] && [ -n "$ALERT_TO" ]; then
  MSG=$(mktemp); CFG=$(mktemp)
  chmod 600 "$CFG"
  # Credentials go in a 0600 config file, not on the command line, so they
  # never show up in `ps` output.
  printf 'user = "%s:%s"\n' "$SMTP_USER" "$SMTP_PASS" > "$CFG"
  {
    printf 'From: Sell Model <%s>\n' "$ALERT_FROM"
    printf 'To: %s\n' "$ALERT_TO"
    printf 'Subject: %s\n' "$SUBJECT"
    printf 'Content-Type: text/plain; charset=utf-8\n'
    printf 'X-Mailer: sellmodel-notify\n\n'
    printf '%s\n' "$BODY"
  } > "$MSG"
  if /usr/bin/curl -sS --ssl-reqd --max-time 45 \
        --url "smtp://${SMTP_HOST}:${SMTP_PORT}" \
        --config "$CFG" \
        --mail-from "$ALERT_FROM" --mail-rcpt "$ALERT_TO" \
        --upload-file "$MSG"; then
    rm -f "$MSG" "$CFG"
    echo "notify: emailed $ALERT_TO"
    exit 0
  fi
  rm -f "$MSG" "$CFG"
  echo "notify: SMTP send FAILED, falling back to a desktop notification"
else
  echo "notify: no SMTP credentials in .env, using a desktop notification"
fi

/usr/bin/osascript -e "display notification \"${SUBJECT//\"/}\" with title \"Relative Sell Model\" sound name \"Basso\"" 2>/dev/null \
  && echo "notify: desktop notification shown" \
  || echo "notify: desktop notification unavailable"
exit 0
