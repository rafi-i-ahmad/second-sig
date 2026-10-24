"""Watch the Sepolia Safe's queue in Safe{Wallet}, judge each proposal, and stamp the matches on Sepolia.

    uv run python -m sepolia.watcher --once [--live]    # judge what is queued now, print, exit
    uv run python -m sepolia.watcher [--live]           # keep polling every 15 s

The web demo runs the same ``Watcher`` inside the server (web/sepolia.py) and streams each run to
the Safe App panel.

One proposal, end to end:

1. Read it from Safe's Transaction Service. The description is the Safe{Wallet} note (untrusted).
2. Reset the Sepolia fork to the latest real block; skip unless the Safe is at the proposal's nonce.
3. Recompute the safeTxHash from the service's fields on the fork. A mismatch is refused: the judge
   never rehearses other bytes than the ones Safe{Wallet} shows and the owners sign.
4. Approve the hash on the fork only (approvedHashes, no key, no block) and rehearse the real
   execTransaction: judge/evidence/fork.py, unchanged.
5. ``pipeline.judge``, unchanged: floor, forward ‖ backward, source check, compare, verdict.
6. MATCH: sign the stamp for the Sepolia guard (chain 11155111) and attest it on Sepolia from the
   relayer. Safe{Wallet}'s own execute then passes the guard; anything else reverts.

No note means no description: the floor still runs (a floor hit is decisive without words), but no
model is called and no stamp is made until an owner supplies one through the panel.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Literal

from eth_utils import to_checksum_address
from pydantic import BaseModel, Field
from web3 import Web3

from contracts.setup import judge_address
from judge import pipeline, verdict as verdicting
from judge.evidence import fork as evidence_fork
from judge.schemas import Decision, EvidenceBundle
from sepolia import chain, txservice
from sepolia.chain import SepoliaUnavailable, redact

POLL_S = 15
MAX_STAMP_AGE = 100  # blocks; SecondSigGuard.MAX_STAMP_AGE

Emit = Callable[[str, Any], None]
Status = Literal["judging", "judged", "needs_description", "waiting", "refused", "error"]


def _quiet(event: str, payload: Any) -> None:
    return None


class Entry(BaseModel):
    """What the watcher knows about one proposal. Persisted in logs/sepolia/<safeTxHash>.json."""

    safe_tx_hash: str
    nonce: int
    note: str | None = Field(default=None, description="Safe{Wallet} note. Untrusted.")
    status: Status
    detail: str = ""
    decision: str | None = None
    headline: str = ""
    live: bool = False
    fork_block: int | None = None
    stamp_signature: str | None = None
    attest_tx: str | None = None
    attest_block: int | None = None
    judged_at: str | None = None
    calls: list[str] = Field(default_factory=list)


class Watcher:
    """One Safe, one fork, one judgment at a time (the fork is reset for each)."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.entries: dict[str, Entry] = {}
        self.results: dict[str, pipeline.JudgeResult] = {}
        self.proposals: dict[str, pipeline.Proposal] = {}
        self.bundles: dict[str, EvidenceBundle] = {}
        self._live: Web3 | None = None
        self._fork: Web3 | None = None
        chain.LOGS.mkdir(parents=True, exist_ok=True)
        for p in chain.LOGS.glob("0x*.json"):
            e = Entry.model_validate_json(p.read_text(encoding="utf-8"))
            if e.status == "judging":  # the process stopped mid-run
                e = e.model_copy(update={"status": "error", "detail": "interrupted; re-check"})
            self.entries[e.safe_tx_hash] = e

    # ----------------------------------------------------------------- connections

    @property
    def live(self) -> Web3:
        if self._live is None:
            self._live = chain.sepolia_w3(chain.relayer())
        return self._live

    @property
    def fork(self) -> Web3:
        if self._fork is None:
            self._fork = chain.fork_w3()
        return self._fork

    # ----------------------------------------------------------------- reading

    def state(self) -> dict[str, Any]:
        w3, safe = self.live, chain.safe_address()
        s = chain.safe_reader(w3, safe)
        usdc = w3.eth.contract(address=chain.USDC, abi=chain.ERC20_ABI)
        return {
            "chain_id": chain.CHAIN_ID,
            "head_block": w3.eth.block_number,
            "safe": safe,
            "safe_version": s.functions.VERSION().call(),
            "owners": s.functions.getOwners().call(),
            "threshold": s.functions.getThreshold().call(),
            "nonce": s.functions.nonce().call(),
            "guard": chain.current_guard(w3, safe),
            "judge": judge_address(),
            "balances": {"ETH": w3.eth.get_balance(safe), "USDC": usdc.functions.balanceOf(safe).call()},
        }

    def queue(self, nonce: int | None = None) -> list[txservice.ServiceTx]:
        safe = chain.safe_address()
        if nonce is None:
            nonce = chain.safe_reader(self.live, safe).functions.nonce().call()
        return txservice.pending(safe, nonce)

    def due(self, queue: list[txservice.ServiceTx], nonce: int) -> list[str]:
        """Proposals at the current nonce the watcher has not judged yet."""
        return [t.safe_tx_hash for t in queue if t.nonce == nonce and t.safe_tx_hash not in self.entries]

    def stamp_blocks_left(self, entry: Entry, head: int) -> int | None:
        if entry.attest_tx is None or entry.fork_block is None:
            return None
        return entry.fork_block + MAX_STAMP_AGE - head

    # ----------------------------------------------------------------- judging

    def judge(self, safe_tx_hash: str, *, live: bool, emit: Emit | None = None) -> Entry:
        """Judge one proposal from the queue. Never raises: failures become an 'error' entry."""
        emit = emit or _quiet
        with self.lock:
            prior = self.entries.get(safe_tx_hash)
            self._put(Entry(safe_tx_hash=safe_tx_hash, nonce=prior.nonce if prior else -1,
                            note=prior.note if prior else None, status="judging", live=live))
            try:
                entry = self._judge(txservice.get(safe_tx_hash), live, emit)
            except Exception as exc:  # noqa: BLE001 - shown on the panel; no stamp is the safe outcome
                entry = Entry(safe_tx_hash=safe_tx_hash, nonce=prior.nonce if prior else -1,
                              note=prior.note if prior else None, status="error", live=live,
                              detail=redact(f"{type(exc).__name__}: {exc}"))
                emit("error", {"message": entry.detail})
            self._put(entry)
            return entry

    def _rehearse(self, t: txservice.ServiceTx, description: str, emit: Emit) -> EvidenceBundle | Entry:
        """Fork at the head, check nonce and hash, rehearse. Returns an Entry when it must stop."""
        safe = chain.safe_address()
        base = {"safe_tx_hash": t.safe_tx_hash, "nonce": t.nonce, "note": t.note()}
        if to_checksum_address(t.safe) != safe:
            return Entry(**base, status="refused", detail=f"proposal is for {t.safe}, not this Safe")
        head = self.live.eth.block_number
        emit("stage", {"name": "rehearsing", "detail": f"forking Sepolia at block {head:,}"})
        chain.refork(self.fork, head)
        reader = chain.safe_reader(self.fork, safe)
        nonce = reader.functions.nonce().call()
        if t.nonce != nonce:
            why = "already used" if t.nonce < nonce else "queued behind an earlier proposal"
            return Entry(**base, status="waiting", detail=f"the Safe is at nonce {nonce}; nonce {t.nonce} is {why}")
        tx = t.safe_tx()
        h = evidence_fork.safe_tx_hash(self.fork, safe, tx)
        if h.lower() != t.safe_tx_hash.lower():
            return Entry(**base, status="refused",
                         detail=f"the service says {t.safe_tx_hash} but its fields hash to {h}; not judged")
        owners = sorted(reader.functions.getOwners().call(), key=lambda a: int(a, 16))
        threshold = reader.functions.getThreshold().call()
        sigs = chain.approve_in_fork(self.fork, safe, h, owners[:threshold])
        emit("stage", {"name": "rehearsing", "detail": f"running the bytes on a fork of Sepolia block {head:,}"})
        return evidence_fork.build_bundle(self.fork, safe, tx, sigs, description)

    def _proposal(self, t: txservice.ServiceTx, nonce_owners: tuple[int, int]) -> pipeline.Proposal:
        p = self.proposals.get(t.safe_tx_hash)
        if p is not None:
            return p
        owners, threshold = nonce_owners
        st = t.safe_tx()
        case = {
            "id": "sep_" + t.safe_tx_hash[2:12].lower(),
            "description": t.note() or "",
            "address_book": chain.address_book(),
            "safe": {"address": chain.safe_address(), "version": "1.4.1", "owners": owners, "threshold": threshold},
            "safe_tx": st.model_dump(),
        }
        p = pipeline.Proposal.load_or_create(case)  # keeps owners' amendments across restarts
        self.proposals[t.safe_tx_hash] = p
        return p

    def _judge(self, t: txservice.ServiceTx, live: bool, emit: Emit) -> Entry:
        reader = chain.safe_reader(self.live)
        proposal = self._proposal(t, (len(reader.functions.getOwners().call()), reader.functions.getThreshold().call()))
        # Replay needs recorded forms for this very proposal; without them the models run, and the
        # page must say so (invariant 11)
        live = live or not _recorded(proposal)
        emit("mode", {"live": live})
        description = proposal.effective_description()
        got = self._rehearse(t, description, emit)
        if isinstance(got, Entry):
            emit("notice", {"status": got.status, "message": got.detail})
            return got.model_copy(update={"live": live})
        bundle = got
        self.bundles[t.safe_tx_hash] = bundle

        if not description.strip() and not verdicting.decide(bundle).floor_hits:
            emit("floor", [])
            detail = "No description: add a note in Safe{Wallet}, or answer below as an owner."
            emit("notice", {"status": "needs_description", "message": detail})
            return Entry(safe_tx_hash=t.safe_tx_hash, nonce=t.nonce, note=None, status="needs_description",
                         detail=detail, fork_block=bundle.fork_block, live=live)

        res = pipeline.judge(proposal, bundle, replay=not live, emit=emit)
        return self._finish(t.safe_tx_hash, t.nonce, t.note(), res, live, emit)

    def _finish(self, h: str, nonce: int, note: str | None, res: pipeline.JudgeResult, live: bool,
                emit: Emit) -> Entry:
        self.results[h] = res
        entry = Entry(safe_tx_hash=h, nonce=nonce, note=note, status="judged", live=live,
                      decision=res.verdict.decision.value, headline=res.note, fork_block=res.bundle.fork_block,
                      judged_at=datetime.now(timezone.utc).isoformat(), calls=res.calls)
        emit("verdict", res)
        if res.verdict.decision == Decision.MATCH:
            entry = self._stamp(entry, res, emit)
        emit("stage", {"name": "done", "detail": ""})
        return entry

    def _stamp(self, entry: Entry, res: pipeline.JudgeResult, emit: Emit) -> Entry:
        guard = chain.current_guard(self.live, chain.safe_address())
        if guard is None:
            detail = "MATCH, but the Safe has no guard set: nothing to attest to"
            emit("error", {"message": detail})
            return entry.model_copy(update={"detail": detail})
        emit("stage", {"name": "stamping", "detail": "signing the EIP-712 stamp and attesting it on Sepolia"})
        try:
            sig = pipeline.sign_stamp(res, self.live, guard)
            rcpt = pipeline.attest(res, self.live, chain.guard_contract(self.live, guard), chain.relayer().address)
        except Exception as exc:  # noqa: BLE001 - the verdict stands; without an attested stamp the guard refuses
            detail = redact(f"MATCH, but the stamp was not attested: {type(exc).__name__}: {exc}")
            emit("error", {"message": detail})
            return entry.model_copy(update={"detail": detail})
        out = entry.model_copy(update={"stamp_signature": sig, "attest_tx": rcpt["transactionHash"].to_0x_hex(),
                                       "attest_block": rcpt["blockNumber"]})
        emit("stamp", {"judge": judge_address(), "fork_block": res.stamp.forkBlock, "signature": sig,
                       "safe_tx_hash": res.stamp.safeTxHash, "attest_tx": out.attest_tx,
                       "attest_block": out.attest_block, "guard": guard})
        return out

    # ----------------------------------------------------------------- answering an ASK

    def answer(self, safe_tx_hash: str, owner: str, text: str, *, live: bool, emit: Emit | None = None) -> Entry:
        """An owner's words amend the description; the judge runs again on the same bytes. The
        rehearsal is redone at the current head so a MATCH can still be stamped."""
        emit = emit or _quiet
        with self.lock:
            try:
                t = txservice.get(safe_tx_hash)
                reader = chain.safe_reader(self.live)
                proposal = self._proposal(t, (len(reader.functions.getOwners().call()),
                                              reader.functions.getThreshold().call()))
                emit("mode", {"live": live})
                got = self._rehearse(t, proposal.effective_description(), emit)
                if isinstance(got, Entry):
                    emit("notice", {"status": got.status, "message": got.detail})
                    entry = got
                else:
                    self.bundles[safe_tx_hash] = got
                    prior = self.results.get(safe_tx_hash)
                    # same bytes, same state: the earlier backward form still describes them only if the
                    # rehearsal is unchanged; otherwise backward runs again
                    same = prior is not None and _effects(prior.bundle) == _effects(got)
                    res = pipeline.answer(proposal, owner, text, got, self.live,
                                          backward_form=prior.backward if same else None, replay=not live, emit=emit)
                    emit("amendments", [a.model_dump() for a in proposal.amendments])
                    entry = self._finish(safe_tx_hash, t.nonce, t.note(), res, live, emit)
            except Exception as exc:  # noqa: BLE001
                detail = redact(f"{type(exc).__name__}: {exc}")
                emit("error", {"message": detail})
                prior_e = self.entries.get(safe_tx_hash)
                entry = (prior_e or Entry(safe_tx_hash=safe_tx_hash, nonce=-1, status="error")).model_copy(
                    update={"status": "error", "detail": detail})
            self._put(entry)
            return entry

    # ----------------------------------------------------------------- records

    def _put(self, entry: Entry) -> None:
        self.entries[entry.safe_tx_hash] = entry
        (chain.LOGS / f"{entry.safe_tx_hash}.json").write_text(
            entry.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")


def _recorded(p: pipeline.Proposal) -> bool:
    """Recorded forward and backward forms exist for this proposal (fixtures/outputs/sep_<hash>.*)."""
    return pipeline.recorded_forward(p.id) is not None and pipeline.recorded_backward(p.id) is not None


def _effects(b: EvidenceBundle) -> str:
    """The rehearsal's evidence without its block, for 'did the bytes do the same thing again?'."""
    return json.dumps([b.safe_tx_hash, [c.model_dump() for c in b.call_tree], [w.model_dump() for w in b.storage_diff],
                       [x.model_dump() for x in b.balance_diff], [e.model_dump() for e in b.events]],
                      sort_keys=True, default=str)


# --------------------------------------------------------------------------- CLI


def _print_event(event: str, payload: Any) -> None:
    if event == "stage":
        name = payload["name"] if isinstance(payload, dict) else payload
        detail = payload.get("detail", "") if isinstance(payload, dict) else ""
        print(f"  · {name} {detail}".rstrip())
    elif event == "floor" and payload:
        for h in payload:
            print(f"  ! floor {h.rule}: {h.reason}")
    elif event == "stamp":
        print(f"  stamp attested in block {payload['attest_block']}: {payload['attest_tx']}")
    elif event in ("error", "notice"):
        print(f"  ! {payload['message']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--once", action="store_true", help="judge what is queued now and exit")
    ap.add_argument("--live", action="store_true", help="call the models (default: recorded forms where they exist)")
    args = ap.parse_args(argv)
    w = Watcher()
    while True:
        try:
            nonce = chain.safe_reader(w.live).functions.nonce().call()
            queue = w.queue(nonce)
            print(f"{datetime.now():%H:%M:%S} nonce {nonce}: {len(queue)} pending")
            for h in w.due(queue, nonce):
                t = next(x for x in queue if x.safe_tx_hash == h)
                print(f"judging {h[:12]}… nonce {t.nonce} note={t.note()!r}")
                e = w.judge(h, live=args.live, emit=_print_event)
                print(f"  => {e.status} {e.decision or ''} {e.detail}".rstrip())
                if e.headline:
                    print(f"     {e.headline}")
        except SepoliaUnavailable as exc:
            print(f"unavailable: {exc}", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            print(f"error: {redact(f'{type(exc).__name__}: {exc}')}", file=sys.stderr)
        if args.once:
            return 0
        time.sleep(POLL_S)


if __name__ == "__main__":
    sys.exit(main())
