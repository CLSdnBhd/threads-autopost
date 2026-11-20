# Threads auto-poster

Posts property listings to Threads twice a day (1 PM and 8 PM Malaysia time) as a photo
carousel plus a self-reply with a WhatsApp link, in the style that works best on Threads
(see STYLE.md).

- `inbox/`: one folder per property (photos + details.txt). Stays on your Mac only.
- `queue/queue.json`: the approved posts for the week. `queue/photos/` holds the resized photos.
- `poster/post.py`: does the posting. GitHub Actions runs it (`.github/workflows/post.yml`).
- `tools/prep.py`: weekly prep helper (scan, photos, validate, review page, approve, report).
- `STYLE.md`: caption formulas. `WEEKLY.md`: the Sunday routine. `SETUP.md`: one-time setup.
