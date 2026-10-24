"""Layer 1 evidence: the hard floor.

Rules with no honest counterexample. Any hit forces REJECT before a model runs, whatever a
model later says (invariant 2). Pure functions of the bundle: no network, no model, no fork.

1. delegatecall_not_allowlisted: the Safe delegatecalls anything but canonical MultiSendCallOnly
2. protected_slot_write: the Safe's singleton, guard, fallback-handler slot or modules mapping changes
3. unverified_code: a call or delegatecall into a contract with no verified source
4. refund_drain: gasPrice != 0 with a gas token or refund receiver set

Missing evidence fails closed: a called address with no Source record counts as unverified.
"""

from __future__ import annotations

from eth_abi import encode
from eth_utils import keccak, to_checksum_address

from judge.schemas import Call, EvidenceBundle, FloorHit, SlotWrite

ZERO = "0x0000000000000000000000000000000000000000"

# Canonical Safe singletons (safe-deployments). Only the proxy's own forwarding hop to one of
# these is exempt from rule 1; a delegatecall to them from inside the Safe's logic is not.
SAFE_SINGLETONS = frozenset(
    to_checksum_address(a)
    for a in (
        "0xd9Db270c1B5E3Bd161E8c8503c55cEABeE709552",  # 1.3.0
        "0x3E5c63644E683549055b9Be8653de26E0B4CD36E",  # 1.3.0 L2
        "0x41675C099F32341bf84BFc5382aF534df5C7461a",  # 1.4.1
        "0x29fcB43b46531BcA003ddC8FCB67FFE91900C762",  # 1.4.1 L2
    )
)

# The only delegatecall targets allowed from the Safe: canonical MultiSendCallOnly, which
# itself refuses nested delegatecalls.
DELEGATECALL_ALLOWLIST = frozenset(
    to_checksum_address(a)
    for a in (
        "0x40A2aCCbd92BCA938b02010E17A5b8929b49130D",  # MultiSendCallOnly 1.3.0
        "0x9641d764fc13c8B624c04430C7356C1C7C8102e2",  # MultiSendCallOnly 1.4.1
    )
)

SLOT_SINGLETON = "0x" + "00" * 32
# keccak256("guard_manager.guard.address")
SLOT_GUARD = "0x4a204f620c8c5ccdca3fd54d003badd85ba500436a431f0cbda4f558c93c34c8"
# keccak256("fallback_manager.handler.address")
SLOT_FALLBACK_HANDLER = "0x6c9a6c4a39284e37ed1cf53d337577d14212a4870fb976a4366c693b939918d5"
MODULES_MAPPING_SLOT = 1
SENTINEL = "0x0000000000000000000000000000000000000001"

PROTECTED_FIXED_SLOTS = {
    SLOT_SINGLETON: "singleton (slot 0)",
    SLOT_GUARD: "guard",
    SLOT_FALLBACK_HANDLER: "fallback handler",
}

# Precompiles 0x01..0x0a plus room for later forks; they are not contracts with source.
PRECOMPILE_MAX = 0x100

STATE_CHANGING_KINDS = frozenset({"CALL", "DELEGATECALL", "CALLCODE"})


def evaluate(bundle: EvidenceBundle) -> list[FloorHit]:
    """All floor hits for this bundle. Ignores whatever is already in bundle.floor_hits."""
    return [
        *_delegatecalls(bundle),
        *_protected_slots(bundle),
        *_unverified_code(bundle),
        *_refund_drain(bundle),
    ]


def with_floor(bundle: EvidenceBundle) -> EvidenceBundle:
    """A copy of the bundle with floor_hits recomputed from its evidence."""
    return bundle.model_copy(update={"floor_hits": evaluate(bundle)})


# --------------------------------------------------------------------------- rule 1


def _is_proxy_forward(call: Call, by_id: dict[str, Call], safe: str) -> bool:
    """The SafeProxy's own hop: a frame running in the Safe (entered by CALL) delegatecalls its singleton."""
    if call.to_address not in SAFE_SINGLETONS or call.parent is None:
        return False
    parent = by_id[call.parent]
    return parent.kind == "CALL" and parent.to_address == safe


def _delegatecalls(bundle: EvidenceBundle) -> list[FloorHit]:
    safe = to_checksum_address(bundle.safe_address)
    by_id = {c.id: c for c in bundle.call_tree}
    hits = []
    for c in bundle.call_tree:
        if c.kind not in ("DELEGATECALL", "CALLCODE") or to_checksum_address(c.storage_context) != safe:
            continue
        target = to_checksum_address(c.to_address)
        if target in DELEGATECALL_ALLOWLIST or _is_proxy_forward(c, by_id, safe):
            continue
        hits.append(
            FloorHit(
                rule="delegatecall_not_allowlisted",
                cites=[c.id],
                reason=f"The Safe delegatecalls {_short(target)}, which is not MultiSendCallOnly: "
                f"that code runs with the Safe's own storage and funds.",
            )
        )
    # The struct itself asks for a delegatecall the trace does not show (e.g. it reverted first).
    st = bundle.safe_tx
    if (
        not hits
        and st.operation == 1
        and to_checksum_address(st.to) not in DELEGATECALL_ALLOWLIST
        and bundle.call_tree
    ):
        hits.append(
            FloorHit(
                rule="delegatecall_not_allowlisted",
                cites=[bundle.call_tree[0].id],
                reason=f"The transaction asks the Safe to delegatecall {_short(st.to)}, "
                f"which is not MultiSendCallOnly.",
            )
        )
    return hits


# --------------------------------------------------------------------------- rule 2


def _module_slot(key: str) -> str:
    return "0x" + keccak(encode(["address", "uint256"], [key, MODULES_MAPPING_SLOT])).hex()


def _candidate_addresses(bundle: EvidenceBundle) -> set[str]:
    """Every address that appears in the evidence: possible keys of the modules mapping."""
    out = {SENTINEL}
    for c in bundle.call_tree:
        out |= {c.from_address, c.to_address, c.storage_context}
        out |= {a.value for a in c.args if a.type == "address"}
    for e in bundle.events:
        out |= {a.value for a in e.args if a.type == "address"}
        out |= {"0x" + t[-40:] for t in e.topics[1:]}
    data = bytes.fromhex(bundle.safe_tx.data.removeprefix("0x"))
    for i in range(4, len(data) - 31):  # any 32-byte word that could be an address
        word = data[i : i + 32]
        if word[:12] == b"\x00" * 12 and word[12:] != b"\x00" * 20:
            out.add("0x" + word[12:].hex())
    return {to_checksum_address(a) for a in out if len(a) == 42}


def _protected_slot_name(w: SlotWrite, module_slots: dict[str, str]) -> str | None:
    slot = w.slot.lower()
    if slot in PROTECTED_FIXED_SLOTS:
        return PROTECTED_FIXED_SLOTS[slot]
    if slot in module_slots:
        return f"modules mapping (entry for {_short(module_slots[slot])})"
    if w.label and w.label.startswith("Safe.modules"):
        return f"modules mapping ({w.label})"
    return None


def _protected_slots(bundle: EvidenceBundle) -> list[FloorHit]:
    safe = to_checksum_address(bundle.safe_address)
    module_slots = {_module_slot(a): a for a in _candidate_addresses(bundle)}
    hits = []
    for w in bundle.storage_diff:
        if to_checksum_address(w.contract) != safe:
            continue
        name = _protected_slot_name(w, module_slots)
        if name is None:
            continue
        hits.append(
            FloorHit(
                rule="protected_slot_write",
                cites=[w.id],
                reason=f"The Safe's {name} changes from {_word_short(w.before)} to {_word_short(w.after)}.",
            )
        )
    return hits


# --------------------------------------------------------------------------- rule 3


def _unverified_code(bundle: EvidenceBundle) -> list[FloorHit]:
    safe = to_checksum_address(bundle.safe_address)
    hits = []
    seen: set[str] = set()
    for c in bundle.call_tree:
        if c.kind not in STATE_CHANGING_KINDS:
            continue
        target = to_checksum_address(c.to_address)
        if target == safe or int(target, 16) < PRECOMPILE_MAX or target in seen:
            continue
        src = bundle.sources.get(target)
        if src is None:
            reason = f"{_short(target)} was called but has no source record; treated as unverified."
        elif not src.has_code or src.verified:
            continue
        else:
            reason = f"{_short(target)} has no verified source."
        seen.add(target)
        hits.append(FloorHit(rule="unverified_code", cites=[c.id], reason=reason))
    return hits


# --------------------------------------------------------------------------- rule 4


def _refund_drain(bundle: EvidenceBundle) -> list[FloorHit]:
    st = bundle.safe_tx
    if st.gas_price == 0:
        return []
    if int(st.gas_token, 16) == 0 and int(st.refund_receiver, 16) == 0:
        return []
    if not bundle.call_tree:
        return []
    return [
        FloorHit(
            rule="refund_drain",
            cites=[bundle.call_tree[0].id],
            reason=f"gasPrice is {st.gas_price} with gas token {_short(st.gas_token)} and refund receiver "
            f"{_short(st.refund_receiver)}: the Safe would pay the executor a refund.",
        )
    ]


# --------------------------------------------------------------------------- formatting


def _short(addr: str) -> str:
    a = to_checksum_address(addr)
    return f"{a[:6]}…{a[-4:]}"


def _word_short(word: str) -> str:
    """A storage word, shown as an address when it looks like one."""
    h = word.removeprefix("0x").rjust(64, "0")
    if h[:24] == "0" * 24:
        return _short("0x" + h[24:])
    return "0x" + h.lstrip("0")[:16] + ("…" if len(h.lstrip("0")) > 16 else "")
