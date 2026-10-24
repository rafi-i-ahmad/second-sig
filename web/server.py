"""The demo page's server: the three scenarios, the judge as an event stream, and the real chain.

    uv run uvicorn web.server:app --port 8000        # anvil must be running (NOTES.md)

The server owns the fork, the owners' test keys and (through judge/stamp.py) the judge key; the
page owns nothing and computes nothing. Everything sent to the page is already in display form.

Replay is the default (invariant 11): recorded forms from fixtures/outputs/, no model call, and the
page says so. With replay the events are paced so the cards fill one after another; that pacing is
presentation only and the stage line reads "replay". ``live=true`` calls the models.

The bundle: with replay, the recorded bundle is used when the Safe's nonce on the fork still equals
the bundle's (its recorded forms cite its entry ids); otherwise the bytes are rehearsed on the fork
now, which is code only, no model.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from eth_utils import keccak, to_checksum_address
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from contracts.setup import (
    FORK_BLOCK, OWNERS, THRESHOLD, connect, ensure_guard, ensure_safe, judge_address, rpc,
)
from judge import pipeline
from judge.run_fixture import ensure_usdc
from judge.schemas import Decision, EvidenceBundle
from web import sepolia
from web.display import JOBS, Job, _amount, _short, relay, show_backward, show_forward, show_verdict

STATIC = Path(__file__).resolve().parent / "static"
REPLAY_PACE_S = 0.7

USDC = to_checksum_address("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
AUSDC = to_checksum_address("0x98C23E9d8f34FEFb1B7BD6a91B7FF122F4e16F5c")
BALANCE_OF_ABI = [{"type": "function", "name": "balanceOf", "stateMutability": "view",
                   "inputs": [{"name": "a", "type": "address"}], "outputs": [{"type": "uint256"}]}]

SCENARIOS: dict[str, dict[str, str]] = {
    "bybit": {
        "case": "demo_bybit",
        "title": "Bybit replay",
    },
    "aave": {
        "case": "demo_aave",
        "title": "Aave deposit",
    },
    "auditor": {
        "case": "demo_auditor",
        "title": "Auditor payment",
    },
}

GUARD_ERRORS = [
    "SecondSig__NoStamp(bytes32)", "SecondSig__StaleStamp(bytes32,uint64)", "SecondSig__BadSignature()",
    "SecondSig__WrongSigner(address)", "SecondSig__WrongJudgeVersion(bytes32)",
    "SecondSig__OverrideNotReady(bytes32,uint256)", "SecondSig__NotSafe(address)",
]
SELECTORS = {"0x" + keccak(text=sig)[:4].hex(): sig for sig in GUARD_ERRORS}
GUARD_ERROR_TEXT = {
    "SecondSig__NoStamp": "the guard found no stamp for this exact transaction",
    "SecondSig__StaleStamp": "the stamp is older than 100 blocks",
}


# --------------------------------------------------------------------------- state


class Demo:
    """One fork, one Safe, one guard, and the latest result per scenario."""

    def __init__(self) -> None:
        self.w3 = None
        self.safe = None
        self.guard = None
        self.snapshot: str | None = None
        self.results: dict[str, pipeline.JudgeResult] = {}
        self.proposals: dict[str, pipeline.Proposal] = {}
        self.chain_lock = threading.Lock()

    def connect(self) -> None:
        self.w3 = connect()
        self.safe = ensure_safe(self.w3, quiet=True)
        self.guard = ensure_guard(self.w3, self.safe)
        ensure_usdc(self.w3, self.safe.address)  # the recorded bundles assume 10,000 USDC in the Safe
        self.snapshot = rpc(self.w3, "evm_snapshot", [])

    def ready(self) -> None:
        if self.w3 is None:
            try:
                self.connect()
            except SystemExit as exc:  # contracts.setup exits when anvil is not reachable
                raise HTTPException(503, "anvil is not reachable on the fork RPC; start it (NOTES.md)") from exc


demo = Demo()
app = FastAPI(title="Second Sig demo")


def _case(scenario: str) -> dict[str, Any]:
    if scenario not in SCENARIOS:
        raise HTTPException(404, f"unknown scenario {scenario}")
    (path,) = (pipeline.FIXTURES / "cases").glob(f"*/{SCENARIOS[scenario]['case']}.json")
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- the judge, as a job


def _bundle_for(case: dict[str, Any], live: bool, job: Job) -> EvidenceBundle:
    nonce = demo.safe.functions.nonce().call()
    recorded = pipeline.recorded_bundle(case["id"])
    if not live and recorded is not None and recorded.safe_tx.nonce == nonce:
        job.push("stage", {"name": "rehearsing", "detail": f"recorded rehearsal at Safe nonce {nonce}"})
        return recorded
    job.push("stage", {"name": "rehearsing", "detail": f"running the bytes on a fork snapshot at nonce {nonce}"})
    with demo.chain_lock:
        return pipeline.rehearse(case, demo.w3)


def _stamp(res: pipeline.JudgeResult, job: Job) -> None:
    job.push("stage", {"name": "stamping", "detail": "signing the EIP-712 stamp with the judge key"})
    with demo.chain_lock:
        sig = pipeline.sign_stamp(res, demo.w3, demo.guard.address)
        rcpt = pipeline.attest(res, demo.w3, demo.guard, OWNERS[2].address)
    job.push("stamp", {"judge": judge_address(), "fork_block": res.stamp.forkBlock, "signature": sig,
                       "safe_tx_hash": res.stamp.safeTxHash, "attest_tx": rcpt["transactionHash"].to_0x_hex(),
                       "attest_block": rcpt["blockNumber"]})


def _run(job: Job, scenario: str, live: bool, answer: dict[str, Any] | None = None) -> None:
    pace = 0.0 if live else REPLAY_PACE_S
    try:
        case = _case(scenario)
        job.push("mode", {"live": live})
        bundle = _bundle_for(case, live, job)
        if answer is None:
            proposal = pipeline.Proposal.from_case(case)
        else:
            proposal = demo.proposals.get(scenario) or pipeline.Proposal.from_case(case)
        demo.proposals[scenario] = proposal
        book = proposal.address_book
        emit = relay(job, bundle=lambda: bundle, description=proposal.effective_description, book=book, pace=pace)

        if answer is None:
            res = pipeline.judge(proposal, bundle, replay=not live, emit=emit)
        else:
            # The owner's words amend the description; the bytes and the backward form stay (pipeline.answer).
            res = pipeline.answer(proposal, OWNERS[answer["owner"]].address, answer["text"], bundle, demo.w3,
                                  backward_form=pipeline.recorded_backward(case["id"]) if not live else None,
                                  replay=not live, emit=emit)
            job.push("amendments", [a.model_dump() for a in proposal.amendments])
        demo.results[scenario] = res
        if res.verdict.floor_hits and not live:
            # The floor decided before any model ran. For the audience, show the recorded forms as
            # reference only; they did not and could not change the verdict.
            b = res.bundle
            note = "Recorded form, shown for reference: the floor decided before any model ran."
            if (f := pipeline.recorded_forward(case["id"])) is not None:
                job.push("forward", show_forward(f, b, book) | {"note": note})
            if (w := pipeline.recorded_backward(case["id"])) is not None:
                job.push("backward", show_backward(w, b, book) | {"note": note})
        if pace:
            time.sleep(pace)
        job.push("verdict", show_verdict(res))
        if res.verdict.decision == Decision.MATCH:
            _stamp(res, job)
        job.push("stage", {"name": "done", "detail": ""})
    except Exception as exc:  # noqa: BLE001 - the page shows it and offers replay
        replayable = pipeline.recorded_forward(SCENARIOS.get(scenario, {}).get("case", "")) is not None
        job.push("error", {"message": f"{type(exc).__name__}: {exc}", "replay_available": replayable and live})
    finally:
        job.done = True


def _start(scenario: str, live: bool, answer: dict[str, Any] | None = None) -> dict[str, str]:
    demo.ready()
    _case(scenario)
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = job = Job()
    threading.Thread(target=_run, args=(job, scenario, live, answer), daemon=True).start()
    return {"job_id": job_id}


# --------------------------------------------------------------------------- endpoints


@app.get("/api/state")
def state() -> dict[str, Any]:
    demo.ready()
    w3, safe = demo.w3, demo.safe
    usdc = w3.eth.contract(address=USDC, abi=BALANCE_OF_ABI)
    ausdc = w3.eth.contract(address=AUSDC, abi=BALANCE_OF_ABI)
    return {
        "chain_id": w3.eth.chain_id,
        "fork_block": FORK_BLOCK,
        "head_block": w3.eth.block_number,
        "safe": safe.address,
        "safe_version": "1.4.1",
        "owners": [o.address for o in OWNERS],
        "threshold": THRESHOLD,
        "nonce": safe.functions.nonce().call(),
        "guard": demo.guard.address,
        "judge": judge_address(),
        "balances": {
            "ETH": _amount(w3.eth.get_balance(safe.address), 18, "ETH"),
            "USDC": _amount(usdc.functions.balanceOf(safe.address).call(), 6, "USDC"),
            "aEthUSDC": _amount(ausdc.functions.balanceOf(safe.address).call(), 6, "aEthUSDC"),
        },
    }


def _book_name(book: dict[str, str], address: str) -> str:
    """Address-book name if the owners know this address, else the short address. Never the fixture's
    own label: the page must not say what the judge has not found yet."""
    for name, a in book.items():
        if a.lower() == address.lower():
            return name
    return _short(to_checksum_address(address))


@app.get("/api/scenarios")
def scenarios() -> list[dict[str, Any]]:
    out = []
    for key, s in SCENARIOS.items():
        case = _case(key)
        out.append({"id": key, "title": s["title"], "description": case["description"],
                    "address_book": case["address_book"], "calls": [
                        {"to": _book_name(case["address_book"], c["to"]), "function": c.get("function"),
                         "operation": c["operation"]}
                        for c in case.get("calls", [])],
                    "operation": case["safe_tx"]["operation"], "to": case["safe_tx"]["to"],
                    "recorded": pipeline.recorded_forward(s["case"]) is not None})
    return out


@app.post("/api/judge/{scenario}")
def judge(scenario: str, live: bool = False) -> dict[str, str]:
    return _start(scenario, live)


class AnswerIn(BaseModel):
    owner: int
    text: str


@app.post("/api/answer/{scenario}")
def answer(scenario: str, body: AnswerIn, live: bool = False) -> dict[str, str]:
    if scenario not in demo.results:
        raise HTTPException(409, "judge the scenario first")
    if not 0 <= body.owner < len(OWNERS) or not body.text.strip():
        raise HTTPException(422, "owner must be 0, 1 or 2 and the answer must not be empty")
    return _start(scenario, live, {"owner": body.owner, "text": body.text})


@app.get("/api/jobs/{job_id}/events")
async def events(job_id: str) -> EventSourceResponse:
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "no such job")

    async def stream():
        sent = 0
        while True:
            with job.lock:
                new = job.events[sent:]
                done = job.done
            for event, payload in new:
                yield {"event": event, "data": json.dumps(payload, default=str)}
            sent += len(new)
            if done and sent == len(job.events):
                yield {"event": "end", "data": "{}"}
                return
            await asyncio.sleep(0.05)

    return EventSourceResponse(stream())


def _decode_revert(err: str) -> dict[str, Any]:
    m = re.search(r"0x[0-9a-fA-F]{8}[0-9a-fA-F]*", err)
    if m:
        data = m.group(0).lower()
        sig = SELECTORS.get(data[:10])
        if sig:
            name = sig.split("(")[0]
            arg = "0x" + data[10:74] if len(data) >= 74 else ""
            return {"name": name, "arg": arg, "why": GUARD_ERROR_TEXT.get(name, "")}
    gs = re.search(r"GS\d{3}", err)
    if gs:
        return {"name": gs.group(0), "arg": "", "why": "the Safe itself refused"}
    return {"name": "revert", "arg": "", "why": err[:200]}


@app.post("/api/execute/{scenario}")
def execute(scenario: str) -> dict[str, Any]:
    demo.ready()
    res = demo.results.get(scenario)
    if res is None:
        raise HTTPException(409, "judge the scenario first")
    with demo.chain_lock:
        out = pipeline.execute(res, demo.w3, demo.safe, OWNERS[0].address)
    signers = f"{THRESHOLD} of {len(OWNERS)} owners had signed"
    if out["executed"]:
        return {"executed": True, "tx": out["tx"], "block": out["block"],
                "execution_success": out["execution_success"], "signers": signers, "state": state()}
    return {"executed": False, "error": _decode_revert(out["error"]), "signers": signers}


@app.post("/api/reset")
def reset(hard: bool = False) -> dict[str, Any]:
    """Back to the base snapshot (fast). ``hard`` re-forks from the pinned block and rebuilds the Safe
    and the guard, as ``secondsig reset`` does."""
    demo.ready()
    with demo.chain_lock:
        ok = False
        if demo.snapshot and not hard:
            ok = bool(rpc(demo.w3, "evm_revert", [demo.snapshot]))
        if not ok:
            url = os.environ.get("MAINNET_RPC") or "https://eth.drpc.org"
            rpc(demo.w3, "anvil_reset", [{"forking": {"jsonRpcUrl": url, "blockNumber": FORK_BLOCK}}])
            demo.safe = ensure_safe(demo.w3, quiet=True)
            demo.guard = ensure_guard(demo.w3, demo.safe)
            ensure_usdc(demo.w3, demo.safe.address)
        demo.snapshot = rpc(demo.w3, "evm_snapshot", [])
    demo.results.clear()
    demo.proposals.clear()
    return {"ok": True, "hard": not ok, "state": state()}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.include_router(sepolia.router)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
