"""Layer 1 evidence: trace. Turn a Rehearsal's raw traces into citable bundle entries.

Calls are flattened in pre-order (c0, c1, ...); each records whose storage it acts on, so a
delegatecall into the Safe is visible as such. Logs become events (e0, ...) tied to the frame
that emitted them. The prestate diff becomes storage writes (s0, ...) and ETH balance changes;
Transfer-log holders' token balances become token changes (b0, ...). The relayer's gas is
taken out of its ETH change. Names are not decoded here; see decode.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from eth_utils import to_checksum_address
from pydantic import BaseModel

from judge.schemas import BalanceChange, Call, Event, SlotWrite

if TYPE_CHECKING:
    from judge.evidence.fork import RawFrame, Rehearsal

PRECOMPILE_MAX = 0x100
ZERO_WORD = "0x" + "00" * 32
# EIP-7708 (live on Sepolia, not at the mainnet fork block): every ETH value transfer also emits an
# ERC-20-shaped Transfer log from this system address. Only the protocol can emit from it, and the
# call's value and the balance diff already record the movement, so these logs are skipped.
ETH_TRANSFER_LOG_ADDRESS = "0xfffffffffffffffffffffffffffffffffffffffe"


class TraceEvidence(BaseModel):
    calls: list[Call]
    events: list[Event]
    storage_diff: list[SlotWrite]
    balance_diff: list[BalanceChange]
    implementations: dict[str, str]  # proxy -> code it delegated to in this trace


def _word(h: str) -> str:
    return "0x" + h.removeprefix("0x").lower().rjust(64, "0")


def flatten(frame: RawFrame) -> tuple[list[Call], list[Event], dict[str, str]]:
    calls: list[Call] = []
    events: list[Event] = []
    impls: dict[str, str] = {}

    def walk(f: RawFrame, parent: Call | None, depth: int) -> None:
        to = to_checksum_address(f.to)
        sender = to_checksum_address(f.from_)
        kind = f.type.upper()
        ctx = parent.storage_context if kind in ("DELEGATECALL", "CALLCODE") and parent else to
        if kind == "DELEGATECALL" and parent is not None and parent.kind == "CALL" and parent.to_address == ctx:
            impls.setdefault(ctx, to)  # a proxy forwarding to its implementation
        is_precompile = int(to, 16) < PRECOMPILE_MAX
        c = Call(
            id=f"c{len(calls)}", parent=parent.id if parent else None, depth=depth, kind=kind,
            from_address=sender, to_address=to, storage_context=ctx,
            value=int(f.value, 16) if f.value else 0, input=f.input,
            selector=f.input[:10].lower() if len(f.input) >= 10 and not is_precompile else None,
            success=f.error is None, revert_reason=f.revert_reason,
        )
        calls.append(c)
        for log in f.logs:
            if log.address.lower() == ETH_TRANSFER_LOG_ADDRESS:
                continue  # EIP-7708: the protocol's log for a value transfer the call itself records
            events.append(Event(
                id=f"e{len(events)}", call_id=c.id, address=to_checksum_address(log.address),
                topic0=log.topics[0].lower() if log.topics else None,
                topics=[t.lower() for t in log.topics], data=log.data,
            ))
        for child in f.calls:
            walk(child, c, depth + 1)

    walk(frame, None, 0)
    return calls, events, impls


def storage_writes(r: Rehearsal) -> list[SlotWrite]:
    out: list[SlotWrite] = []
    for addr in sorted(set(r.diff.pre) | set(r.diff.post)):
        pre = r.diff.pre.get(addr)
        post = r.diff.post.get(addr)
        before = pre.storage if pre else {}
        after = post.storage if post else {}
        for slot in sorted(set(before) | set(after)):
            b = _word(before.get(slot, ZERO_WORD))
            a = _word(after.get(slot, ZERO_WORD))  # diffMode omits a slot that became zero
            if a != b:
                out.append(SlotWrite(id=f"s{len(out)}", contract=to_checksum_address(addr), slot=_word(slot), before=b, after=a))
    return out


def balance_changes(r: Rehearsal) -> list[BalanceChange]:
    out: list[BalanceChange] = []
    relayer = r.relayer.lower()
    for addr in sorted(set(r.diff.pre) | set(r.diff.post)):
        pre = r.diff.pre.get(addr)
        post = r.diff.post.get(addr)
        if not (post and post.balance is not None) and not (pre and pre.balance is not None):
            continue
        before = int(pre.balance, 16) if pre and pre.balance else 0
        after = int(post.balance, 16) if post and post.balance else before
        if addr.lower() == relayer:
            after += r.relayer_gas_cost  # gas is the relayer's cost, not an effect of the transaction
        if after != before:
            out.append(BalanceChange(
                id=f"b{len(out)}", holder=to_checksum_address(addr), asset="ETH", symbol="ETH", decimals=18,
                before=before, after=after, delta=after - before,
            ))
    for t in r.token_balances:
        if t.after != t.before:
            out.append(BalanceChange(
                id=f"b{len(out)}", holder=t.holder, asset=t.token, symbol=t.symbol, decimals=t.decimals,
                before=t.before, after=t.after, delta=t.after - t.before,
            ))
    return out


def to_evidence(r: Rehearsal) -> TraceEvidence:
    calls, events, impls = flatten(r.frame)
    return TraceEvidence(
        calls=calls, events=events, storage_diff=storage_writes(r), balance_diff=balance_changes(r),
        implementations=impls,
    )
