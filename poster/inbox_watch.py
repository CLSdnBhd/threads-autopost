#!/usr/bin/env python3
"""Telegram alerts for new replies on Calvin's Threads posts (including hidden ones).

Runs every 15 minutes in GitHub Actions. Looks at every post made in the last
21 days, finds replies by other people that haven't been alerted yet, and sends
each one to Calvin's Telegram bot chat. Remembers what it sent in
queue/seen_replies.json.

Threads has no API for DMs or message requests, so those are not covered here.

  python3 poster/inbox_watch.py            check and alert
  python3 poster/inbox_watch.py --test     send one "connected" message to Telegram
  python3 poster/inbox_watch.py --dry-run  print what would be sent

Env: THREADS_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import post as poster  # noqa: E402

ROOT = poster.ROOT
SEEN = os.path.join(ROOT, "queue", "seen_replies.json")
HISTORY = os.path.join(ROOT, "queue", "history.json")
ME = "calvinnnadam"
LOOKBACK_DAYS = 21
HIDDEN = {"HIDDEN", "COVERED", "RESTRICTED", "BLOCKED"}


def telegram(text):
    token, chat = os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"]
    data = urllib.parse.urlencode({"chat_id": chat, "text": text,
                                   "disable_web_page_preview": "true"}).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=30) as r:
        return json.loads(r.read()).get("ok")


def recent_posts():
    posts = poster.load_queue()["posts"]
    if os.path.exists(HISTORY):
        posts += json.load(open(HISTORY, encoding="utf-8"))["posts"]
    cutoff = poster.now_myt() - dt.timedelta(days=LOOKBACK_DAYS)
    out = []
    for p in posts:
        if p.get("status") == "posted" and p.get("post_id") and p.get("posted_at"):
            when = dt.datetime.strptime(p["posted_at"], "%Y-%m-%d %H:%M").replace(tzinfo=poster.MYT)
            if when >= cutoff:
                out.append(p)
    return out


def replies_for(media_id, token):
    fields = "id,text,username,timestamp,permalink,hide_status,media_type"
    r = poster.api("GET", f"{media_id}/conversation", {"fields": fields, "reverse": "false"}, token)
    return r.get("data", [])


def listing_name(p):
    return p.get("listing", "").replace("-", " ").title()


def main():
    test, dry = "--test" in sys.argv, "--dry-run" in sys.argv
    if test:
        ok = telegram("✅ Threads alerts connected. I'll message you here whenever someone replies "
                      "to your Threads posts (hidden replies included).")
        print("Telegram test sent" if ok else "Telegram test FAILED")
        return

    token = os.environ["THREADS_TOKEN"]
    seen = set(json.load(open(SEEN))) if os.path.exists(SEEN) else set()
    first_run = not os.path.exists(SEEN)
    new = []
    for p in recent_posts():
        try:
            reps = replies_for(p["post_id"], token)
        except Exception as e:
            print(f"  couldn't read replies for {p['id']}: {e}")
            continue
        for r in reps:
            if r["id"] in seen or r.get("username") == ME:
                seen.add(r["id"])
                continue
            seen.add(r["id"])
            new.append((p, r))

    if first_run:
        print(f"First run: remembering {len(seen)} existing replies, no alerts sent.")
    else:
        for p, r in new:
            hidden = r.get("hide_status") in HIDDEN
            msg = (f"{'🙈 HIDDEN reply' if hidden else '💬 New reply'} on your Threads post "
                   f"({listing_name(p)})\n\n@{r.get('username', '?')}: {r.get('text') or '(photo/no text)'}\n\n"
                   f"Open: {r.get('permalink') or p.get('permalink')}")
            if hidden:
                msg += "\n\n(Threads hid this reply. Check it: it may be a buyer.)"
            print(msg + "\n---")
            if not dry:
                telegram(msg)
        print(f"{len(new)} new replies.")

    if not dry:
        with open(SEEN, "w") as f:
            json.dump(sorted(seen), f, indent=0)


if __name__ == "__main__":
    main()
