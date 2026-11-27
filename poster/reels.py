#!/usr/bin/env python3
"""Reels auto-poster for Facebook Page + Instagram (@caricalvin campaign).

Runs in GitHub Actions at 8 PM Malaysia time. Picks the approved reel from
queue/reels.json that is due, uploads the video file straight to Meta (no public
link needed) as a Facebook Reel and an Instagram Reel, and records the result.
Each platform is tracked on its own, so a retry only re-posts where it failed.

  python3 poster/reels.py              post whatever is due now
  python3 poster/reels.py --dry-run    show what would be posted
  python3 poster/reels.py --id <id>    post one approved reel now (test)
  python3 poster/reels.py --check      check the Meta token and print the accounts it posts to

Env (GitHub secrets): META_PAGE_TOKEN, FB_PAGE_ID, IG_USER_ID.
Standard library only.
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

V = "v21.0"
GRAPH = f"https://graph.facebook.com/{V}"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUEUE = os.path.join(ROOT, "queue", "reels.json")
CONFIG = os.path.join(ROOT, "config.json")
MYT = dt.timezone(dt.timedelta(hours=8))
EARLY_MIN, LATE_HOURS = 15, 10
IG_CAPTION_MAX, IG_TAGS_MAX = 2200, 30
PLATFORMS = ("facebook", "instagram")


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


def footer():
    """Agency line on every caption (Malaysian estate-agent ads should show agency + REN)."""
    c = json.load(open(CONFIG, encoding="utf-8")).get("reels", {})
    ren = c.get("ren_number", "").strip()
    title = ren or c.get("agent_title", "").strip()
    brand = c.get("brand", "KL Realtor").strip()
    return f"Calvin{' · ' + title if title else ''}{' · ' + brand if brand else ''}"


def tg(text):
    """Message Calvin's Telegram bot. Never lets a Telegram problem stop posting."""
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return False
    try:
        data = urllib.parse.urlencode({"chat_id": chat, "text": text, "disable_web_page_preview": "true"}).encode()
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=30) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception as e:
        print(f"  (Telegram message failed: {e})")
        return False


def full_caption(post):
    tags = " ".join(post.get("hashtags", []))
    return "\n\n".join(x for x in (post["caption"].strip(), footer(), tags) if x)


# ---------------- Meta API ----------------
def call(method, url, params=None, token=None, data=None, headers=None, timeout=120):
    params = dict(params or {})
    if token and data is None:
        params["access_token"] = token
    q = urllib.parse.urlencode(params)
    if method == "GET":
        req = urllib.request.Request(f"{url}?{q}" if q else url, headers=headers or {})
    else:
        body = data if data is not None else q.encode()
        req = urllib.request.Request(f"{url}?{q}" if (data is not None and q) else url, data=body,
                                     method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Meta API {e.code} on {url.split('?')[0]}: {e.read().decode(errors='replace')[:600]}") from None


def upload_bytes(url, path, token):
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        data = f.read()
    return call("POST", url, data=data, timeout=600, headers={
        "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size),
        "Content-Type": "application/octet-stream"})


def post_instagram(post, video, token, ig_id):
    c = call("POST", f"{GRAPH}/{ig_id}/media", {
        "media_type": "REELS", "upload_type": "resumable", "caption": full_caption(post),
        "share_to_feed": "true"}, token)
    cid = c["id"]
    upload_bytes(c.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{V}/{cid}", video, token)
    start = time.time()
    while True:
        s = call("GET", f"{GRAPH}/{cid}", {"fields": "status_code,status"}, token)
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram processing {s.get('status_code')}: {s.get('status')}")
        if time.time() - start > 600:
            raise RuntimeError("Instagram still processing after 10 min")
        time.sleep(10)
    mid = call("POST", f"{GRAPH}/{ig_id}/media_publish", {"creation_id": cid}, token)["id"]
    link = call("GET", f"{GRAPH}/{mid}", {"fields": "permalink"}, token).get("permalink")
    return mid, link


def post_facebook(post, video, token, page_id):
    s = call("POST", f"{GRAPH}/{page_id}/video_reels", {"upload_phase": "start"}, token)
    vid = s["video_id"]
    upload_bytes(s.get("upload_url") or f"https://rupload.facebook.com/video-upload/{V}/{vid}", video, token)
    call("POST", f"{GRAPH}/{page_id}/video_reels", {
        "upload_phase": "finish", "video_id": vid, "video_state": "PUBLISHED",
        "description": full_caption(post)}, token)
    start = time.time()
    while time.time() - start < 600:
        st = call("GET", f"{GRAPH}/{vid}", {"fields": "status"}, token).get("status", {})
        if st.get("video_status") in ("ready", "published") or st.get("publishing_phase", {}).get("status") == "complete":
            break
        if st.get("video_status") == "error":
            raise RuntimeError(f"Facebook processing error: {st}")
        time.sleep(10)
    return vid, f"https://www.facebook.com/reel/{vid}"


# ---------------- queue logic ----------------
def validate(post):
    problems = []
    video = os.path.join(ROOT, post["video"])
    if not os.path.exists(video):
        problems.append(f"missing video {post['video']}")
    elif os.path.getsize(video) > 300 * 1024 * 1024:
        problems.append("video over 300 MB")
    cap = full_caption(post)
    if len(cap) > IG_CAPTION_MAX:
        problems.append(f"caption {len(cap)} chars (Instagram max {IG_CAPTION_MAX})")
    if len(post.get("hashtags", [])) > IG_TAGS_MAX:
        problems.append(f"{len(post['hashtags'])} hashtags (Instagram max {IG_TAGS_MAX})")
    return problems


def pending_platforms(post):
    res = post.get("results", {})
    return [p for p in post.get("platforms", PLATFORMS) if res.get(p, {}).get("status") != "posted"]


def pick_due(q, now):
    due = None
    for post in sorted(q["posts"], key=lambda p: p["slot"]):
        if post.get("status") not in ("queued", "partial") or not post.get("approved"):
            continue
        slot = parse_slot(post["slot"])
        if slot > now + dt.timedelta(minutes=EARLY_MIN):
            continue
        if now - slot > dt.timedelta(hours=LATE_HOURS):
            if post["status"] == "queued":
                post["status"] = "missed"
                print(f"- {post['id']}: missed (slot {post['slot']} too old)")
            continue
        if due is None:
            due = post
    return due


def creds():
    t, page, ig = (os.environ.get(k) for k in ("META_PAGE_TOKEN", "FB_PAGE_ID", "IG_USER_ID"))
    if not (t and page and ig):
        sys.exit("META_PAGE_TOKEN, FB_PAGE_ID and IG_USER_ID must all be set")
    return t, page, ig


def check():
    t, page, ig = creds()
    p = call("GET", f"{GRAPH}/{page}", {"fields": "name,username"}, t)
    i = call("GET", f"{GRAPH}/{ig}", {"fields": "username"}, t)
    print(f"Token works. Facebook Page: {p.get('name')} (@{p.get('username')}). Instagram: @{i.get('username')}.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--id")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        return check()

    q = load_queue()
    now = now_myt()
    print(f"Now {now:%Y-%m-%d %H:%M} MYT")
    if a.id:
        post = next((p for p in q["posts"] if p["id"] == a.id), None)
        if not post:
            sys.exit(f"No reel with id {a.id}")
        if not post.get("approved"):
            sys.exit(f"{a.id} is not approved yet")
    else:
        post = pick_due(q, now)
    if not post:
        print("Nothing due.")
        if not a.dry_run:
            save_queue(q)
        return

    todo = pending_platforms(post)
    print(f"Due: {post['id']} ({post['slot']}) {post.get('title')} -> {', '.join(todo) or 'nothing left'}")
    problems = validate(post)
    if problems:
        post["status"], post["error"] = "error", "; ".join(problems)
        print("  NOT POSTED: " + post["error"])
        if not a.dry_run:
            save_queue(q)
            tg(f"⚠️ Reel NOT posted: {post.get('title')}\n{post['error']}\nTell Claude to fix it.")
        sys.exit(1)
    if a.dry_run:
        print("--- caption ---\n" + full_caption(post) + "\n(dry run: nothing posted)")
        return

    import headsup  # same heads-up issues as the Threads poster
    try:
        skip = headsup.skip_requested(post["id"])
    except Exception as e:
        print(f"  (couldn't check for SKIP: {e})")
        skip = False
    if skip:
        post.update(status="skipped", error="Calvin replied SKIP to the heads-up")
        save_queue(q)
        print("  SKIPPED")
        tg(f"⏭️ Skipped tonight's reel as you asked: {post.get('title')}")
        return

    token, page_id, ig_id = creds()
    video = os.path.join(ROOT, post["video"])
    post.setdefault("results", {})
    for plat in todo:
        try:
            fn = post_facebook if plat == "facebook" else post_instagram
            mid, link = fn(post, video, token, page_id if plat == "facebook" else ig_id)
            post["results"][plat] = {"status": "posted", "id": mid, "permalink": link,
                                     "posted_at": now_myt().strftime("%Y-%m-%d %H:%M")}
            print(f"  {plat}: {link}")
        except Exception as e:
            post["results"][plat] = {"status": "error", "error": str(e)[:800]}
            print(f"  {plat} FAILED: {e}")
        save_queue(q)

    left = pending_platforms(post)
    post["status"] = "posted" if not left else ("partial" if len(left) < len(post.get("platforms", PLATFORMS)) else "error")
    post["error"] = None if not left else "; ".join(post["results"][p].get("error", "") for p in left)
    save_queue(q)
    links = "\n".join(f"- {p}: {r.get('permalink')}" for p, r in post["results"].items() if r.get("status") == "posted")
    if not left:
        tg(f"✅ Reel posted: {post.get('title')}\n\n{links.replace('- ', '')}\n\n"
           "Reply to comments in the next 30 min, and upload the same video to TikTok 🙌")
    else:
        tg(f"⚠️ Reel problem: {post.get('title')}\nPosted: {links.replace('- ', '') or 'none'}\n"
           f"Failed: {', '.join(left)}. Tomorrow's run retries only what failed. Tell Claude if it keeps failing.")
    try:
        if not left:
            headsup.close_with_note(post["id"], f"✅ Posted:\n{links}")
    except Exception as e:
        print(f"  (couldn't close heads-up: {e})")
    if left:
        sys.exit(1)


if __name__ == "__main__":
    main()
