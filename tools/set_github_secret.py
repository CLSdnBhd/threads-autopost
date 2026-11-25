#!/usr/bin/env python3
"""Copy THREADS_TOKEN from .env into the GitHub repository's Actions secrets.

The value is encrypted on this Mac with the repository's public key (as GitHub
requires) and never printed. Uses the GitHub key already saved in Keychain.

  tools/.venv/bin/python tools/set_github_secret.py [SECRET_NAME]
"""
import base64
import json
import os
import subprocess
import sys
import urllib.request

from nacl import encoding, public

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
name = sys.argv[1] if len(sys.argv) > 1 else "THREADS_TOKEN"
repo = json.load(open(os.path.join(ROOT, "config.json")))["github_repo"]

value = os.environ.get(name)
for line in ([] if value else open(os.path.join(ROOT, ".env"), encoding="utf-8")):
    if line.startswith(name + "="):
        value = line.strip().split("=", 1)[1]
if not value:
    sys.exit(f"No {name} in .env")

cred = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n",
                      capture_output=True, text=True, cwd=ROOT).stdout
gh = next((l.split("=", 1)[1] for l in cred.splitlines() if l.startswith("password=")), None)
if not gh:
    sys.exit("No GitHub key in Keychain")


def call(method, path, body=None):
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/{path}", method=method,
                                 data=json.dumps(body).encode() if body else None,
                                 headers={"Authorization": f"Bearer {gh}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, (json.loads(r.read() or b"{}"))


_, key = call("GET", "actions/secrets/public-key")
box = public.SealedBox(public.PublicKey(key["key"].encode(), encoding.Base64Encoder()))
enc = base64.b64encode(box.encrypt(value.encode())).decode()
status, _ = call("PUT", f"actions/secrets/{name}", {"encrypted_value": enc, "key_id": key["key_id"]})
print(f"{name} saved to GitHub ({'created' if status == 201 else 'updated'}).")
