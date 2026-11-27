#!/usr/bin/env python3
"""Turn the short-lived Graph API Explorer token into a Page token that doesn't expire,
find the Instagram account linked to the Page, and save META_PAGE_TOKEN / FB_PAGE_ID /
IG_USER_ID to .env. Never prints a token.

Needs in .env: META_APP_SECRET, META_USER_TOKEN. App id and Page id come from config.json.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = os.path.join(ROOT, ".env")
G = "https://graph.facebook.com/v21.0"
cfg = json.load(open(os.path.join(ROOT, "config.json")))["reels"]


def env():
    e = {}
    for line in open(ENV, encoding="utf-8"):
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1); e[k] = v
    return e


def get(path, **p):
    try:
        return json.loads(urllib.request.urlopen(f"{G}/{path}?{urllib.parse.urlencode(p)}", timeout=30).read())
    except urllib.error.HTTPError as ex:
        sys.exit(f"Meta said: {ex.read().decode(errors='replace')[:400]}")


def save(values, drop=()):
    lines = [l for l in open(ENV, encoding="utf-8") if l.split("=", 1)[0] not in set(values) | set(drop)]
    lines += [f"{k}={v}\n" for k, v in values.items()]
    open(ENV, "w", encoding="utf-8").writelines(lines); os.chmod(ENV, 0o600)


e = env()
app_id, page_id = cfg["meta_app_id"], cfg["fb_page_id"]
long_user = get("oauth/access_token", grant_type="fb_exchange_token", client_id=app_id,
                client_secret=e["META_APP_SECRET"], fb_exchange_token=e["META_USER_TOKEN"])["access_token"]
perms = get("me/permissions", access_token=long_user).get("data", [])
granted = sorted(p["permission"] for p in perms if p.get("status") == "granted")
print("Permissions granted:", ", ".join(granted))
need = {"pages_manage_posts", "pages_read_engagement", "pages_show_list", "instagram_basic", "instagram_content_publish"}
if need - set(granted):
    print("MISSING:", ", ".join(sorted(need - set(granted))), "- add them in Graph API Explorer and generate the token again.")

pages = get("me/accounts", access_token=long_user, fields="id,name,access_token,instagram_business_account{id,username}").get("data", [])
page = next((p for p in pages if p["id"] == page_id), None) or \
       next((p for p in pages if p["name"] == cfg.get("fb_page_name")), None)
if not page:
    sys.exit(f"The token can't see Page {page_id}. Pages it can see: {[p['name'] for p in pages]}. "
             "In Graph API Explorer, make sure the Page is ticked when you approve.")
ig = page.get("instagram_business_account") or {}
if not ig:
    sys.exit("The Page has no linked Instagram business account visible to this token.")
dbg = get("debug_token", input_token=page["access_token"], access_token=f"{app_id}|{e['META_APP_SECRET']}")["data"]
exp = dbg.get("expires_at", 0)
save({"META_PAGE_TOKEN": page["access_token"], "FB_PAGE_ID": page["id"], "IG_USER_ID": ig["id"]}, drop=("META_USER_TOKEN",))
print(f"Saved. Page: {page['name']}. Instagram: @{ig.get('username')} (id {ig['id']}). "
      f"Page token {'never expires' if not exp else 'expires at ' + str(exp)}.")
