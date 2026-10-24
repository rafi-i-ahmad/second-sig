"""Check the source reader's claims against the source and the slot arithmetic. Pure code.

A SlotClaim counts only if
1. every cited s-id is an unlabelled write of the contract the claim names;
2. every source citation resolves: the file is in the verified source of that contract (or of
   the implementation behind it), the line exists, and the line mentions the variable; and
3. code reproduces the slot: keccak(key, base_slot) + offset for a mapping, or base_slot + offset
   for a plain slot, equals the written slot (judge/evidence/slots._map).

A corroborated ``routine_bookkeeping`` claim becomes the write's label, which is the only way a
model's reading ever lowers suspicion (invariant 4: structure that code can verify). Any other
reading, corroborated or not, raises the write to notable with the model's sentence as the reason.
A claim that fails any check changes nothing and is listed as rejected.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from eth_utils import is_address, to_checksum_address

from judge.evidence import slots
from judge.schemas import Classification, EvidenceBundle, SlotClaim, SlotWrite, Source

MAX_OFFSET = 64


@dataclass
class Corroboration:
    bundle: EvidenceBundle
    explained: list[str] = field(default_factory=list)  # "s3 PoolInstance._reserves[USDC]+1: sentence (path:line)"
    raised: dict[str, str] = field(default_factory=dict)  # s-id -> reason
    rejected: list[str] = field(default_factory=list)  # "s3: why the claim failed"


def _files_for(bundle: EvidenceBundle, contract: str) -> dict[str, str]:
    src: Source | None = bundle.sources.get(contract)
    if src is None:
        return {}
    files = dict(src.files)
    if src.implementation and src.implementation in bundle.sources:
        files.update(bundle.sources[src.implementation].files)
    return files


def _slot_matches(claim: SlotClaim, slot_hex: str) -> bool:
    slot = int(slot_hex, 16)
    if not (0 <= claim.offset <= MAX_OFFSET) or claim.base_slot < 0:
        return False
    if claim.key is None:
        return slot == claim.base_slot + claim.offset
    try:
        if claim.key_type == "address":
            if not is_address(claim.key):
                return False
            key = to_checksum_address(claim.key)
        elif claim.key_type == "uint256":
            key = int(claim.key, 0)
        else:
            key = bytes.fromhex(claim.key.removeprefix("0x")).rjust(32, b"\x00")
        base = int(slots._map(key, claim.base_slot, claim.key_type), 16)
    except (ValueError, TypeError):
        return False
    return slot == base + claim.offset


def _check(claim: SlotClaim, bundle: EvidenceBundle, writes: dict[str, SlotWrite]) -> str | None:
    """None if the claim holds; otherwise the first reason it does not."""
    if not is_address(claim.contract):
        return f"contract {claim.contract!r} is not an address"
    contract = to_checksum_address(claim.contract)
    for sid in claim.cites:
        w = writes.get(sid)
        if w is None:
            return f"{sid} is not a storage write in the bundle"
        if w.label:
            return f"{sid} is already labelled ({w.label})"
        if to_checksum_address(w.contract) != contract:
            return f"{sid} belongs to {w.contract}, not {contract}"
        if not _slot_matches(claim, w.slot):
            return f"{sid}: slot does not equal keccak(key, {claim.base_slot}) + {claim.offset}"
    files = _files_for(bundle, contract)
    if not files:
        return f"no verified source for {contract}"
    var = claim.variable.strip().replace("_", "").lower()
    if not var:
        return "claim names no variable"
    for c in claim.source_cites:
        text = files.get(c.path)
        if text is None:
            return f"source file {c.path!r} is not in the verified source"
        lines = text.splitlines()
        if not (1 <= c.line <= len(lines)):
            return f"{c.path}:{c.line} is out of range (1..{len(lines)})"
        # at least one cited line must name the variable; underscores and case are tolerated
    if not any(var in files[c.path].splitlines()[c.line - 1].replace("_", "").lower() for c in claim.source_cites):
        return f"none of the cited lines mentions {claim.variable!r}"
    return None


def apply(bundle: EvidenceBundle, cls: Classification | None) -> Corroboration:
    out = Corroboration(bundle=bundle)
    if cls is None:
        return out
    writes = {w.id: w for w in bundle.storage_diff}
    labels: dict[str, str] = {}
    for claim in cls.items:
        why = _check(claim, bundle, writes)
        name = bundle.sources.get(to_checksum_address(claim.contract)) if is_address(claim.contract) else None
        cname = (name.name if name and name.name else claim.contract[:10])
        where = ", ".join(f"{c.path.rsplit('/', 1)[-1]}:{c.line}" for c in claim.source_cites)
        key = f"[{slots._short(claim.key)}]" if claim.key and is_address(claim.key) else (f"[{claim.key}]" if claim.key else "")
        off = f"+{claim.offset}" if claim.offset else ""
        label = f"{cname}.{claim.variable}{key}{off}"
        if why is not None:
            out.rejected.append(f"{', '.join(claim.cites)} {label}: {why}")
            continue
        if claim.reading == "routine_bookkeeping":
            for sid in claim.cites:
                labels[sid] = label
            out.explained.append(f"{', '.join(claim.cites)} {label}: {claim.sentence} ({where})")
        else:
            for sid in claim.cites:
                out.raised[sid] = f"{claim.reading}: {claim.sentence} ({where})"
    if labels:
        diff = [w.model_copy(update={"label": labels[w.id]}) if w.id in labels else w for w in bundle.storage_diff]
        out.bundle = bundle.model_copy(update={"storage_diff": diff})
    return out
