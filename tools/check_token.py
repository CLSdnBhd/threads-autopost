#!/usr/bin/env python3
"""Check (and if needed, upgrade) the Threads token stored in threads-autopost/.env.

  python3 tools/check_token.py            show which Threads account the token posts as
  python3 tools/check_token.py exchange   turn a short-lived token (1 hour) into a
                                          long-lived one (60 days); needs THREADS_APP_SECRET in .env

.env format (you create this file yourself, it never leaves your Mac):
  THREADS_TOKEN=...
  THREADS_APP_SECRET=...     (only needed for "exchange")
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = os.path.join(ROOT, ".env")


def read_env():
    env = {}
    if os.path.exists(ENV):
        for line in open(ENV, encoding="utf-8"):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.strip().split("=", 1)
                env[k.strip()] = v.strip().strip('"')
    return env


def get(url):
    try:
        return json.loads(urllib.request.urlopen(url, timeout=30).read())
    except urllib.error.HTTPError as e:
        sys.exit(f"Threads said: {e.read().decode(errors='replace')}")


def main():
    env = read_env()
    token = env.get("THREADS_TOKEN")
    if not token:
        sys.exit(f"No THREADS_TOKEN in {ENV}")

    if sys.argv[1:] == ["exchange"]:
        secret = env.get("THREADS_APP_SECRET")
        if not secret:
            sys.exit("Add THREADS_APP_SECRET=... to .env first (Meta app > App settings > Basic > App secret)")
        r = get("https://graph.threads.net/access_token?" + urllib.parse.urlencode(
            {"grant_type": "th_exchange_token", "client_secret": secret, "access_token": token}))
        lines = [l for l in open(ENV, encoding="utf-8") if not l.startswith("THREADS_TOKEN=")]
        lines.append(f"THREADS_TOKEN={r['access_token']}\n")
        open(ENV, "w", encoding="utf-8").writelines(lines)
        token = r["access_token"]
        print(f"Long-lived token saved to .env (valid {int(r.get('expires_in', 0)) // 86400} days).")

    me = get("https://graph.threads.net/v1.0/me?" + urllib.parse.urlencode(
        {"fields": "id,username", "access_token": token}))
    print(f"Token works. It posts as @{me['username']} (id {me['id']}).")


if __name__ == "__main__":
    main()
