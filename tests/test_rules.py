"""The hard floor: Bybit trips rules 1, 2 and 3; honest shapes trip nothing."""

from __future__ import annotations

from pathlib import Path

import pytest
from eth_utils import keccak

from judge.evidence import rules
from judge.schemas import Call, DecodedArg, EvidenceBundle, SafeTx, SlotWrite, Source

EXAMPLE = Path(__file__).resolve().parent.parent / "fixtures" / "examples" / "bybit.bundle.json"

SAFE = "0xDFECEf26e5d211b9935cABC9FAD1edB8960aaE47"
RELAYER = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
SINGLETON = "0x41675C099F32341bf84BFc5382aF534df5C7461a"
MULTISEND = "0x9641d764fc13c8B624c04430C7356C1C7C8102e2"
USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
USDC_IMPL = "0x43506849D7C04F9138D1A2050bbF3A0c054402dd"
OPS_WALLET = "0xE1D9a0eADCb8082d7989D7304061c017bE296C31"
EVIL = "0x96221423681A6d52E184D440a8eFCEbB105C7242"
W0 = "0x" + "00" * 32


def word(addr: str) -> str:
    return "0x" + addr[2:].lower().rjust(64, "0")


def _call(i: int, parent: int | None, kind: str, frm: str, to: str, ctx: str | None = None, **kw) -> Call:
    return Call(
        id=f"c{i}", parent=None if parent is None else f"c{parent}", depth=0 if parent is None else 1,
        kind=kind, from_address=frm, to_address=to, storage_context=ctx or to, input=kw.pop("input", "0x"),
        success=True, **kw,
    )


def safe_frames(*inner: Call) -> list[Call]:
    """Relayer -> Safe proxy -> delegatecall singleton, then the inner frames (parent c1)."""
    return [
        _call(0, None, "CALL", RELAYER, SAFE),
        _call(1, 0, "DELEGATECALL", SAFE, SINGLETON, SAFE),
        *inner,
    ]


def src(addr: str, verified: bool = True, has_code: bool = True) -> Source:
    return Source(address=addr, has_code=has_code, verified=verified)


def bundle(calls: list[Call], *, writes=(), sources=None, safe_tx: SafeTx | None = None) -> EvidenceBundle:
    base = {SAFE: Source(address=SAFE, has_code=True, verified=False, implementation=SINGLETON), SINGLETON: src(SINGLETON)}
    return EvidenceBundle(
        safe_tx_hash="0x" + "11" * 32, safe_address=SAFE, chain_id=1, fork_block=21895239,
        description="test", execution_success=True,
        safe_tx=safe_tx or SafeTx(to=OPS_WALLET, value=0, data="0x", operation=0, nonce=0),
        call_tree=calls, storage_diff=list(writes), sources={**base, **(sources or {})},
    )


# --------------------------------------------------------------------------- constants


def test_slot_constants_match_safe_source() -> None:
    assert rules.SLOT_GUARD == "0x" + keccak(text="guard_manager.guard.address").hex()
    assert rules.SLOT_FALLBACK_HANDLER == "0x" + keccak(text="fallback_manager.handler.address").hex()


# --------------------------------------------------------------------------- Bybit


def test_bybit_trips_rules_1_2_3() -> None:
    b = EvidenceBundle.model_validate_json(EXAMPLE.read_text(encoding="utf-8")).model_copy(update={"floor_hits": []})
    hits = rules.evaluate(b)
    assert sorted((h.rule, tuple(h.cites)) for h in hits) == [
        ("delegatecall_not_allowlisted", ("c4",)),
        ("protected_slot_write", ("s0",)),
        ("unverified_code", ("c4",)),
    ]
    slot0 = next(h for h in hits if h.rule == "protected_slot_write")
    assert "0x4167…461a" in slot0.reason and "0xbDd0…9516" in slot0.reason
    # what with_floor writes back must validate as a bundle (citations resolve)
    EvidenceBundle.model_validate(rules.with_floor(b).model_dump())


# --------------------------------------------------------------------------- honest shapes: no hits


def test_eth_transfer_to_eoa_is_clean() -> None:
    b = bundle(safe_frames(_call(2, 1, "CALL", SAFE, OPS_WALLET, value=5 * 10**18)),
               sources={OPS_WALLET: src(OPS_WALLET, verified=False, has_code=False)})
    assert rules.evaluate(b) == []


def test_multisend_batch_through_proxied_token_is_clean() -> None:
    calls = safe_frames(
        _call(2, 1, "DELEGATECALL", SAFE, MULTISEND, SAFE),
        _call(3, 2, "CALL", SAFE, USDC),
        _call(4, 3, "DELEGATECALL", USDC, USDC_IMPL, USDC),  # USDC's own proxy hop: not the Safe's context
    )
    b = bundle(calls, sources={MULTISEND: src(MULTISEND), USDC: src(USDC), USDC_IMPL: src(USDC_IMPL)},
               safe_tx=SafeTx(to=MULTISEND, value=0, data="0x8d80ff0a", operation=1, nonce=0))
    assert rules.evaluate(b) == []


def test_nonce_and_owner_writes_are_not_protected() -> None:
    writes = [
        SlotWrite(id="s0", contract=SAFE, slot="0x" + "00" * 31 + "05", before=W0, after="0x" + "00" * 31 + "01"),
        SlotWrite(id="s1", contract=SAFE, slot="0x" + "00" * 31 + "04", before=W0, after="0x" + "00" * 31 + "03"),
    ]
    assert rules.evaluate(bundle(safe_frames(), writes=writes)) == []


def test_slot_zero_of_another_contract_is_not_protected() -> None:
    w = SlotWrite(id="s0", contract=USDC, slot=W0, before=W0, after=word(EVIL))
    assert rules.evaluate(bundle(safe_frames(), writes=[w])) == []


def test_staticcall_and_precompile_into_unverified_are_clean() -> None:
    calls = safe_frames(
        _call(2, 1, "STATICCALL", SAFE, EVIL),
        _call(3, 1, "STATICCALL", SAFE, "0x0000000000000000000000000000000000000001"),
    )
    assert rules.evaluate(bundle(calls, sources={EVIL: src(EVIL, verified=False)})) == []


def test_gas_price_without_refund_target_is_clean() -> None:
    st = SafeTx(to=OPS_WALLET, value=0, data="0x", operation=0, nonce=0, gas_price=1)
    assert rules.evaluate(bundle(safe_frames(), safe_tx=st)) == []


# --------------------------------------------------------------------------- each rule fires


def test_delegatecall_to_singleton_from_inside_safe_logic_fires() -> None:
    # only the proxy's own forwarding hop is exempt, not any delegatecall to a singleton
    calls = safe_frames(_call(2, 1, "DELEGATECALL", SAFE, SINGLETON, SAFE))
    hits = rules.evaluate(bundle(calls))
    assert [(h.rule, h.cites) for h in hits] == [("delegatecall_not_allowlisted", ["c2"])]


def test_nested_delegatecall_in_safe_context_fires() -> None:
    other = "0x1111111111111111111111111111111111111111"
    calls = safe_frames(
        _call(2, 1, "DELEGATECALL", SAFE, MULTISEND, SAFE),
        _call(3, 2, "DELEGATECALL", SAFE, other, SAFE),
    )
    hits = rules.evaluate(bundle(calls, sources={MULTISEND: src(MULTISEND), other: src(other)}))
    assert [(h.rule, h.cites) for h in hits] == [("delegatecall_not_allowlisted", ["c3"])]


def test_delegatecall_in_struct_but_not_in_trace_fires() -> None:
    st = SafeTx(to=EVIL, value=0, data="0x", operation=1, nonce=0)
    hits = rules.evaluate(bundle(safe_frames(), safe_tx=st))
    assert [(h.rule, h.cites) for h in hits] == [("delegatecall_not_allowlisted", ["c0"])]


@pytest.mark.parametrize("slot", [rules.SLOT_GUARD, rules.SLOT_FALLBACK_HANDLER, W0])
def test_fixed_protected_slots_fire(slot: str) -> None:
    w = SlotWrite(id="s0", contract=SAFE, slot=slot, before=word(SINGLETON), after=W0)
    hits = rules.evaluate(bundle(safe_frames(), writes=[w]))
    assert [(h.rule, h.cites) for h in hits] == [("protected_slot_write", ["s0"])]


def test_enabling_a_module_fires() -> None:
    module = "0x2222222222222222222222222222222222222222"
    # enableModule(module): modules[module] = modules[SENTINEL]; modules[SENTINEL] = module
    writes = [
        SlotWrite(id="s0", contract=SAFE, slot=rules._module_slot(module), before=W0, after=word(rules.SENTINEL)),
        SlotWrite(id="s1", contract=SAFE, slot=rules._module_slot(rules.SENTINEL), before=word(rules.SENTINEL), after=word(module)),
    ]
    calls = safe_frames(_call(2, 1, "CALL", SAFE, SAFE, SAFE, args=[DecodedArg(name="module", type="address", value=module)]))
    hits = rules.evaluate(bundle(calls, writes=writes))
    assert sorted(h.cites[0] for h in hits if h.rule == "protected_slot_write") == ["s0", "s1"]


def test_module_slot_found_from_calldata_without_decoding() -> None:
    module = "0x3333333333333333333333333333333333333333"
    data = "0x610b5925" + module[2:].rjust(64, "0")  # enableModule(address), undecoded
    st = SafeTx(to=SAFE, value=0, data=data, operation=0, nonce=0)
    w = SlotWrite(id="s0", contract=SAFE, slot=rules._module_slot(module), before=W0, after=word(rules.SENTINEL))
    hits = rules.evaluate(bundle(safe_frames(), writes=[w], safe_tx=st))
    assert [h.rule for h in hits] == ["protected_slot_write"]


def test_call_into_unverified_contract_fires_once_per_address() -> None:
    calls = safe_frames(_call(2, 1, "CALL", SAFE, EVIL), _call(3, 1, "CALL", SAFE, EVIL))
    hits = rules.evaluate(bundle(calls, sources={EVIL: src(EVIL, verified=False)}))
    assert [(h.rule, h.cites) for h in hits] == [("unverified_code", ["c2"])]


def test_missing_source_record_fails_closed() -> None:
    calls = safe_frames(_call(2, 1, "CALL", SAFE, EVIL))
    hits = rules.evaluate(bundle(calls))
    assert [h.rule for h in hits] == ["unverified_code"] and "no source record" in hits[0].reason


@pytest.mark.parametrize("field", ["gas_token", "refund_receiver"])
def test_refund_drain_fires(field: str) -> None:
    st = SafeTx(to=OPS_WALLET, value=0, data="0x", operation=0, nonce=0, gas_price=10**9, **{field: EVIL})
    hits = rules.evaluate(bundle(safe_frames(), safe_tx=st))
    assert [(h.rule, h.cites) for h in hits] == [("refund_drain", ["c0"])]
