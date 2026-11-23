#!/usr/bin/env bash
# Runs the poller every 10 minutes (every 30 overnight) for about 5.5 hours,
# saving state after each pass. GitHub's own cron is best-effort and often
# skips runs for hours, so the workflow keeps itself alive instead: each run
# queues the next one, and the cron is only a watchdog.
set -u
LOOP_SECONDS=${LOOP_SECONDS:-19800}
end=$(( $(date +%s) + LOOP_SECONDS ))
git config user.name "radar-bot"
git config user.email "radar-bot@users.noreply.github.com"
pass=0
while :; do
  start=$(date +%s)
  git pull -q --rebase origin main || echo "! git pull failed, using current checkout"
  if [ -f .test-alert ] || { [ "$pass" = 0 ] && [ "${TEST_INPUT:-false}" = "true" ]; }; then
    export TEST_ALERT=1
  else
    unset TEST_ALERT
  fi
  # Only the first pass counts as a manual/push run (writes snapshot + health).
  if [ "$pass" -gt 0 ]; then export GITHUB_EVENT_NAME=schedule; fi
  echo "::group::pass $pass at $(TZ=America/New_York date '+%b %d %I:%M %p ET')"
  timeout 540 python3 poller.py || echo "! poller exited with $?"
  echo "::endgroup::"
  [ -f .test-alert ] && git rm -q .test-alert
  git add -A data
  if ! git diff --cached --quiet; then
    git commit -q -m "radar: state update"
    for i in 1 2 3; do
      git pull -q --rebase origin main && git push -q origin HEAD:main && break
      sleep 5
    done
  fi
  pass=$(( pass + 1 ))
  hour=$(TZ=America/New_York date +%H)
  interval=600
  if [ $((10#$hour)) -lt 7 ]; then interval=1800; fi
  next=$(( start + interval ))
  if [ "$next" -ge "$end" ]; then break; fi
  wait=$(( next - $(date +%s) ))
  if [ "$wait" -gt 0 ]; then sleep "$wait"; fi
done
echo "Loop finished after $pass passes."
