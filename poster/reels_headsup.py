#!/usr/bin/env python3
"""Heads-up 30 min before each reel: opens a GitHub issue (emailed to Calvin) with the
caption and a link to the video. Replying SKIP or closing the issue cancels that reel.

  python3 poster/reels_headsup.py [--dry-run]
"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import headsup  # noqa: E402
import reels    # noqa: E402

WINDOW_MIN = 120   # heads-up runs from 7 PM for the 8 PM reel


def main():
    dry = "--dry-run" in sys.argv
    q = reels.load_queue()
    now = reels.now_myt()
    p = next((p for p in sorted(q["posts"], key=lambda p: p["slot"])
              if p.get("status") == "queued" and p.get("approved")
              and now <= reels.parse_slot(p["slot"]) <= now + dt.timedelta(minutes=WINDOW_MIN)), None)
    if not p:
        print("No reel in the next hour.")
        return
    slot = reels.parse_slot(p["slot"])
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    video = f"https://github.com/{repo}/blob/main/{p['video']}"
    title = f"🎬 {slot:%-I:%M %p} {slot:%a}: {p.get('title')} [{p['id']}] (reply SKIP to cancel)"
    body = (f"{headsup.OWNER_MENTION} this reel goes out at **{slot:%-I:%M %p}** ({slot:%a %d %b}) "
            f"on {', '.join(p.get('platforms', reels.PLATFORMS))}.\n\n"
            f"**To cancel it, reply `SKIP` to this email** (or close this issue). Do nothing to let it post.\n\n"
            f"**Video:** {video}\n\n---\n**Caption:**\n\n" + "\n".join(f"> {l}" for l in reels.full_caption(p).splitlines()))
    if dry:
        print(title + "\n\n" + body)
        return
    if headsup.issue_for(p["id"]):
        print(f"Heads-up already sent for {p['id']}")
        return
    iss = headsup.gh("POST", "issues", {"title": title, "body": body})
    print(f"Heads-up sent: {iss.get('html_url')}")
    reels.tg(f"⏰ {slot:%-I:%M %p} tonight: {p.get('title')}\n\n{p['caption']}\n\n"
             f"🎬 Video: {video}\n"
             f"To cancel, reply SKIP to the GitHub email or close this: {iss.get('html_url')}")


if __name__ == "__main__":
    main()
