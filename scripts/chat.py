"""Terminal chat with the real kitchen agent (T2.4).

Usage:
    uv run python scripts/chat.py                  # the app's database (DB_PATH), session "terminal"
    uv run python scripts/chat.py --demo           # in-memory demo inventory (fridge scanned, pantry not)
    uv run python scripts/chat.py --session s2 --debug

The session history is stored in the database (run_turn loads and saves it), so restarting with the same
--session continues the conversation. With --demo nothing on disk changes.

Commands:
    /photo <path> [<path> ...] [fridge|freezer|pantry]   attach photos to the next message (default: fridge)
    /inventory                                          print the inventory as the agent sees it
    /new                                                start a new session (preferences stay)
    /help, /quit
A line with only photos pending and no text (just Enter) sends the photos alone.
"""

import argparse
import asyncio
import logging
import shlex
import sys
import uuid
from pathlib import Path
from typing import get_args

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded  # noqa: E402
from pydantic_ai.messages import ModelMessagesTypeAdapter  # noqa: E402

from app import config  # noqa: E402
from app.agent import TurnResult, run_turn  # noqa: E402
from app.llm import setup_observability  # noqa: E402
from app.models import Location  # noqa: E402
from app.store import Store  # noqa: E402
from app.timing import format_steps  # noqa: E402
from app.tools.inventory import get_inventory, inventory_summary  # noqa: E402
from app.trace import format_trace  # noqa: E402

LOCATIONS: tuple[str, ...] = get_args(Location)
HELP = __doc__.split("Commands:")[1].rstrip()


def parse_photo_command(args: str) -> list[tuple[Path, Location]]:
    """`a.jpg "my photos/b.jpg" pantry` -> [(a.jpg, pantry), (b.jpg, pantry)]. Raises ValueError on a bad path."""
    tokens = [t.strip('"').strip("'") for t in shlex.split(args, posix=False)]
    place: Location = "fridge"
    if tokens and tokens[-1].lower() in LOCATIONS:
        place = tokens.pop().lower()  # type: ignore[assignment]
    if not tokens:
        raise ValueError("usage: /photo <path> [<path> ...] [fridge|freezer|pantry]")
    paths = [Path(t).expanduser() for t in tokens]
    for p in paths:
        if not p.is_file():
            raise ValueError(f"no such file: {p}")
    return [(p, place) for p in paths]


def show(turn: TurnResult, debug: bool) -> None:
    r = turn.reply
    print(f"\nagent: {r.message}")
    for i, meal in enumerate(r.meals, 1):
        uses = f"  uses: {', '.join(meal.uses_from_inventory)}" if meal.uses_from_inventory else ""
        print(f"  [{i}] {meal.name} ({meal.time_minutes} min, id {meal.id}){uses}")
    if r.substitutions:
        print("  substitutions: " + ", ".join(f"{s.use_instead} for {s.missing}" for s in r.substitutions))
    if r.shopping_list or r.check_first or r.substitutions:
        print(f"  to buy: {', '.join(r.shopping_list) or 'nothing'}")
    if r.check_first:
        print(f"  check your pantry first: {', '.join(r.check_first)}")
    for q in r.questions:
        print(f"  ? {q}")
    u = turn.usage
    print(f"trace ({len(turn.trace)} steps, {u.latency_s:.1f}s, {u.requests} requests, "
          f"{u.input_tokens} in / {u.output_tokens} out tokens):")
    print(format_trace(turn.trace))
    if debug:
        print("timing:")
        print(format_steps(turn.steps))
        print("messages:")
        print(ModelMessagesTypeAdapter.dump_json(turn.result.new_messages(), indent=2).decode())


async def repl(store: Store, session: str, debug: bool) -> None:
    pending: list[tuple[Path, Location]] = []
    print(f"session {session!r}. Type /help for commands, /quit to leave.")
    while True:
        prompt = f"you ({len(pending)} photo{'s' if len(pending) != 1 else ''} attached)> " if pending else "you> "
        try:
            line = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        cmd, _, rest = line.partition(" ")
        if cmd in ("/quit", "/exit"):
            return
        if cmd == "/help":
            print(HELP)
            continue
        if cmd == "/inventory":
            print(inventory_summary(get_inventory(store), store.load_scan_state()))
            continue
        if cmd == "/new":
            session = f"terminal-{uuid.uuid4().hex[:6]}"
            pending = []
            print(f"new session {session!r}")
            continue
        if cmd == "/photo":
            try:
                photos = parse_photo_command(rest)
            except ValueError as e:
                print(e)
                continue
            pending.extend(photos)
            print(f"attached {len(photos)} ({photos[0][1]}); type a message or press Enter to send")
            continue
        if line.startswith("/"):
            print(f"unknown command {cmd}; /help lists them")
            continue
        if not line and not pending:
            continue
        try:
            turn = await run_turn(store, session, line, pending)
        except (UnexpectedModelBehavior, UsageLimitExceeded) as e:
            print(f"!! the agent gave up on this turn: {type(e).__name__}: {e}")
            continue
        finally:
            pending = []
        show(turn, debug)


def main() -> None:
    p = argparse.ArgumentParser(description="Terminal chat with the kitchen agent.")
    p.add_argument("--session", default="terminal", help="session id (history is kept per session)")
    p.add_argument("--db", default=str(config.DB_PATH), help="database file (default: DB_PATH)")
    p.add_argument("--demo", action="store_true", help="use the in-memory demo inventory instead of the database")
    p.add_argument("--debug", action="store_true", help="print the timing and the full message list of each run")
    args = p.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except AttributeError:
        pass
    setup_observability()
    if args.demo:
        from try_recipes import demo_store
        store = demo_store()
        print("demo inventory (in memory): fridge scanned, pantry not; preference: kids dislike eggplant")
    else:
        store = Store(args.db)
        print(f"database {args.db}")
    # the trace and the usage line already say what the INFO logs say; DEBUG adds every tool call
    logging.getLogger("app.agent").setLevel(logging.DEBUG if args.debug else logging.WARNING)
    try:
        asyncio.run(repl(store, args.session, args.debug))
    finally:
        store.close()


if __name__ == "__main__":
    main()
