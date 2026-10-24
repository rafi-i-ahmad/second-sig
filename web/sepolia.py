"""The Safe{Wallet} panel: Second Sig as a custom Safe App, next to the real queue on Sepolia.

    Safe{Wallet} → Apps → Add custom app → http://localhost:8000/safe-app

The panel only reads. Owners propose, sign and execute in Safe{Wallet} with their own wallets; the
watcher (sepolia/watcher.py) judges each proposal and, on MATCH, attests the stamp on Sepolia, so
Safe{Wallet}'s execute passes the guard. Nothing here holds an owner key.

Proposals at the Safe's current nonce are judged as they appear (``SEPOLIA_AUTO``: ``live``, the
default, ``replay`` or ``off``); the panel streams each run on the same SSE jobs as the fork page.
Replay needs recorded forms for that very proposal; without them the models run and the page says
Live (invariant 11).
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from eth_utils import is_address, to_checksum_address
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from sepolia import chain
from sepolia.chain import SHORT_NAME, SepoliaUnavailable, redact
from sepolia.watcher import Entry, Watcher
from web.display import JOBS, Job, _amount, relay, show_backward, show_floor, show_forward, show_verdict

STATIC = Path(__file__).resolve().parent / "static" / "safe-app"
POLL_S = 15
ETHERSCAN = "https://sepolia.etherscan.io"
MANIFEST = {
    "name": "Second Sig",
    "description": "Rehearses each queued transaction, checks it against its note, and stamps only a match. "
                   "The Safe's guard refuses anything unstamped.",
    "iconPath": "icon.svg",
}
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET",
        "Access-Control-Allow-Headers": "X-Requested-With, content-type, Authorization"}

router = APIRouter()
_watcher: Watcher | None = None
_running: dict[str, str] = {}  # safeTxHash -> job id
_lock = threading.Lock()
_poller: threading.Thread | None = None


def _auto() -> str:
    mode = os.environ.get("SEPOLIA_AUTO", "live").strip().lower()
    return mode if mode in ("live", "replay", "off") else "live"


def watcher() -> Watcher:
    global _watcher, _poller
    with _lock:
        if _watcher is None:
            try:
                chain.safe_address()
                _watcher = Watcher()
            except SepoliaUnavailable as exc:
                raise HTTPException(503, str(exc)) from None
        if _poller is None and _auto() != "off":
            _poller = threading.Thread(target=_poll, daemon=True)
            _poller.start()
        return _watcher


def _unavailable(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    return HTTPException(503, redact(f"{type(exc).__name__}: {exc}"))


# --------------------------------------------------------------------------- jobs


def _start(h: str, live: bool, answer: dict[str, Any] | None = None) -> str:
    w = watcher()
    with _lock:
        if h in _running and not JOBS[_running[h]].done:
            return _running[h]
        job_id = uuid.uuid4().hex[:12]
        JOBS[job_id] = job = Job()
        _running[h] = job_id
    p = w.proposals.get(h)
    show = relay(job, bundle=lambda: w.bundles.get(h),
                 description=lambda: w.proposals[h].effective_description() if h in w.proposals else "",
                 book=p.address_book if p else chain.address_book())

    def emit(event: str, payload: Any) -> None:
        if event == "stamp":
            payload = payload | {"attest_link": f"{ETHERSCAN}/tx/{payload['attest_tx']}"}
        show(event, payload)

    def run() -> None:
        try:
            if answer is None:
                w.judge(h, live=live, emit=emit)
            else:
                w.answer(h, answer["owner"], answer["text"], live=live, emit=emit)
            job.push("stage", {"name": "done", "detail": ""})
        finally:
            job.done = True

    threading.Thread(target=run, daemon=True).start()
    return job_id


def _poll() -> None:
    """Judge new proposals at the current nonce as Safe{Wallet} queues them."""
    while True:
        try:
            w = _watcher
            if w is not None and _auto() != "off":
                nonce = chain.safe_reader(w.live).functions.nonce().call()
                for h in w.due(w.queue(nonce), nonce):
                    if h not in _running:
                        _start(h, live=_auto() == "live")
        except Exception:  # noqa: BLE001 - the panel shows state errors; the poller keeps going
            pass
        time.sleep(POLL_S)


# --------------------------------------------------------------------------- display


def _links(safe: str, h: str | None = None) -> dict[str, str]:
    out = {"safe_wallet": f"https://app.safe.global/home?safe={SHORT_NAME}:{safe}",
           "safe_etherscan": f"{ETHERSCAN}/address/{safe}"}
    if h:
        out["tx_safe_wallet"] = f"https://app.safe.global/transactions/tx?safe={SHORT_NAME}:{safe}&id=multisig_{safe}_{h}"
    return out


def _summary(t: Any, book: dict[str, str]) -> str:
    """What the bytes call, in a few words, for the queue row. Display only; never judged on."""
    names = {v: k for k, v in book.items()}
    to = to_checksum_address(t.to)
    who = "this Safe" if to == chain.safe_address() else names.get(to, f"{to[:6]}…{to[-4:]}")
    method = (t.data_decoded or {}).get("method") if isinstance(t.data_decoded, dict) else None
    kind = "delegatecall" if t.operation == 1 else "call"
    if method:
        return f"{method} → {who}" + (" (delegatecall)" if t.operation == 1 else "")
    if t.value and not t.data:
        return f"send {t.value / 1e18:g} ETH → {who}"
    return f"{kind} → {who}"


def _entry_view(e: Entry | None, head: int) -> dict[str, Any] | None:
    if e is None:
        return None
    left = _watcher.stamp_blocks_left(e, head) if _watcher else None
    return {"status": e.status, "decision": e.decision, "headline": e.headline, "detail": e.detail, "live": e.live,
            "judged_at": e.judged_at, "fork_block": e.fork_block, "attest_tx": e.attest_tx,
            "attest_block": e.attest_block, "blocks_left": left,
            "attest_link": f"{ETHERSCAN}/tx/{e.attest_tx}" if e.attest_tx else None}


# --------------------------------------------------------------------------- API


@router.get("/sepolia/api/state")
def state() -> dict[str, Any]:
    try:
        w = watcher()
        s = w.state()
    except Exception as exc:  # noqa: BLE001
        raise _unavailable(exc) from None
    try:
        w.fork.eth.block_number
        fork_ok = True
    except Exception:  # noqa: BLE001
        fork_ok = False
    s["balances"] = {"ETH": _amount(s["balances"]["ETH"], 18, "ETH"), "USDC": _amount(s["balances"]["USDC"], 6, "USDC")}
    s["fork_ok"] = fork_ok
    s["auto"] = _auto()
    s["links"] = _links(s["safe"]) | ({"guard_etherscan": f"{ETHERSCAN}/address/{s['guard']}"} if s["guard"] else {})
    return s


@router.get("/sepolia/api/queue")
def queue() -> dict[str, Any]:
    try:
        w = watcher()
        nonce = chain.safe_reader(w.live).functions.nonce().call()
        head = w.live.eth.block_number
        txs = w.queue(nonce)
    except Exception as exc:  # noqa: BLE001
        raise _unavailable(exc) from None
    book = chain.address_book()
    safe = chain.safe_address()
    rows = []
    for t in txs:
        e = w.entries.get(t.safe_tx_hash)
        job = _running.get(t.safe_tx_hash)
        rows.append({
            "safe_tx_hash": t.safe_tx_hash, "nonce": t.nonce, "note": t.note(),
            "confirmations": len(t.confirmations), "required": t.confirmations_required,
            "summary": _summary(t, book), "current": t.nonce == nonce,
            "entry": _entry_view(e, head),
            "job_id": job if job and not JOBS[job].done else None,
            "has_result": t.safe_tx_hash in w.results,
            "links": _links(safe, t.safe_tx_hash),
        })
    return {"nonce": nonce, "head": head, "rows": rows}


@router.get("/sepolia/api/result/{h}")
def result(h: str) -> dict[str, Any]:
    """The last run for this proposal in display form, for a row opened after it was judged."""
    w = watcher()
    res = w.results.get(h)
    e = w.entries.get(h)
    out: dict[str, Any] = {"entry": _entry_view(e, w.live.eth.block_number) if e else None}
    if res is not None:
        b = res.bundle
        book = res.proposal.address_book
        out["floor"] = show_floor(res.verdict.floor_hits)
        out["forward"] = show_forward(res.forward, b, book) if res.forward else None
        out["backward"] = show_backward(res.backward, b, book) if res.backward else None
        out["verdict"] = show_verdict(res)
        out["amendments"] = [a.model_dump() for a in res.proposal.amendments]
    return out


@router.post("/sepolia/api/judge/{h}")
def judge(h: str, live: bool = True) -> dict[str, str]:
    return {"job_id": _start(h, live)}


class AnswerIn(BaseModel):
    owner: str
    text: str


@router.post("/sepolia/api/answer/{h}")
def answer(h: str, body: AnswerIn, live: bool = True) -> dict[str, str]:
    if not is_address(body.owner) or not body.text.strip():
        raise HTTPException(422, "owner must be an address and the answer must not be empty")
    return {"job_id": _start(h, live, {"owner": to_checksum_address(body.owner), "text": body.text})}


# --------------------------------------------------------------------------- the Safe App itself


@router.get("/safe-app/manifest.json")
def manifest() -> JSONResponse:
    return JSONResponse(MANIFEST, headers=CORS)


@router.get("/safe-app/icon.svg")
def icon() -> FileResponse:
    return FileResponse(STATIC / "icon.svg", media_type="image/svg+xml", headers=CORS)


@router.get("/safe-app")
@router.get("/safe-app/")
def panel() -> FileResponse:
    return FileResponse(STATIC / "index.html")
