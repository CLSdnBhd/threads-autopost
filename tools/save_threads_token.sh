#!/bin/bash
# Asks for your Threads access token in a Mac pop-up (hidden), saves it to .env
# on this Mac only (never uploaded), then checks which Threads account it posts as.
set -e
cd "$(dirname "$0")/.."
TOKEN=$(osascript -e 'text returned of (display dialog "Paste your Threads access token from the Meta page:" default answer "" with hidden answer with title "Threads token" buttons {"Cancel", "Save"} default button "Save")')
TOKEN=$(printf '%s' "$TOKEN" | tr -d '[:space:]')
if [ ${#TOKEN} -lt 50 ]; then echo "That looks too short to be a Threads token. Nothing saved."; exit 1; fi
touch .env && chmod 600 .env
grep -v '^THREADS_TOKEN=' .env > .env.tmp || true
printf 'THREADS_TOKEN=%s\n' "$TOKEN" >> .env.tmp && mv .env.tmp .env && chmod 600 .env
unset TOKEN
echo "Saved to .env (this Mac only)."
python3 tools/check_token.py
