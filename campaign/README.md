# Campaign page refresh

`build.py` rebuilds the Cari Calvin campaign page calendar (a private claude.ai artifact) from `queue/reels.json` + `plan.json`.
A cloud routine runs it at 9:15am and 9:15pm MYT and republishes the page when something changed.
When queuing a reel, add its page wording to `plan.json` → `overrides` (area only, never the development name).
