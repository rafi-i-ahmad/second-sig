"""What the demo pages see: judge results in display form, and the jobs that stream them.

Shared by the fork page (web/server.py) and the Safe{Wallet} panel (web/sepolia.py). Everything
here is already in display form; the pages compute nothing and insert text with textContent only,
because descriptions, notes and names are attacker-authorable (invariant 7).
"""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Any, Callable

from judge import model, pipeline
from judge.canon import Resolver, from_backward, from_forward, render_config, render_movement, render_permission
from judge.labeller import plain_address_book
from judge.schemas import Decision, EvidenceBundle, ExpectedEffects, FloorHit, Narration


class Job:
    def __init__(self) -> None:
        self.events: list[tuple[str, Any]] = []
        self.done = False
        self.lock = threading.Lock()

    def push(self, event: str, payload: Any) -> None:
        with self.lock:
            self.events.append((event, payload))


# Every running or finished job, by id; /api/jobs/{id}/events streams any of them
JOBS: dict[str, Job] = {}


def _short(addr: str) -> str:
    return f"{addr[:6]}…{addr[-4:]}"


def book_names(book: dict[str, str]) -> dict[str, str]:
    """address -> name, for the plain-name labels only (labeller.plain_address_book). A label the
    judge ignores is never shown as a name either; its address shows raw."""
    kept, _ = plain_address_book(book)
    return {a.lower(): name for name, a in kept.items()}


def _amount(base: int, decimals: int, symbol: str) -> str:
    whole = base / 10**decimals
    return f"{whole:,.0f} {symbol}" if whole == int(whole) else f"{whole:,.4f} {symbol}"


def _raw(bundle: EvidenceBundle, cites: list[str]) -> list[dict[str, Any]]:
    out = []
    for c in cites:
        e = bundle.entry(c)
        out.append({"id": c, "entry": e.model_dump(mode="json") if e is not None else None})
    return out


def show_floor(hits: list[FloorHit]) -> list[dict[str, Any]]:
    return [{"rule": h.rule, "reason": h.reason, "cites": h.cites} for h in hits]


def show_forward(fwd: ExpectedEffects, bundle: EvidenceBundle, book: dict[str, str]) -> dict[str, Any]:
    c = from_forward(fwd, bundle.description, Resolver(bundle, book))
    rows = ([{"kind": "move", "text": render_movement(m)} for m in c.movements]
            + [{"kind": "allow", "text": render_permission(p)} for p in c.permissions]
            + [{"kind": "config", "text": render_config(x)} for x in c.configs])
    return {"rows": rows, "nothing_else": fwd.nothing_else, "questions": list(fwd.questions_for_human),
            "assumptions": list(fwd.assumptions), "confidence": fwd.confidence}


def show_backward(bwd: Narration, bundle: EvidenceBundle, book: dict[str, str]) -> dict[str, Any]:
    c = from_backward(bwd, Resolver(bundle, book))
    order = {"critical": 0, "notable": 1, "info": 2}
    effects = sorted(c.effects, key=lambda e: order[e.severity])
    return {"effects": [{"sentence": e.sentence, "severity": e.severity, "cites": e.cites, "cited_ok": e.cited_ok,
                         "raw": _raw(bundle, e.cites)} for e in effects],
            "confidence": bwd.confidence}


# "forward gemini-3.8-flash 6487 ms <iid>"; the source reader adds "<n> tokens" before the id
_CALL = re.compile(r"^(?P<stage>\S+) (?P<model>\S+) (?P<ms>\d+) ms (?:\d+ tokens )?(?P<iid>\S+)$")


def _usage(iids: set[str]) -> dict[str, dict[str, Any]]:
    """Token usage and estimated cost per interaction id, from the adapter's log (logs/calls.jsonl)."""
    out: dict[str, dict[str, Any]] = {}
    if not iids or not model.LOG_PATH.exists():
        return out
    for raw in reversed(model.LOG_PATH.read_text(encoding="utf-8").splitlines()):
        try:
            line = json.loads(raw)
        except ValueError:
            continue
        iid = line.get("interaction_id")
        if iid in iids and iid not in out:
            out[iid] = {"usage": line.get("usage") or {}, "usd": line.get("est_usd")}
            if len(out) == len(iids):
                break
    return out


def show_calls(calls: list[str]) -> list[dict[str, Any]]:
    """The model calls a run made, with tokens and estimated cost where the log has them. Empty
    means no model was called: the forms were recorded (replay) or the floor decided first."""
    parsed = [(c, _CALL.match(c)) for c in calls]
    usage = _usage({m["iid"] for _, m in parsed if m})
    out = []
    for text, m in parsed:
        if not m:
            out.append({"stage": text.split(" ")[0], "text": text})
            continue
        u = usage.get(m["iid"], {})
        tokens = sum(v for k, v in u.get("usage", {}).items() if k in ("input", "output", "thought")) or None
        out.append({"stage": m["stage"], "model": m["model"], "ms": int(m["ms"]), "tokens": tokens, "usd": u.get("usd")})
    return out


_GAP = {"omission": "Omission", "contradiction": "Contradiction", "vague_description": "Vague description"}


def _why(res: pipeline.JudgeResult) -> list[str]:
    """Why the table did not say MATCH, for the reasons no row shows: an ASK can arrive with every
    item matched (the forward pass raised a question), and a failed rehearsal or missing form has
    no row. Drive the page from the decision, never from the rows."""
    v = res.verdict
    if v.decision == Decision.MATCH or v.floor_hits:
        return []
    shown = ("unexplained", "expected but not observed", "address-book label ignored")
    return [r[0].upper() + r[1:] for r in v.reasons if r and not r.startswith(shown)]


def _headline(res: pipeline.JudgeResult) -> str:
    q = res.question
    if q is not None:
        text = q.statement if res.verdict.decision == Decision.REJECT else q.question
        if text:
            return text.strip()
    return res.verdict.question or res.note


def show_verdict(res: pipeline.JudgeResult) -> dict[str, Any]:
    v, b = res.verdict, res.bundle
    rows: list[dict[str, Any]] = []
    if v.compare:
        rows += [{"state": "match", "text": m.observed, "detail": m.tier.replace("_", " ")} for m in v.compare.matched]
        typed = {tuple(u.cites) for u in v.compare.observed_unexplained if u.kind != "effect"}
        rows += [{"state": u.severity, "text": u.item, "detail": u.reason, "cites": u.cites}
                 for u in v.compare.observed_unexplained if u.kind != "effect" or tuple(u.cites) not in typed]
        rows += [{"state": "missing", "text": x, "detail": "promised in the words, not seen in the bytes"}
                 for x in v.compare.expected_unobserved]
    unlabelled = [w.id for w in b.storage_diff if not w.label]
    gap = res.question.gap_kind if res.question and v.decision == Decision.ASK else None
    return {
        "decision": v.decision.value,
        "note": res.note,
        "headline": _headline(res),
        "reasoning": v.reasoning,
        "gap": _GAP.get(gap or ""),
        "why": _why(res),
        "rows": rows,
        "ignored_labels": v.compare.ignored_labels if v.compare else [],
        "floor": show_floor(v.floor_hits),
        "source": {"explained": res.source_check, "raised": res.source_raised, "rejected": res.source_rejected,
                   "tokens": res.source_tokens, "unlabelled": unlabelled},
        "calls": show_calls(res.calls),
        "safe_tx_hash": b.safe_tx_hash,
        "fork_block": b.fork_block,
    }


def relay(job: Job, *, bundle: Callable[[], EvidenceBundle | None], description: Callable[[], str],
          book: dict[str, str], pace: float = 0.0) -> Callable[[str, Any], None]:
    """An ``emit(event, payload)`` for pipeline.judge and sepolia.watcher that pushes each stage to
    ``job`` in display form. ``bundle`` and ``description`` are read when a form arrives, because
    the rehearsal and the amendments may be newer than the job. ``pace`` is presentation only."""

    def emit(event: str, payload: Any) -> None:
        if pace:
            time.sleep(pace)
        if event == "stage":
            job.push("stage", payload if isinstance(payload, dict) else {"name": payload, "detail": ""})
        elif event == "floor":
            job.push("floor", show_floor(payload))
        elif event in ("forward", "backward"):
            b = bundle()
            if b is None:
                return
            b = b.model_copy(update={"description": description()})
            show = show_forward if event == "forward" else show_backward
            job.push(event, show(payload, b, book))
        elif event == "verdict":
            job.push("verdict", show_verdict(payload))
        else:  # mode, stamp, notice, error, amendments: already in display form
            job.push(event, payload)

    return emit
