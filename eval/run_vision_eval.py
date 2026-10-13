"""Vision eval: recognition recall / hallucinations / latency on the labelled photo sets.

    uv run python eval/run_vision_eval.py --model deepseek-flash --tiles 1
    uv run python eval/run_vision_eval.py --model deepseek-flash --tiles 2 --sets path/to/other/sets

Each folder in --sets (default eval/fridges/) with a labels.json is one set (see eval/fridges/README.md).
Prints a markdown table (per set, per place, overall) and saves the results as JSON in --out.
- recall: labelled items found (matched with same_ingredient against the name or any alt)
- halluc/photo: predicted items matching no label, excluding items flagged uncertain, per photo
- latency/photo: mean wall time of one photo's recognition (its tiles run in parallel)
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
from app.llm import build_model, setup_observability  # noqa: E402
from app.tools.normalize import same_ingredient  # noqa: E402
from app.tools.recognize import recognize_images  # noqa: E402

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def score_set(labels: list[dict], predicted: list[tuple[str, bool]]) -> dict:
    """labels: [{"name", "alt"?}]; predicted: [(canonical name, uncertain)]. Returns counts."""

    def matches(pred: str, label: dict) -> bool:
        return any(same_ingredient(pred, n) for n in [label["name"], *label.get("alt", [])])

    found = [lab["name"] for lab in labels if any(matches(p, lab) for p, _ in predicted)]
    missed = [lab["name"] for lab in labels if lab["name"] not in found]
    halluc = [p for p, uncertain in predicted if not uncertain and not any(matches(p, lab) for lab in labels)]
    return {"labels": len(labels), "found": found, "missed": missed, "hallucinated": halluc}


def aggregate(rows: list[dict]) -> dict:
    labels = sum(r["labels"] for r in rows)
    photos = sum(r["photos"] for r in rows)
    latencies = [x for r in rows for x in r["latencies_s"]]
    return {
        "recall": len([f for r in rows for f in r["found"]]) / labels if labels else 0.0,
        "halluc_per_photo": sum(len(r["hallucinated"]) for r in rows) / photos if photos else 0.0,
        "latency_s": sum(latencies) / len(latencies) if latencies else 0.0,
        "photos": photos,
        "labels": labels,
    }


async def run_set(folder: Path, model, tiles: int) -> dict:
    spec = json.loads((folder / "labels.json").read_text(encoding="utf-8"))
    location = spec["location"]
    photos = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES)
    results = await recognize_images([(p, location) for p in photos], model=model, tiles=tiles)
    # merge the photos of one set by canonical name; an item counts as uncertain only if every reading was
    predicted: dict[str, bool] = {}
    for r in results:
        for it in r.items:
            uncertain = it.confidence < config.UNCERTAIN_THRESHOLD
            predicted[it.name] = predicted.get(it.name, True) and uncertain
    row = score_set(spec["items"], list(predicted.items()))
    row.update({
        "set": folder.name, "location": location, "photos": len(photos),
        "latencies_s": [round(r.latency_s, 2) for r in results],
        "predicted": [{"name": n, "uncertain": u} for n, u in predicted.items()],
    })
    return row


def table(rows: list[dict]) -> str:
    lines = ["| set | place | photos | recall | halluc/photo | latency/photo |", "|---|---|---|---|---|---|"]

    def line(name: str, place: str, agg: dict) -> str:
        return (f"| {name} | {place} | {agg['photos']} | {agg['recall']:.0%} ({round(agg['recall'] * agg['labels'])}"
                f"/{agg['labels']}) | {agg['halluc_per_photo']:.1f} | {agg['latency_s']:.1f} s |")

    for r in rows:
        lines.append(line(r["set"], r["location"], aggregate([r])))
    for place in ("fridge", "freezer", "pantry"):
        here = [r for r in rows if r["location"] == place]
        if here:
            lines.append(line(f"**all {place}**", place, aggregate(here)))
    lines.append(line("**overall**", "", aggregate(rows)))
    return "\n".join(lines)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=config.VISION_MODEL)
    parser.add_argument("--tiles", type=int, choices=(1, 2, 4), default=config.VISION_TILES)
    parser.add_argument("--sets", type=Path, default=ROOT / "eval" / "fridges")
    parser.add_argument("--out", type=Path, default=ROOT / "eval" / "results")
    args = parser.parse_args()
    setup_observability()

    folders = sorted(f for f in args.sets.iterdir() if (f / "labels.json").is_file())
    if not folders:
        print(f"No labelled sets in {args.sets} (each set needs a labels.json, see eval/fridges/README.md)")
        return 1
    model = build_model(args.model)
    start = time.perf_counter()
    rows = [await run_set(f, model, args.tiles) for f in folders]  # sets one by one; photos in parallel

    print(f"\nModel {args.model}, tiles={args.tiles}, {len(rows)} sets, {time.perf_counter() - start:.0f} s total\n")
    print(table(rows))
    print()
    for r in rows:
        print(f"{r['set']}: missed {r['missed'] or '-'}; hallucinated {r['hallucinated'] or '-'}")

    args.out.mkdir(parents=True, exist_ok=True)
    out = args.out / f"vision_{args.model}_t{args.tiles}_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps({
        "model": args.model, "tiles": args.tiles, "sets_dir": str(args.sets), "at": datetime.now().isoformat(),
        "overall": aggregate(rows), "sets": rows,
    }, indent=2), encoding="utf-8")
    print(f"\nSaved {out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
