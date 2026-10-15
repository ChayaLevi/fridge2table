# Evaluation results

<!-- latency:begin -->
## Latency (T5.2), 2026-10-15, 12:30

agent deepseek-v4-pro, recipes deepseek-flash, vision deepseek-flash; thinking off; 5 sequential runs per case; photo cases use the stand-in photo `tests/fixtures/coffee.jpg`.

| Case | Runs | Median | Max | Target | Agent model | Recipe/vision model | Other | Agent calls | Final agent call | Retries |
|---|---|---|---|---|---|---|---|---|---|---|
| Photo -> inventory (1 photo) | 5 | 8.7 s | 8.8 s | < 30 s ✓ | 4.0 s | 2.6 s | 1.5 s | 2 | 2.3 s | 0 |
| Photo -> inventory (4 photos) | 5 | 10.4 s | 14.5 s | < 30 s ✓ | 4.0 s | 17.4 s | 0.0 s | 2 | 2.4 s | 0 |
| Opening (app opens) | 5 | 8.5 s | 9.8 s | < 25 s ✓ | 4.2 s | 3.9 s | 0.6 s | 2 | 1.8 s | 0 |
| Mode A, Only what I have | 5 | 10.9 s | 13.9 s | < 25 s ✓ | 5.5 s | 5.0 s | 0.7 s | 2 | 3.5 s | 0 |
| Mode A, Shopping OK | 5 | 10.5 s | 13.5 s | < 25 s ✓ | 3.9 s | 6.0 s | 0.5 s | 2 | 2.2 s | 0 |
| Mode B (lasagna) | 5 | 7.0 s | 8.0 s | < 25 s ✓ | 4.0 s | 2.6 s | 0.5 s | 2 | 2.6 s | 0 |
| Recipe steps (tap a card) | 5 | 2.8 s | 3.0 s | - | 0.0 s | 2.8 s | 0.0 s | 0 | 0.0 s | 0 |
<!-- latency:end -->

Reading the table: "Agent model" and "Recipe/vision model" are the summed seconds of those model calls; "Other" is the rest (code, tools, network). Vision calls for several photos run in parallel, so with 4 photos "Recipe/vision model" (summed) is larger than the total. "Final agent call" is the call that writes the reply. Regenerate the table with `uv run python eval/run_latency.py --repeat 5 --write` (it replaces only the block between the latency markers).

### Notes (T5.2, 2026-10-15)

- **The API's speed is the biggest factor.** The same cases measured at about 12:05 the same day (3 runs each, before the Mode B change below) took twice as long: one `deepseek-v4-pro` agent call took about 6 s instead of 2-2.5 s.

  | Case (12:05, slow API) | Median | Max |
  |---|---|---|
  | Photo -> inventory (1 / 4 photos) | 15.4 / 17.6 s | 17.1 / 18.4 s |
  | Opening | 20.2 s | 22.7 s |
  | Mode A, Only what I have / Shopping OK | 19.6 / 18.1 s | 20.3 / 21.7 s |
  | Mode B (lasagna), 3 agent calls then | 22.6 s | **29.4 s** (one output-check retry) |

  Every case met its target in both measurements except Mode B in the slow hour, which is what the change below fixes. Before the demo, run `eval/run_latency.py --only mode_a,mode_b` once to see which kind of hour it is.
- **Change: Mode B in 2 agent calls instead of 3.** `get_recipe` now returns the missing report (computed by code) with the recipe (`to_buy`, `check_first`), so the agent no longer calls `compute_missing` before replying. That saves one agent call (2-6 s): Mode B went from 22.6 s (median, slow hour) to 7.0 s (fast hour), and scenarios 4, 5 and 10 passed 3/3 each, with no beef-to-chicken swaps.
- **AGENT_MODEL stays `deepseek-v4-pro`.** With `deepseek-flash` an agent call takes about 1.5 s, and in the slow hour Mode A went 19.6 → 11.0 s and Mode B 22.6 → 9.5 s. The scenario suite passed 28/28 (2 runs), but the replies were worse in ways the suite does not catch: chicken instead of the beef in bolognese and lasagna (the instructions forbid exactly that, and pro has not done it since T4.2), and "Four creamy pasta options" when 3 are shown. Two of 3 Mode B runs also needed an output-check retry. Pro meets the targets, so the quality wins. Flash is the fallback if the demo-day API is slow: `set AGENT_MODEL=deepseek-flash`.
- **No streaming of the message text.** Time to first token of the final agent call is 1.2-2.3 s, and the whole call is 2-3.5 s (measured directly: 1.2-2.3 s first token, 2.3-3.4 s total, for a 7k-token request with a short tool-call answer). Streaming would show the sentence about 1 s earlier at best. The meal cards still need the whole reply, and it would need a streaming endpoint and page changes. Most of the wait is in the tools (recipe model 3-6 s) and the first agent call, which streaming does not shorten.
- `suggest_meals` keeps `n=5`: the recipe call is 4-6 s, and fewer candidates would mean more "fewer than 1 passed" second calls.
