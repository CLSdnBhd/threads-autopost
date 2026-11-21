#!/bin/bash
# Asks for your GitHub access key in a Mac pop-up (hidden), saves it in your
# Keychain for github.com, then uploads. The key is never printed or stored in a file.
set -e
cd "$(dirname "$0")/.."
KEY=$(osascript -e 'text returned of (display dialog "Paste your NEW GitHub access key (starts with github_pat_):" default answer "" with hidden answer with title "GitHub upload" buttons {"Cancel", "Save"} default button "Save")')
case "$KEY" in
  github_pat_*|ghp_*) ;;
  *) echo "That doesn't look like a GitHub access key (should start with github_pat_). Nothing saved."; exit 1 ;;
esac
printf 'protocol=https\nhost=github.com\n\n' | git credential reject 2>/dev/null || true
printf 'protocol=https\nhost=github.com\nusername=CLSdnBhd\npassword=%s\n\n' "$KEY" | git credential approve
unset KEY
echo "Key saved to Keychain. Uploading..."
git push -u origin main
echo "UPLOAD DONE"
