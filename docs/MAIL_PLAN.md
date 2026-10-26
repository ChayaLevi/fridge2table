# Grocery email → inventory: full work plan

Written 2026-10-25 at the human's request, from the design note "Fridge-to-Table – plan for connecting email and updating inventory from orders" (Oct 25, 2026). It is a new phase after the Oct 23 demo. `docs/PRODUCT.md` §11 lists receipts and delivery apps as out of scope; this plan is the human's decision to add them. For the video-only version, see `docs/MAIL_DEMO_PLAN.md`; build that first, since it is the front half of this plan.

## Goal

The inventory updates itself from grocery orders: no photo, no typing. The agent reads order emails from a real inbox (read-only), works out when an order really arrived and what was actually in it (after missing items, substitutions and refunds), keeps only cooking ingredients, and updates the inventory. It decides on its own whether to apply silently with undo, ask, or suggest a meal from the delivery.

**In scope:** read-only access to one inbox; known retailer senders only; classifying each email into an order lifecycle stage; reconciling all emails of one order into the final delivered list; the cooking filter; mapping to canonical names; apply with undo; the decision layer; the app starting a conversation when a delivery lands.

**Out of scope for now:** sending or changing anything in the mailbox; placing orders or reordering; several households or login (one inbox per server); exact expiry dates; push notifications.

## Design rules (on top of `CLAUDE.md`)

1. **Email content is untrusted.** Classification and extraction run as separate LLM calls with structured output only, without tools and without inventory access. The main agent sees only the validated `ParsedEmail` data, never the email text.
2. **The LLM reads, the code decides what changed.** Reconciliation, the final list, the diff, filtering by known names and applying are deterministic Python with unit tests.
3. **Idempotent.** Each email is processed once (Message-ID). The final list is recomputed from the whole event log every time; it never accumulates. Applying means a diff against `applied_snapshot`, so a repeated or out-of-order email changes nothing.
4. **The user wins.** A manual panel edit of an item that came from an order is kept; a later correction changes only the difference.
5. **No email bodies are stored.** Only the Message-ID, type, order id and extracted lines are kept.
6. **Only Chinese models.** `RECIPE_MODEL`-class model (`deepseek-flash`) for classify / extract / relevance, through a new env var `MAIL_MODEL`.

## Pipeline

`Fetch → Dedupe → Classify → Extract → Reconcile → Filter → Map → Decide → Apply`

Classify, Extract and the Filter fallback use the LLM; Reconcile, Map and Apply are code. Every source (files, IMAP, Gmail API, a forwarding address) implements one interface: `MailSource.fetch_new(since) -> list[RawEmail]` (`message_id`, `sender`, `subject`, `date`, `html`, `text`).

## Phases and tasks

### M0 Email corpus 🧑 (2–3 days)
- 🧑 Pick 2–3 retailers for the demo (open question below) and collect at least 30 real emails covering every type: placed, modified (missing / substituted / weight), shipped, delivered, refund, cancelled, marketing.
- Anonymize them into `eval/mail/<retailer>/*.eml`, each with a golden `*.json` (type, order id, lines, line statuses, categories).
- **Done when:** the corpus covers every email type for each retailer; a test loads every fixture and validates its golden JSON against the schemas.

### M1 Classify and extract (4–5 days)
- `app/mail/models.py`: `RawEmail`, `EmailType`, `OrderLine`, `ParsedEmail` (as in the design note; `OrderLine` already exists from the demo's `data/demo_delivery.json`).
- `app/mail/sources.py`: `MailSource` + `FileMailSource` (a folder of `.eml`).
- `data/retailers.yaml`: per retailer, allowed sender domains, subject patterns per email type, category map, finality trigger (`shipped` or `delivered`), optional HTML table selectors.
- `app/mail/classify.py`, in layers: allowlist (everything else dropped before any model sees it) → YAML rules → schema.org `Order` / `ParcelDelivery` markup → LLM fallback (JSON: type, order id, confidence, reason; low confidence → `other` + needs review).
- `app/mail/extract.py`: schema.org `orderedItem` → per-retailer HTML parser (BeautifulSoup) → LLM with `ParsedEmail` output on cleaned text. Code checks afterwards: every `substitute_for` points to a line, totals / item counts match when present (a gap lowers confidence), a line without a readable name or qty goes to review.
- `eval/run_mail_eval.py`: accuracy report on the corpus.
- **Done when:** unit tests pass with mocked LLM calls; on the corpus, type accuracy ≥95% and line F1 (name + qty + status) ≥90%; an email whose text tells the model to delete the inventory gives a normal `ParsedEmail` and no other effect.

### M2 Order lifecycle, filter, map, apply (5–6 days)
- Tables in `app/store.py`: `processed_email`, `grocery_order`, `order_event`, `inventory_change`, `item_relevance_override` (as in the design note).
- `app/mail/orders.py`: the state machine (`placed → modified* → shipped → delivered`, `cancelled` from any state, `refund` / `return` after delivery); `final_lines(events)` recomputed from the log (missing → removed, substituted → replaced with a `substitute_for` link, weight → actual amount, refused at the door → removed); order matching by order id, otherwise retailer + date window + line overlap, marked uncertain.
- `app/mail/relevance.py`: `normalize()` known name → `cooking_ingredient`; retailer category via YAML; one batched LLM call for the rest; `item_relevance_override` remembers the user's answers. `ready_to_eat` is a per-household setting (open question).
- `app/mail/apply.py`: map to inventory (strip brand / pack size / marketing words, then `normalize()`; place by category, an existing item keeps its place; amount = qty × pack size per T6.3, added to a compatible existing amount, else plenty; staples only marked refreshed; a substitute goes in under its own name). Apply = diff between the new final list and `applied_snapshot`; a negative diff (refund) uses the "I made it" rule (exact subtract when units match, else one level down). Every apply writes an `inventory_change` row with an undo token.
- Upgrade the demo's `app/tools/delivery.py` to call these functions instead of reading one JSON.
- **Done when:** the 13 end-to-end scenarios in the design note pass on files (normal order applied once; missing not added; substitute in, original out; weighed amount; refund after delivery lowers it; cancel before shipping changes nothing; same email twice → no duplicate; delivered before shipped → same result; mixed order → only ingredients; marketing email skipped; injected instructions have no effect; manual edit then refund keeps the edit; no delivery email → one question after 48 h), plus cooking-filter precision ≥95% and recall ≥90% on the corpus.

### M3 Real inbox (3–4 days)
- **First choice: IMAP with an app password** (`imaplib` from the standard library, read-only `EXAMINE INBOX`, `SEARCH FROM <allowed domains> SINCE <last_sync>`). It works with Gmail (2-step verification + app password) and with QQ / 163 mailboxes, and needs no Google app review. `ImapMailSource` implements `MailSource`.
- Optional later: `GmailApiSource` (OAuth, `gmail.readonly`, Testing mode, query `from:(…)`, History API). Only if IMAP is not enough.
- A background poller started in the FastAPI `lifespan`: every `MAIL_POLL_SECONDS` (default 600) it runs the pipeline for `MAIL_HOUSEHOLD` (one household until there is login). Errors are logged, never crash the app.
- Secrets: the password / token encrypted at rest with a key from an env var (`MAIL_SECRET_KEY`); never in logs or traces. `mail_account` table: source, encrypted secret, last_sync, active.
- UI: "Connect email" (address + app password, or OAuth) and "Disconnect", which revokes / deletes the secret and deletes `processed_email` and the orders, while the inventory stays.
- Deployment: the free Render instance sleeps, and so does the poller. Keep it awake during the demo, or run locally. 🧑 Check that the server can reach `imap.gmail.com:993` (or the chosen provider).
- **Done when:** an email sent to the connected inbox updates the inventory within one poll interval; disconnect removes the secret and the orders; `LOG_LEVEL=DEBUG` shows each poll and each processed Message-ID, and no secret.

### M4 Decision layer and UX (4–5 days)
- Built on the demo's notices, banner and agent delivery message (`docs/MAIL_DEMO_PLAN.md` D3).
- **How to apply** (rules in code, thresholds in config): all lines high-confidence, known retailer, clear finality → silent apply + banner with undo; some `uncertain` or new name mappings → apply the sure ones + a confirmation card for the rest (the existing post-scan review card); uncertain order match or a clash with a manual edit → a card for the whole order, nothing applied; no delivery confirmation after 48 h from shipped (or 5 days from placed) → one question "Did the order from X arrive?".
- **Whether to suggest a meal now:** yes if the delivery makes a meal possible that was not before (`compute_missing` before vs after) during the household's usual deciding hours; higher priority if it completes a meal with a use-soon item; no if a proactive message was already sent today (budget: one per day) or the last suggestion was declined recently; otherwise keep it for the next opening ("From yesterday's delivery you can make…").
- New agent tool `get_recent_orders` (thin wrapper, plain function in `app/mail/`) for "what came in the last order?".
- Trace on every mail-driven change: "source: order from X, email of <date>".
- Metrics logged per household: undo rate of silent applies (above 10% means the threshold is too optimistic), manual fixes per order, share of delivery suggestions that led to "I made it".
- New scenarios in `eval/scenarios.yaml`: a delivery notice leads to a validated meal; "what came in the last order?" answered from `get_recent_orders`.
- **Done when:** the decision rules have unit tests for each row above; the new scenarios and the existing ones pass on real models; in a phone-size browser, a real email to the connected inbox produces the banner, the card for an uncertain item and, at the right time, the agent's meal message.

## Estimate

| Phase | Days |
|---|---|
| Demo plan first (`MAIL_DEMO_PLAN.md`) | ~2 |
| M0 corpus 🧑 | 2–3 |
| M1 classify + extract | 4–5 |
| M2 lifecycle + filter + apply | 5–6 |
| M3 real inbox (IMAP) | 3–4 |
| M4 decision + UX | 3–4 (the demo already built part of it) |
| **Total** | **about 3–4 weeks**, solo |

M0–M2 do not need a real inbox, so most of the value can be shown before any credentials are involved.

## Open questions 🧑

- Which retailers? They decide the corpus and the parsers. Chinese grocery apps (Hema, Meituan) mostly send app notifications, not email; JD and Western sites send detailed emails.
- IMAP or the Gmail API first? This plan assumes IMAP.
- Per retailer: is `shipped` or `delivered` the finality trigger?
- Does `ready_to_eat` (bread, yogurt, sliced cheese) go into the inventory?
- Is the opening message plus a banner enough, or is push needed?
- Internal demo only, or login before a real inbox is connected?
- Is there an order API (Hema, Meituan) that could replace email later?
