#!/usr/bin/env python3
"""Weekly prep helper (runs on the Mac, used by Claude every Sunday).

  python3 tools/prep.py scan                 list listings in inbox/ and how often each was posted
  python3 tools/prep.py photos <folder>      resize a listing's photos into queue/photos/<folder>/
  python3 tools/prep.py slots [YYYY-MM-DD]   print the 14 slots for the week starting that Monday
  python3 tools/prep.py validate             check every queued post (length, photos, link)
  python3 tools/prep.py review               build queue/review.html (the approval page)
  python3 tools/prep.py approve [ids...]     mark posts approved (all queued ones if no ids)
  python3 tools/prep.py archive              move posted/missed posts into queue/history.json
  python3 tools/prep.py report               pull Threads insights for posted posts (needs .env)

Standard library + macOS `sips` only.
"""
import base64
import datetime as dt
import html
import json
import os
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(ROOT, "inbox")
QDIR = os.path.join(ROOT, "queue")
QUEUE = os.path.join(QDIR, "queue.json")
HISTORY = os.path.join(QDIR, "history.json")
CONFIG = os.path.join(ROOT, "config.json")
PHOTO_EXT = (".jpg", ".jpeg", ".png", ".heic", ".webp")
SLOT_TIMES = ("13:00", "20:00")


def load(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def all_posts():
    return load(HISTORY, {"posts": []})["posts"] + load(QUEUE, {"posts": []})["posts"]


def listing_photos(folder):
    d = os.path.join(INBOX, folder)
    return sorted(f for f in os.listdir(d) if f.lower().endswith(PHOTO_EXT) and not f.startswith("."))


def cmd_scan():
    counts, last = {}, {}
    for p in all_posts():
        if p.get("status") == "posted":
            counts[p["listing"]] = counts.get(p["listing"], 0) + 1
            last[p["listing"]] = max(last.get(p["listing"], ""), p.get("posted_at") or "")
    queued = {p["listing"] for p in load(QUEUE, {"posts": []})["posts"] if p.get("status") == "queued"}
    for folder in sorted(os.listdir(INBOX)):
        d = os.path.join(INBOX, folder)
        if not os.path.isdir(d) or folder.startswith(("_", ".")):
            continue
        details = os.path.join(d, "details.txt")
        info = open(details, encoding="utf-8").read().strip() if os.path.exists(details) else "(no details.txt)"
        other = sorted(f for f in os.listdir(d) if not f.lower().endswith(PHOTO_EXT)
                       and f != "details.txt" and not f.startswith("."))
        print(f"== {folder}")
        print(f"   photos: {len(listing_photos(folder))}  posted: {counts.get(folder, 0)}x"
              f"  last: {last.get(folder) or '-'}  in queue: {'yes' if folder in queued else 'no'}")
        if other:
            print(f"   other files (brochure/notes, read these too): {', '.join(other)}")
        for line in info.splitlines():
            print(f"   | {line}")


def cmd_photos(folder):
    src = listing_photos(folder)
    if not src:
        sys.exit(f"No photos in inbox/{folder}")
    out = os.path.join(QDIR, "photos", folder)
    os.makedirs(out, exist_ok=True)
    paths = []
    for i, f in enumerate(src[:20], 1):
        dst = os.path.join(out, f"{i:02d}.jpg")
        subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "85", "-Z", "1440",
                        os.path.join(INBOX, folder, f), "--out", dst],
                       check=True, capture_output=True)
        paths.append(os.path.relpath(dst, ROOT))
    if len(src) > 20:
        print(f"note: {len(src)} photos, Threads allows 20; used the first 20 by filename")
    print(json.dumps(paths, indent=2))


def cmd_slots(start=None):
    today = dt.date.today()
    monday = dt.date.fromisoformat(start) if start else today + dt.timedelta(days=(7 - today.weekday()) % 7 or 7)
    for i in range(7):
        d = monday + dt.timedelta(days=i)
        for t in SLOT_TIMES:
            tag = "am" if t == "13:00" else "pm"
            print(f"{d:%Y-%m-%d}-{tag}\t{d:%Y-%m-%d} {t}\t{d:%a}")


def problems_for(p):
    out = []
    if len(p.get("caption", "")) > 500:
        out.append(f"caption {len(p['caption'])} chars > 500")
    reply_len = len(p.get("reply", "")) + (len(p["link"]) + 1 if p.get("link") else 0)
    if reply_len > 500:
        out.append(f"reply + link {reply_len} chars > 500")
    if not p.get("caption"):
        out.append("no caption")
    if not 1 <= len(p.get("photos", [])) <= 20:
        out.append(f"{len(p.get('photos', []))} photos (need 1-20)")
    for ph in p.get("photos", []):
        if not os.path.exists(os.path.join(ROOT, ph)):
            out.append(f"missing {ph}")
        elif os.path.getsize(os.path.join(ROOT, ph)) > 8 * 1024 * 1024:
            out.append(f"{ph} over 8 MB")
    if p.get("link") and not p["link"].startswith("https://"):
        out.append("link must start with https://")
    for name in dev_names(p.get("listing", "")):
        for field in ("caption", "reply"):
            if name.lower() in p.get(field, "").lower():
                out.append(f"{field} names the development ({name}): Calvin's rule is no development names on Threads")
    return out


def dev_names(folder):
    """Project/developer names from a listing's details.txt that must never appear in replies."""
    path = os.path.join(INBOX, folder, "details.txt")
    names = []
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            for key in ("project:", "developer:"):
                if line.lower().startswith(key):
                    v = line.split(":", 1)[1].split("#")[0].strip()
                    v = v.split(" (")[0].split(",")[0].split(" by ")[0].strip()
                    if len(v) >= 3 and not v.startswith("("):
                        names.append(v)
    return names


def cmd_validate():
    q = load(QUEUE, {"posts": []})
    bad = 0
    ids = [p["id"] for p in q["posts"]]
    if len(ids) != len(set(ids)):
        print("DUPLICATE post ids")
        bad += 1
    for p in q["posts"]:
        if p.get("status") != "queued":
            continue
        pr = problems_for(p)
        print(f"{'OK ' if not pr else 'BAD'} {p['id']}  {p['listing']}  {len(p['photos'])} photos"
              f"  caption {len(p['caption'])}c  {'approved' if p.get('approved') else 'not approved'}")
        for x in pr:
            print(f"     - {x}")
        bad += bool(pr)
    sys.exit(1 if bad else 0)


def thumb(path, size=360):
    with tempfile.TemporaryDirectory() as t:
        dst = os.path.join(t, "t.jpg")
        subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "70", "-Z", str(size),
                        os.path.join(ROOT, path), "--out", dst], check=True, capture_output=True)
        return "data:image/jpeg;base64," + base64.b64encode(open(dst, "rb").read()).decode()


def cmd_review():
    q = load(QUEUE, {"posts": []})
    posts = [p for p in sorted(q["posts"], key=lambda p: p["slot"]) if p.get("status") == "queued"]
    cards = []
    for n, p in enumerate(posts, 1):
        slot = dt.datetime.strptime(p["slot"], "%Y-%m-%d %H:%M")
        imgs = "".join(f'<img src="{thumb(ph)}" alt="Photo {i+1}">' for i, ph in enumerate(p["photos"]))
        pr = problems_for(p)
        warn = f'<p class="warn">⚠ {html.escape("; ".join(pr))}</p>' if pr else ""
        cards.append(f"""
<article class="post" id="p{n}">
  <header><span class="num">{n}</span><div><b>{slot:%a %d %b, %-I:%M %p}</b>
  <small>{html.escape(p['listing'])} · {html.escape(p.get('formula',''))} · {len(p['photos'])} photos · ID {html.escape(p['id'])}</small></div>
  <span class="state {'ok' if p.get('approved') else ''}">{'Approved' if p.get('approved') else 'Waiting for approval'}</span></header>
  <div class="strip">{imgs}</div>
  <div class="txt"><div class="lbl">Main post</div><p>{html.escape(p['caption']).replace(chr(10), '<br>')}</p>
  <div class="lbl">Reply (posted ~20 s later)</div><p>{html.escape(p.get('reply','')).replace(chr(10), '<br>')}</p>
  <p class="link">{html.escape(p.get('link',''))}</p>{warn}</div>
</article>""")
    # Listings tracker: every inbox listing, its facts, what's missing, how often it's queued/posted
    queued_n, posted_n = {}, {}
    for p in all_posts():
        tgt = queued_n if p.get("status") == "queued" else posted_n if p.get("status") == "posted" else None
        if tgt is not None:
            tgt[p["listing"]] = tgt.get(p["listing"], 0) + 1
    rows = []
    for folder in sorted(os.listdir(INBOX)):
        d = os.path.join(INBOX, folder)
        if not os.path.isdir(d) or folder.startswith(("_", ".")):
            continue
        facts, missing = {}, ""
        dt_path = os.path.join(d, "details.txt")
        if os.path.exists(dt_path):
            for line in open(dt_path, encoding="utf-8"):
                line = line.strip()
                if line.upper().startswith("# MISSING"):
                    missing = line.split(":", 1)[-1].strip()
                elif ":" in line and not line.startswith("#"):
                    k, v = line.split(":", 1)
                    facts[k.strip()] = v.split("#")[0].strip()
        name = facts.get("project", folder) + (f", {facts['area']}" if facts.get("area") else "")
        miss = f'<span class="miss">Needs: {html.escape(missing)}</span>' if missing else '<span class="ok-t">Complete</span>'
        rows.append(f"<tr><td><b>{html.escape(name)}</b><small>{html.escape(facts.get('type',''))}</small></td>"
                    f"<td>{html.escape(facts.get('price','-'))}</td><td class='n'>{len(listing_photos(folder))}</td>"
                    f"<td class='n'>{queued_n.get(folder,0)}</td><td class='n'>{posted_n.get(folder,0)}</td><td>{miss}</td></tr>")
    cfg = load(CONFIG, {})
    banner = ""
    if "X" in cfg.get("whatsapp_number", "X"):
        banner = ('<p class="banner">⚠ Your WhatsApp number isn\'t set yet, so the links in the replies are placeholders. '
                  'Send it to Claude before approving.</p>')
    tracker = f"""<section class="tracker"><h2>Listings</h2><div class="tbl"><table>
<thead><tr><th>Listing</th><th>Price</th><th>Photos</th><th>This week</th><th>Posted</th><th>Details</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<p class="sub">Add a property by sending photos and then a LISTING: message to the WhatsApp group "Cal's PA Claude".</p></section>"""
    week = f"{posts[0]['slot'][:10]} to {posts[-1]['slot'][:10]}" if posts else "empty"
    page = f"""<title>Threads Planner</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>
:root{{--bg:#f5f6f8;--card:#fff;--fg:#18212c;--muted:#5d6876;--line:#dde2e9;--accent:#c2541b;--ok:#1d7a4a;--okbg:#e2f3ea;--warn:#a32f1a}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#10151b;--card:#18202a;--fg:#e7ecf2;--muted:#9aa5b3;--line:#2a3441;--accent:#f08a4b;--ok:#6fd39c;--okbg:#173326;--warn:#ff8a70;color-scheme:dark}}}}
:root[data-theme="dark"]{{--bg:#10151b;--card:#18202a;--fg:#e7ecf2;--muted:#9aa5b3;--line:#2a3441;--accent:#f08a4b;--ok:#6fd39c;--okbg:#173326;--warn:#ff8a70;color-scheme:dark}}
body{{background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,-apple-system,sans-serif}}
.wrap{{max-width:860px;margin:0 auto;padding-block:32px 60px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));display:grid;gap:16px}}
h1{{margin:0;font-size:28px}} .sub{{color:var(--muted);margin:0}}
.post{{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}}
.post header{{display:flex;gap:12px;align-items:center;padding:14px 16px;border-bottom:1px solid var(--line);flex-wrap:wrap}}
.post header div{{flex:1;min-width:180px}} .post small{{display:block;color:var(--muted)}}
.num{{font-weight:800;color:var(--accent);font-size:20px;min-width:28px}}
.state{{font-size:12px;padding:3px 10px;border-radius:99px;border:1px solid var(--line);color:var(--muted)}}
.state.ok{{background:var(--okbg);color:var(--ok);border-color:transparent}}
.strip{{display:flex;gap:6px;overflow-x:auto;padding:12px 16px}}
.strip img{{height:170px;width:auto;border-radius:6px;flex:none}}
.strip img:first-child{{outline:3px solid var(--accent);outline-offset:-3px}}
.txt{{padding:0 16px 16px}} .txt p{{margin:4px 0 12px}}
.lbl{{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}}
.link{{font-family:ui-monospace,Menlo,monospace;font-size:12px;color:var(--muted);word-break:break-all}}
.warn{{color:var(--warn);font-weight:600}}
h2{{margin:8px 0 4px;font-size:20px}}
.banner{{background:var(--card);border:1px solid var(--warn);color:var(--warn);border-radius:10px;padding:10px 14px;margin:0;font-weight:600}}
.tbl{{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:12px}}
table{{border-collapse:collapse;width:100%;min-width:640px;font-size:14px}}
th,td{{padding:9px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
th{{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:600}}
td small{{display:block;color:var(--muted)}} td.n{{text-align:right;font-variant-numeric:tabular-nums}}
.miss{{color:var(--warn);font-size:13px}} .ok-t{{color:var(--ok);font-size:13px}}
.tracker{{display:grid;gap:10px}}
</style>
<div class="wrap">
<h1>Threads Planner</h1>
{banner}
{tracker}
<h2>Posts for {week}</h2>
<p class="sub">{len(posts)} posts at 1:00 PM and 8:00 PM. The outlined photo is the cover. To change anything, tell Claude e.g. "post 3: use photo 5 as cover" or "post 7: change price to RM2,300". Say "approve all" when it looks right.</p>
{''.join(cards) or '<p>No posts queued.</p>'}
</div>"""
    out = os.path.join(QDIR, "review.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(page)
    print(out)


def cmd_approve(ids):
    q = load(QUEUE, {"posts": []})
    n = 0
    for p in q["posts"]:
        if p.get("status") == "queued" and (not ids or p["id"] in ids):
            if problems_for(p):
                print(f"skip {p['id']}: {problems_for(p)}")
                continue
            p["approved"] = True
            n += 1
    save(QUEUE, q)
    print(f"approved {n} posts")


def cmd_archive():
    q, h = load(QUEUE, {"posts": []}), load(HISTORY, {"posts": []})
    keep = [p for p in q["posts"] if p.get("status") in ("queued", "error")]
    moved = [p for p in q["posts"] if p not in keep]
    h["posts"].extend(moved)
    q["posts"] = keep
    save(HISTORY, h)
    save(QUEUE, q)
    print(f"archived {len(moved)} posts, {len(keep)} left in queue")


def read_env():
    env = {}
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                env[k] = v.strip().strip('"')
    return env


def cmd_report():
    token = os.environ.get("THREADS_TOKEN") or read_env().get("THREADS_TOKEN")
    if not token:
        sys.exit("Put THREADS_TOKEN=... in threads-autopost/.env to pull insights")
    rows, by_formula = [], {}
    posts = [p for p in all_posts() if p.get("status") == "posted" and p.get("post_id")]
    for p in posts[-40:]:
        url = (f"https://graph.threads.net/v1.0/{p['post_id']}/insights?"
               + urllib.parse.urlencode({"metric": "views,likes,replies,reposts,quotes,shares",
                                         "access_token": token}))
        try:
            data = json.loads(urllib.request.urlopen(url, timeout=30).read())["data"]
            m = {d["name"]: (d.get("values") or [{}])[0].get("value", d.get("total_value", {}).get("value", 0))
                 for d in data}
        except Exception as e:
            m = {"error": str(e)[:80]}
        p["insights"] = m
        rows.append(p)
        f = p.get("formula", "?")
        agg = by_formula.setdefault(f, [0, 0, 0, 0])
        agg[0] += 1
        agg[1] += m.get("likes", 0) or 0
        agg[2] += m.get("replies", 0) or 0
        agg[3] += m.get("shares", 0) or 0
    print("slot              listing                       formula             views likes repl share")
    for p in rows:
        m = p["insights"]
        print(f"{p['slot']:<17} {p['listing'][:29]:<29} {p.get('formula','')[:19]:<19} "
              f"{m.get('views','-'):>5} {m.get('likes','-'):>5} {m.get('replies','-'):>4} {m.get('shares','-'):>5}")
    print("\nAverage per formula (likes / replies / shares):")
    for f, (n, l, r, s) in sorted(by_formula.items(), key=lambda kv: -kv[1][1] / kv[1][0]):
        print(f"  {f:<22} {n} posts  {l/n:.0f} / {r/n:.1f} / {s/n:.1f}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    c, args = sys.argv[1], sys.argv[2:]
    {"scan": lambda: cmd_scan(), "photos": lambda: cmd_photos(args[0]), "slots": lambda: cmd_slots(*args[:1]),
     "validate": lambda: cmd_validate(), "review": lambda: cmd_review(), "approve": lambda: cmd_approve(args),
     "archive": lambda: cmd_archive(), "report": lambda: cmd_report()}.get(c, lambda: sys.exit(__doc__))()
