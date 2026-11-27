# Weekly prep (Claude follows this every Sunday)

Working folder: `threads-autopost/`. Read `STYLE.md` and `config.json` first.

1. **Report on last week.** Run `python3 tools/prep.py report` and summarise for Calvin
   which posts and formulas got the most likes, replies and shares. Then run `python3 tools/prep.py archive`.
2. **Pick up new listings from WhatsApp.** Calvin sends photos and then a caption message to the group
   "Cal's PA Claude". Open it in WhatsApp with screen control, read the new captions, and tap download
   on the new photos. Then copy only the image files WhatsApp saved in the last ~30 min from
   `~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared/Message/Media/` (check they all sit in
   one chat folder). Sort them into `inbox/<listing>/` by looking at thumbnails, and write `details.txt`.
   Never read WhatsApp's chat database.
   **See what's available.** Run `python3 tools/prep.py scan`. Skip folders starting with `_`.
   Prefer listings that are new, then ones not posted in 10+ days. If there aren't enough listings
   for 14 posts, reuse listings with a different formula and cover, and tell Calvin to add more.
3. **Slots.** Run `python3 tools/prep.py slots` to get next week's 14 IDs and times.
4. **Photos.** For each listing used, look at the photos in `inbox/<folder>/`. Rename them if needed
   so the order follows STYLE.md (e.g. `01-view.jpg`, `02-living.jpg`…), then run
   `python3 tools/prep.py photos <folder>`. To give the same listing a different cover on a later
   post, reorder the `photos` list in that post's entry instead.
5. **Write posts** into `queue/queue.json` (schema below), following STYLE.md and rotating formulas.
   Facts come only from what Calvin gave for that listing: `details.txt`, a pasted WhatsApp message,
   a brochure PDF, or a screenshot of a price list or cheat sheet (open and read images and PDFs).
   Brochure pages, floor plans and price-list screenshots are never used as post photos.
   If a fact Calvin would want in the reply (price, rooms, tenure) is missing, ask instead of guessing.
6. **Check.** Run `python3 tools/prep.py validate` and fix anything marked BAD.
7. **Review page.** Run `python3 tools/prep.py review` and publish `queue/review.html` as an Artifact
   (same file path every week, so it stays at one link). Tell Calvin it's ready.
8. **On "approve all"** (or approval of specific posts): apply any edits, run
   `python3 tools/prep.py approve [ids]`, then commit and push:
   `git add -A && git commit -m "Week of <date>" && git push`.
   Posts only go out once they're approved **and** pushed.

## queue.json post schema

```json
{
  "id": "2026-11-24-am",
  "slot": "2026-11-24 13:00",
  "listing": "mont-kiara-3r2b",
  "formula": "Price surprise",
  "photos": ["queue/photos/mont-kiara-3r2b/01.jpg", "..."],
  "caption": "Hook line 🫶🏻\nBenefit line 🤍\n📍Mont Kiara, KL",
  "reply": "Mont Kiara, KL\nFreehold | 3 bedrooms 2 bathrooms 2 carparks\nSiap by 2029 ✅\nFrom RM___\nPM for more details 🫡 or WhatsApp terus 👇",
  "link": "https://wa.me/60175495418?text=Hi%20Calvin%2C%20saya%20nak%20tahu%20pasal%20Mont%20Kiara%203R2B%20(Threads)",
  "approved": false,
  "status": "queued"
}
```
The poster adds `post_id`, `reply_id`, `permalink`, `posted_at` and `error`.
Status values: `queued`, `posted`, `missed` (more than 10 h late), `error`.
