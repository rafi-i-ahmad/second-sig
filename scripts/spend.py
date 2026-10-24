"""Estimated Gemini spend from logs/calls.jsonl, by model and status.

The estimate uses judge.model.PRICES, which are assumptions; compare the total with AI Studio's
spend page and correct the table if they disagree. Lines logged before usage was recorded carry
no estimate and are counted as calls only.

    uv run python scripts/spend.py [--since 2026-10-24T17:00:00Z]

With no --since, GEMINI_SPEND_SINCE is used if set, otherwise the whole log.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

from judge import model as m


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--since", default=os.environ.get("GEMINI_SPEND_SINCE") or None)
    args = ap.parse_args(argv)
    start = m._parse_ts(args.since) if args.since else None

    rows: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    if m.LOG_PATH.exists():
        for raw in m.LOG_PATH.read_text(encoding="utf-8").splitlines():
            line = json.loads(raw)
            if start is not None and m._parse_ts(line["ts"]) < start:
                continue
            r = rows[(line.get("model") or "?", line.get("status") or "?")]
            r["calls"] += 1
            for k, v in (line.get("usage") or {}).items():
                r[k] += v
            r["usd"] += line.get("est_usd") or 0.0

    print(f"since {args.since or 'the start of the log'}")
    print(f"{'model':20s} {'status':12s} {'calls':>5s} {'input':>9s} {'output':>8s} {'thought':>8s} {'est USD':>8s}")
    for (model, status), r in sorted(rows.items()):
        print(f"{model:20s} {status:12s} {int(r['calls']):5d} {int(r['input']):9d} {int(r['output']):8d} "
              f"{int(r['thought']):8d} {r['usd']:8.3f}")
    total = sum(r["usd"] for r in rows.values())
    cap = os.environ.get("GEMINI_SPEND_CAP_USD")
    print(f"total est. ${total:.3f}" + (f" of a ${float(cap):.2f} cap" if cap else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
