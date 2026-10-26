# Grocery email → inventory: demo-only plan (for the video)

Written 2026-10-25 at the human's request. The full feature is in `docs/MAIL_PLAN.md`; this is the short version for the video and the demo only.

**Status (2026-10-26): D1–D3 built, D4 script built; the Gmail recording (🧑) is open.** Changes from the plan below: the retailer is **Leafline Market** (FreshMart is a real chain name); the delivery shows as a **card in the chat** (what came in, substitution, out of stock, not food, unsure, Undo, "Show in my kitchen") instead of a banner on the panel, because on a phone the panel is a drawer; the new items are marked **NEW** and listed first in the panel; the uncertain item uses the panel's existing orange ✓ / × row; `/admin/delivery?household=latest` targets the household whose page called last, so `scripts/deliver_demo.py` needs no cookie. See the 2026-10-26 entry in `docs/PROGRESS.md`.

## What the video shows, and what is faked

The video should show this: a grocery delivery email lands in a real Gmail inbox. A few seconds later the app reacts **on its own**: the inventory updates, a banner shows what was added, and the agent writes in the chat, without any click, to suggest a meal the delivery made possible.

What is real and what is faked:

| Part | In this demo |
|---|---|
| The email in Gmail | **Real.** An HTML email from a made-up retailer, sent to a demo Gmail inbox and screen-recorded there. |
| Mail → app connection | **Faked.** The app never reads the inbox. The delivery is injected off camera (a script or `/docs`). |
| Parsing the email | **Faked.** The order lines are a hand-written JSON file that matches the email. |
| Filtering, mapping, applying, undo | **Real code**, deterministic, the same code the full feature will use. |
| The app noticing by itself | **Real.** The page polls for notices, so nobody clicks anything on camera. |
| The agent's meal suggestion | **Real.** The agent runs with the delivery as context and goes through the usual output validator. |

No inbox access, no OAuth, no LLM parsing. The demo is deterministic, so retakes come out the same.

## The story (it fits the existing demo seed)

The seed (`data/demo_seed.json`) has spinach marked "use soon" and no ricotta. The order from **Leafline Market** (made up, order #LL-4821) brings ricotta and lasagna sheets, so a spinach lasagna becomes possible.

Order lines in the email and in the JSON (verify each name with `normalize()` while building):

| Line in email | Status | What the app does |
|---|---|---|
| Ricotta 500 g | delivered | added, 500 g |
| Lasagna sheets 500 g | delivered | added, 500 g |
| Tomatoes 1 kg | delivered | added, 1 kg |
| Chicken breast ~1 kg | weighed 0.86 kg | added, 0.86 kg (actual weight) |
| Parmesan 200 g | substituted with Grana Padano 200 g | Grana Padano added, not parmesan |
| Heavy cream 500 ml | out of stock | not added |
| Fresh basil | delivered | added, plenty |
| "Nonna's Secret Sauce" | delivered | uncertain → asked in the banner |
| Toilet paper 12 pack | delivered | skipped (non-food) |
| Cat food 2 kg | delivered | skipped (non-food) |
| Dish soap | delivered | skipped (non-food) |

## Tasks

### D1 Demo assets (about 0.5 day)
- `demo/mail/leafline_delivered.html`: the email ("Your Leafline order #LL-4821 was delivered") with the table above, showing the substitution, the missing item and the weighed item the way real retailers do. Made-up brand and logo, nothing that looks like a real chain.
- `data/demo_delivery.json`: the same order as structured lines (`raw_name`, `qty`, `pack_size`, `pack_unit`, `line_status`, `substitute_for`, `retailer_category`), so it already matches the `OrderLine` schema from `docs/MAIL_PLAN.md`.
- 🧑 A demo Gmail inbox (e.g. a new account) and a way to send the email to it: paste the HTML into a send tool, or have Claude send it. The human records the inbox.
- **Done when:** the email renders well in Gmail on desktop and phone; the JSON matches the email line by line.

### D2 Apply a delivery + notice (about 0.5 day)
- `app/tools/delivery.py` (plain functions with unit tests, like the other tools):
  - `final_lines(lines)`: drops `missing` lines, replaces a substituted line with its substitute, uses the actual weight.
  - `classify_line(line)`: `cooking_ingredient` if `normalize()` knows the name or the retailer category is a food one, `non_food` for a small fixed list of categories and words (household, pet, toiletries, paper, soap…), else `uncertain`.
  - `apply_delivery(store, order)`: applies the cooking ingredients through the existing `inventory.mark_bought` (amount = qty × pack size when the unit is supported, else plenty; staples only marked refreshed), with one undo token. It returns added / skipped / uncertain.
- A pending **notice** in the store (a small table or a JSON row): retailer, order id, added, skipped, uncertain, undo token, created_at, seen.
- `POST /admin/delivery` (demo only, next to `/admin/seed`) loads `data/demo_delivery.json`, or a body if one is given, and runs `apply_delivery`. `GET /notices` returns unseen notices; `POST /notices/{id}/seen`.
- `scripts/deliver_demo.py`: calls `/admin/delivery` for the recording browser's household. You run it off camera, right after the email is sent.
- **Done when:** unit tests pass (missing not added, substitute added instead of the original, weighed amount used, non-food skipped, uncertain reported, undo restores everything); after `/admin/reset` + `/admin/seed` + `/admin/delivery`, `GET /inventory` shows ricotta 500 g, grana padano and chicken 0.86 kg, and no cream, toilet paper or cat food.

### D3 The app reacts by itself (about 0.5–1 day)
- The page polls `GET /notices` every 5 s (an env var for the interval, `NOTICE_POLL_SECONDS`).
- On a new notice:
  - A banner on the inventory panel: "📦 Leafline delivery: added 8 items · skipped 3 non-food · Undo". New rows are highlighted for a moment, and "Nonna's Secret Sauce" gets the existing keep / rename / remove card.
  - The agent writes in the chat by itself. This reuses the opening runner (T4.1) with a system note listing what arrived, so it suggests one validated meal that uses the delivery and the use-soon spinach ("Your Leafline order arrived: with the ricotta and lasagna sheets you can make a spinach lasagna tonight. Want the recipe?"). The trace line reads "source: Leafline Market order #LL-4821 (email)".
  - The notice is marked seen. If the page was closed, the next opening shows it.
- **Done when:** with the page open in a phone-size browser, running `scripts/deliver_demo.py` makes the banner and the agent message appear within about 10 s with no click; Undo removes the delivery; the meal passes the validator.

### D4 Recording (about 0.5 day)
- Add a `--delivery` scene to `scripts/record_demo.py`: reset, seed, open the chat, wait, inject the delivery, wait for the banner and the agent message, open the recipe, I made it.
- 🧑 Record the Gmail side: the inbox, the email arriving, opening it. In the edit, cut from the opened email to the app updating.
- **Done when:** two takes in a row run cleanly; only the final video goes in `demo/videos` (`*-silent.mp4`).

## Total

About **2 days**. No change to the agent's tools and nothing that the full plan would throw away: `delivery.py`, the notices, the banner and the agent's delivery message are the front half of `docs/MAIL_PLAN.md`. Only `/admin/delivery` and the hand-written JSON get replaced, by the real mail pipeline.

## What to say in the demo, honestly

"In this demo the email is real but the connection is staged: the list is fed in as if the mail pipeline read it. Everything after that, the filtering, the inventory update, undo and the meal suggestion, is the real code." The plan for the real connection is `docs/MAIL_PLAN.md`.
