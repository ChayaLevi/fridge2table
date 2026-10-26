"""Inject the demo grocery delivery, off camera (docs/MAIL_DEMO_PLAN.md, D2).

    uv run python scripts/deliver_demo.py [--base URL] [--file data/demo_delivery.json]

Stands in for the mail pipeline: it posts the order to /admin/delivery for the household whose page
called the server last (the browser you are recording). That page notices it by itself within
NOTICE_POLL_SECONDS: the delivery card, the NEW items, then the agent's meal. Run it right after the
email lands in the Gmail inbox. Exit code 1 if the server refused.
"""

import argparse
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base", default="http://localhost:8000", help="app URL (default http://localhost:8000)")
    parser.add_argument("--file", type=Path, default=None,
                        help="an order JSON (default: the server's data/demo_delivery.json)")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    body = json.loads(args.file.read_text(encoding="utf-8")) if args.file else None
    r = httpx.post(f"{args.base.rstrip('/')}/admin/delivery", params={"household": "latest"}, json=body, timeout=60)
    if r.status_code != 200:
        print(f"refused: {r.status_code} {r.text[:300]}")
        return 1
    n = r.json()["notice"]
    print(f"{n['retailer']} #{n['order_id']}: added {', '.join(i['display_name'] for i in n['added'])}")
    print(f"skipped (not food): {', '.join(n['skipped']) or '-'} · out of stock: {', '.join(n['unavailable']) or '-'}"
          f" · unsure: {', '.join(n['uncertain']) or '-'}")
    print("The open page shows it on its next poll.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
