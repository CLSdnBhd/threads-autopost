#!/usr/bin/env python3
"""Threads auto-poster.

Runs in GitHub Actions at 1 PM and 8 PM Malaysia time. Picks the next
approved post from queue/queue.json that is due, publishes it to Threads
(carousel or single image), then posts the self-reply with the WhatsApp
link, and records the result back into queue.json.

Standard library only, so it runs anywhere Python 3.9+ exists.

Usage:
  python3 poster/post.py              # post whatever is due now
  python3 poster/post.py --dry-run    # show what would be posted, post nothing
  python3 poster/post.py --id <post-id>   # post one specific approved post now (test)

Env:
  THREADS_TOKEN   long-lived Threads access token (GitHub secret)
  GITHUB_REPOSITORY / GITHUB_SHA  set automatically by GitHub Actions; used
                  to build the public photo URLs Threads downloads from.
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://graph.threads.net/v1.0"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE = os.path.join(ROOT, "queue", "queue.json")
MYT = dt.timezone(dt.timedelta(hours=8))
EARLY_MIN = 15          # a run may post a slot up to 15 min before its time
LATE_HOURS = 10         # slots more than 10 h overdue are marked "missed"
CAPTION_MAX = 500       # Threads text limit


def now_myt():
    return dt.datetime.now(MYT)


def parse_slot(s):
    return dt.datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=MYT)


def load_queue():
    with open(QUEUE, encoding="utf-8") as f:
        return json.load(f)


def save_queue(q):
    with open(QUEUE, "w", encoding="utf-8") as f:
        json.dump(q, f, ensure_ascii=False, indent=2)
        f.write("\n")


def api(method, path, params, token):
    params = dict(params, access_token=token)
    data = urllib.parse.urlencode(params).encode()
    url = f"{API}/{path}"
    if method == "GET":
        req = urllib.request.Request(f"{url}?{data.decode()}")
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"Threads API {e.code} on {path}: {body}") from None


def wait_ready(container_id, token, timeout=300):
    """Threads needs time to download/process media before publishing."""
    start = time.time()
    while time.time() - start < timeout:
        r = api("GET", container_id, {"fields": "status,error_message"}, token)
        status = r.get("status")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Container {container_id} {status}: {r.get('error_message')}")
        time.sleep(5)
    raise RuntimeError(f"Container {container_id} not ready after {timeout}s")


def photo_url(path):
    repo = os.environ.get("GITHUB_REPOSITORY")
    ref = os.environ.get("GITHUB_SHA", "main")
    if not repo:
        raise RuntimeError("GITHUB_REPOSITORY not set; photo URLs need the public repo name")
    return f"https://raw.githubusercontent.com/{repo}/{ref}/{urllib.parse.quote(path)}"


def publish_post(post, token):
    photos = post["photos"]
    if not 1 <= len(photos) <= 20:
        raise RuntimeError(f"{len(photos)} photos; Threads allows 1-20")

    if len(photos) == 1:
        cid = api("POST", "me/threads", {
            "media_type": "IMAGE", "image_url": photo_url(photos[0]), "text": post["caption"],
        }, token)["id"]
    else:
        children = []
        for p in photos:
            child = api("POST", "me/threads", {
                "media_type": "IMAGE", "image_url": photo_url(p), "is_carousel_item": "true",
            }, token)["id"]
            children.append(child)
        for c in children:
            wait_ready(c, token)
        cid = api("POST", "me/threads", {
            "media_type": "CAROUSEL", "children": ",".join(children), "text": post["caption"],
        }, token)["id"]

    wait_ready(cid, token)
    media_id = api("POST", "me/threads_publish", {"creation_id": cid}, token)["id"]
    print(f"  published main post {media_id}")

    reply_id = None
    if post.get("reply"):
        time.sleep(20)  # look natural: reply lands shortly after the post
        rid = api("POST", "me/threads", {
            "media_type": "TEXT", "text": reply_text(post), "reply_to_id": media_id,
        }, token)["id"]
        wait_ready(rid, token)
        reply_id = api("POST", "me/threads_publish", {"creation_id": rid}, token)["id"]
        print(f"  published reply {reply_id}")

    permalink = api("GET", media_id, {"fields": "permalink"}, token).get("permalink")
    return media_id, reply_id, permalink


def reply_text(post):
    """Reply text with the WhatsApp link on its own last line (Threads shows a link preview)."""
    text = post.get("reply", "")
    if post.get("link"):
        text = f"{text}\n{post['link']}"
    return text


def validate(post):
    problems = []
    if len(post.get("caption", "")) > CAPTION_MAX:
        problems.append(f"caption is {len(post['caption'])} chars (max {CAPTION_MAX})")
    if len(reply_text(post)) > CAPTION_MAX:
        problems.append(f"reply + link is {len(reply_text(post))} chars (max {CAPTION_MAX})")
    for p in post.get("photos", []):
        if not os.path.exists(os.path.join(ROOT, p)):
            problems.append(f"missing photo {p}")
    return problems


def pick_due(q, now):
    """Mark stale slots missed; return the earliest approved, queued, due post."""
    due = None
    for post in sorted(q["posts"], key=lambda p: p["slot"]):
        if post.get("status") != "queued" or not post.get("approved"):
            continue
        slot = parse_slot(post["slot"])
        if slot > now + dt.timedelta(minutes=EARLY_MIN):
            continue
        if now - slot > dt.timedelta(hours=LATE_HOURS):
            post["status"] = "missed"
            print(f"- {post['id']}: missed (slot {post['slot']} too old)")
            continue
        if due is None:
            due = post
    return due


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--id", help="post this approved post now, ignoring its slot")
    a = ap.parse_args()

    q = load_queue()
    now = now_myt()
    print(f"Now {now:%Y-%m-%d %H:%M} MYT")

    if a.id:
        post = next((p for p in q["posts"] if p["id"] == a.id), None)
        if not post:
            sys.exit(f"No post with id {a.id}")
        if not post.get("approved"):
            sys.exit(f"{a.id} is not approved yet")
        if post.get("status") == "posted":
            sys.exit(f"{a.id} was already posted: {post.get('permalink')}")
    else:
        post = pick_due(q, now)

    if not post:
        print("Nothing due.")
        if not a.dry_run:
            save_queue(q)
        return

    print(f"Due: {post['id']} ({post['slot']}) - {post.get('listing')} - {len(post['photos'])} photos")
    problems = validate(post)
    if problems:
        post["status"], post["error"] = "error", "; ".join(problems)
        print("  NOT POSTED: " + post["error"])
        if not a.dry_run:
            save_queue(q)
        sys.exit(1)

    if a.dry_run:
        print("--- caption ---\n" + post["caption"])
        print("--- reply ---\n" + post.get("reply", ""))
        print("--- link ---\n" + post.get("link", ""))
        print("(dry run: nothing posted)")
        return

    token = os.environ.get("THREADS_TOKEN")
    if not token:
        sys.exit("THREADS_TOKEN is not set")
    try:
        media_id, reply_id, permalink = publish_post(post, token)
    except Exception as e:  # record the failure so it shows up in the weekly report
        post["status"], post["error"] = "error", str(e)[:800]
        save_queue(q)
        print(f"  FAILED: {e}")
        sys.exit(1)

    post.update(status="posted", post_id=media_id, reply_id=reply_id, permalink=permalink,
                posted_at=now_myt().strftime("%Y-%m-%d %H:%M"), error=None)
    save_queue(q)
    print(f"  done: {permalink}")


if __name__ == "__main__":
    main()
