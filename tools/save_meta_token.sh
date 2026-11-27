#!/bin/bash
# Asks (in hidden Mac pop-ups) for the Reels app secret and the token from Graph API Explorer,
# saves them to .env on this Mac only, then turns them into a permanent Page token.
set -e
cd "$(dirname "$0")/.."
ask() { osascript -e "text returned of (display dialog \"$1\" default answer \"\" with hidden answer with title \"Reels poster setup\" buttons {\"Cancel\", \"Save\"} default button \"Save\")"; }
SECRET=$(ask "Paste the App secret (Meta app > App settings > Basic > App secret > Show):" | tr -d '[:space:]')
TOKEN=$(ask "Paste the access token from Graph API Explorer:" | tr -d '[:space:]')
if [ ${#TOKEN} -lt 50 ] || [ ${#SECRET} -lt 20 ]; then echo "That doesn't look right (too short). Nothing saved."; exit 1; fi
touch .env && chmod 600 .env
grep -v -e '^META_APP_SECRET=' -e '^META_USER_TOKEN=' .env > .env.tmp || true
printf 'META_APP_SECRET=%s\nMETA_USER_TOKEN=%s\n' "$SECRET" "$TOKEN" >> .env.tmp && mv .env.tmp .env && chmod 600 .env
unset SECRET TOKEN
echo "Saved to .env (this Mac only)."
python3 tools/meta_setup.py
