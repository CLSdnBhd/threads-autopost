#!/usr/bin/env python3
"""Rebuild the campaign page calendar from the live reels queue.

  python3 build.py            # updates index.html in place, prints a summary
  python3 build.py --check    # prints the summary only
  python3 build.py --page /path/to/page.html   # rebuild a page saved elsewhere (cloud routine)

Sources:
  ../threads-autopost/queue/reels.json  (what is posted / approved / queued)
  plan.json                             (page wording per queue id + planned rows not queued yet)
Prints "CHANGED" or "UNCHANGED" on the last line so a scheduled task knows whether to republish.
"""
import datetime as dt
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
def _arg(name, default):
    if name in sys.argv:
        return sys.argv[sys.argv.index(name) + 1]
    return default


_q1 = os.path.join(HERE, "..", "threads-autopost", "queue", "reels.json")  # Mac layout
_q2 = os.path.join(HERE, "..", "queue", "reels.json")  # inside the threads-autopost repo (campaign/)
QUEUE = _arg("--queue", _q1 if os.path.exists(_q1) else _q2)
PAGE = _arg("--page", os.path.join(HERE, "index.html"))
PLAN = os.path.join(HERE, "plan.json")
START = dt.date(2026, 11, 27)  # campaign day 1 (Fri)
WEEK_NAMES = ["Launch", "Trust", "Listings", "Your clips", "Holidays", "New year"]
PILLAR = {"education": "edu", "listing": "list", "listings": "list", "recruitment": "recruit",
          "recruit": "recruit", "bts": "bts", "behind": "bts", "engagement": "engage", "poll": "engage"}


def cat_for(p):
    pl = (p.get("pillar") or "").lower()
    for k, v in PILLAR.items():
        if k in pl:
            return v
    t = (p.get("title") or "").lower()
    if "recruit" in t or '"join"' in p.get("caption", "").lower():
        return "recruit"
    if "loft park 0" in t:
        return "edu"
    return "list"


def cta(p):
    m = re.search(r'DM(?: aku)? ["“]([A-Z0-9]+)["”]', p.get("caption", ""))
    return f'CTA: DM "{m.group(1)}".' if m else ""


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")) if s else s


def main():
    q = json.load(open(QUEUE, encoding="utf-8"))
    plan = json.load(open(PLAN, encoding="utf-8"))
    over = plan.get("overrides", {})
    rows = []
    taken = set()
    for p in q["posts"]:
        st = p.get("status")
        if st in ("skipped", "cancelled", "removed"):
            continue
        o = over.get(p["id"], {})
        slot = dt.datetime.strptime(p["slot"], "%Y-%m-%d %H:%M")
        date = dt.date.fromisoformat(o["date"]) if o.get("date") else slot.date()
        res = p.get("results") or {}
        if st == "posted":
            status = "posted"
            times = sorted(r.get("posted_at", "") for r in res.values() if r.get("status") == "posted")
            t0 = dt.datetime.strptime(times[0], "%Y-%m-%d %H:%M").strftime("%-I:%M%p").lower() if times else ""
            note = f"Posted {t0} on Facebook + Instagram. " + cta(p)
        elif st == "partial":
            status = "posted"
            ok = [k.title() for k, r in res.items() if r.get("status") == "posted"]
            note = f"Posted on {', '.join(ok)}; retrying the rest. " + cta(p)
        elif st == "error":
            status = "make"
            note = "Failed to post. Claude to check. " + cta(p)
        else:
            status = "ready" if p.get("approved") else "make"
            note = o.get("note") or cta(p)
        if st in ("posted", "partial"):
            note = note.strip()
        else:
            note = o.get("note") or note
        title = o.get("title") or re.sub(r"\s*\(.*?\)\s*$", "", p.get("title", ""))
        rows.append((date, o.get("cat") or cat_for(p), title, note, status))
        taken.add(date)
    for r in plan.get("planned", []):
        d = dt.date.fromisoformat(r["date"])
        if d in taken:
            continue
        rows.append((d, r["cat"], r["title"], r["note"], r["status"]))
    rows.sort(key=lambda r: (r[0], {"posted": 0, "ready": 1, "make": 2, "film": 3}[r[4]]))

    weeks = {}
    for r in rows:
        weeks.setdefault((r[0] - START).days // 7, []).append(r)
    W = []
    for i in sorted(weeks):
        a = START + dt.timedelta(days=7 * i)
        b = a + dt.timedelta(days=6)
        name = WEEK_NAMES[i] if i < len(WEEK_NAMES) else "More"
        W.append({"t": f"Week {i + 1} · {name}", "r": f"{a.day} {a:%b} – {b.day} {b:%b}",
                  "d": [[f"{d:%a} {d.day} {d:%b}", c, esc(t), esc(n), s] for d, c, t, n, s in weeks[i]]})

    n = {k: sum(1 for r in rows if r[4] == k) for k in ("posted", "ready", "make", "film")}
    covered = {r[0] for r in rows if r[4] in ("ready", "posted")}
    last_ready = START  # last night of the unbroken approved run from day 1 (gaps break it)
    while last_ready + dt.timedelta(days=1) in covered:
        last_ready += dt.timedelta(days=1)
    later = sorted(d for d in covered if d > last_ready)
    plus = f" (plus {', '.join(str(d.day) for d in later[:-1])}{' and ' if len(later) > 1 else ''}{later[-1].day} {later[-1]:%b})" if later else ""
    today = dt.datetime.utcnow() + dt.timedelta(hours=8)
    block = f'''  <p class="lead">Started 27 Nov. One reel a day at 8pm. {n["posted"]} posted so far, and every night up to {last_ready.day} {last_ready:%b} is approved{plus}. After that the reels are made or planned and wait for your weekly approval. Listing reels never name the development, only the area. Your-clip days stay open until you send clips. <i>Auto-updated {today:%-d %b, %-I:%M%p}.</i></p>
  <div class="grid counts">
    <div class="tile"><div class="n" style="color:var(--edu)">{n["posted"]}</div><div class="l">Posted</div></div>
    <div class="tile"><div class="n" style="color:var(--ready)">{n["ready"]}</div><div class="l">Approved · posts automatically (to {last_ready.day} {last_ready:%b})</div></div>
    <div class="tile"><div class="n" style="color:var(--make)">{n["make"]}</div><div class="l">Next up · approve each Sunday</div></div>
    <div class="tile"><div class="n" style="color:var(--film)">{n["film"]}</div><div class="l">Days waiting for your clips</div></div>
  </div>
'''
    s = open(PAGE, encoding="utf-8").read()
    old = s
    s = re.sub(r"<!--CAL-START-->\n.*?<!--CAL-END-->", lambda m: "<!--CAL-START-->\n" + block + "<!--CAL-END-->", s, flags=re.S)
    s = re.sub(r"const W=\[.*?\];\n", lambda m: "const W=" + json.dumps(W, ensure_ascii=False).replace("<", "\\u003c") + ";\n", s, count=1, flags=re.S)
    s = re.sub(r'Updated [^<]*? · live since', f"Updated {today.day} {today:%b} · live since", s)
    strip = lambda x: re.sub(r"<i>Auto-updated.*?</i>|Updated \d+ \w+ · ", "", x)
    changed = strip(s) != strip(old)
    print(f"posted {n['posted']} · approved {n['ready']} (to {last_ready:%d %b}) · to approve {n['make']} · your clips {n['film']}")
    if changed and "--check" not in sys.argv:
        open(PAGE, "w", encoding="utf-8").write(s)
    print("CHANGED" if changed else "UNCHANGED")


if __name__ == "__main__":
    main()
