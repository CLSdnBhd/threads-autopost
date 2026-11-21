#!/usr/bin/env python3
"""Heads-up before each post, plus the SKIP check the poster uses.

Run by GitHub Actions 30 minutes before each slot (12:30 PM and 7:30 PM MYT).
It opens a GitHub issue for the next approved post, which GitHub emails to the
repo owner with the photos, caption and reply. Replying "SKIP" to that email
(or closing the issue) cancels that post.

  python3 poster/headsup.py            open a heads-up issue for the next due post
  python3 poster/headsup.py --dry-run  show what it would send

Env: GITHUB_TOKEN, GITHUB_REPOSITORY (set by Actions).
"""
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import post as poster  # noqa: E402

OWNER_MENTION = "@CLSdnBhd"   # GitHub notifies (emails) the owner because of this mention
WINDOW_MIN = 60               # look for a slot starting within the next hour


def gh(method, path, body=None):
    repo = os.environ["GITHUB_REPOSITORY"]
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                 "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        return json.loads(raw) if raw else {}


def issue_for(post_id):
    """The heads-up issue for this post, open or closed, or None."""
    q = urllib.parse.quote(f'repo:{os.environ["GITHUB_REPOSITORY"]} is:issue in:title "[{post_id}]"')
    try:
        req = urllib.request.Request(
            f"https://api.github.com/search/issues?q={q}",
            headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
                     "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            items = json.loads(r.read()).get("items", [])
    except urllib.error.HTTPError:
        return None
    return next((i for i in items if f"[{post_id}]" in i["title"]), None)


def skip_requested(post_id):
    """True if Calvin closed the heads-up issue or replied SKIP to it."""
    if not os.environ.get("GITHUB_TOKEN"):
        return False
    iss = issue_for(post_id)
    if not iss:
        return False
    if iss["state"] == "closed":
        return True
    for c in gh("GET", f"issues/{iss['number']}/comments"):
        first = (c.get("body") or "").strip().splitlines()[0:1]
        if first and first[0].strip().lower().startswith("skip"):
            return True
    return False


def close_with_note(post_id, note):
    if not os.environ.get("GITHUB_TOKEN"):
        return
    iss = issue_for(post_id)
    if iss and iss["state"] == "open":
        gh("POST", f"issues/{iss['number']}/comments", {"body": note})
        gh("PATCH", f"issues/{iss['number']}", {"state": "closed", "state_reason": "completed"})


def next_post(q, now):
    for p in sorted(q["posts"], key=lambda p: p["slot"]):
        if p.get("status") != "queued" or not p.get("approved"):
            continue
        slot = poster.parse_slot(p["slot"])
        if now <= slot <= now + dt.timedelta(minutes=WINDOW_MIN):
            return p
    return None


def body_for(p):
    slot = poster.parse_slot(p["slot"])
    imgs = "\n".join(f'<img src="{poster.photo_url(ph)}" width="180">' for ph in p["photos"])
    return (f"{OWNER_MENTION} this post goes out at **{slot:%-I:%M %p}** ({slot:%a %d %b}).\n\n"
            f"**To cancel it, reply `SKIP` to this email** (or close this issue). Do nothing to let it post.\n\n"
            f"---\n**Main post** ({p.get('formula','')}, {len(p['photos'])} photos):\n\n"
            + "\n".join(f"> {l}" for l in p["caption"].splitlines()) +
            f"\n\n**Reply under it:**\n\n" + "\n".join(f"> {l}" for l in poster.reply_text(p).splitlines()) +
            f"\n\n{imgs}\n")


def main():
    dry = "--dry-run" in sys.argv
    q = poster.load_queue()
    now = poster.now_myt()
    p = next_post(q, now)
    if not p:
        print("No post in the next hour.")
        return
    slot = poster.parse_slot(p["slot"])
    title = f"⏰ {slot:%-I:%M %p} {slot:%a}: {p['listing']} [{p['id']}] (reply SKIP to cancel)"
    if dry:
        print(title + "\n\n" + body_for(p))
        return
    if issue_for(p["id"]):
        print(f"Heads-up already sent for {p['id']}")
        return
    iss = gh("POST", "issues", {"title": title, "body": body_for(p)})
    print(f"Heads-up sent: {iss.get('html_url')}")


if __name__ == "__main__":
    main()
