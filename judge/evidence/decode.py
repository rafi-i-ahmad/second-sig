"""Layer 1 evidence: decode. Name calls and events using verified ABIs only.

A frame is decoded with the ABI of the code that ran: its own target, or for a proxy the
implementation it delegated to in this trace. Unverified code stays undecoded: the selector is
shown raw rather than guessed from a signature database, so an attacker cannot pick a friendly
name by choosing a colliding selector. Every decoded name is still untrusted (invariant 7).
"""

from __future__ import annotations

import json

from eth_abi import decode as abi_decode
from eth_utils import function_signature_to_4byte_selector, keccak, to_checksum_address

from judge.schemas import Call, DecodedArg, Event, Source

PRECOMPILES = {
    1: "ecrecover", 2: "sha256", 3: "ripemd160", 4: "identity", 5: "modexp",
    6: "ecAdd", 7: "ecMul", 8: "ecPairing", 9: "blake2f", 10: "pointEvaluation",
}


def _type_str(p: dict) -> str:
    """ABI param -> canonical type, expanding tuples: (address,uint256)[]."""
    t = p["type"]
    if t.startswith("tuple"):
        return "(" + ",".join(_type_str(c) for c in p.get("components", [])) + ")" + t[len("tuple"):]
    return t


def _render(t: str, v: object) -> str:
    if isinstance(v, (list, tuple)):
        inner = t[1:t.rindex(")")].split(",") if t.startswith("(") and not t.endswith("]") else None
        if inner and len(inner) == len(v):
            return "(" + ", ".join(_render(it, x) for it, x in zip(inner, v)) + ")"
        base = t[: t.rindex("[")] if t.endswith("]") else t
        return "[" + ", ".join(_render(base, x) for x in v) + "]"
    if isinstance(v, bytes):
        return "0x" + v.hex()
    if t == "address":
        return to_checksum_address(v)
    return str(v).lower() if isinstance(v, bool) else str(v)


class _Abi:
    def __init__(self, abi: list[dict]) -> None:
        self.functions: dict[str, tuple[str, list[dict]]] = {}
        self.events: dict[str, dict] = {}
        for item in abi:
            if item.get("type") == "function":
                sig = f"{item['name']}({','.join(_type_str(p) for p in item.get('inputs', []))})"
                self.functions["0x" + function_signature_to_4byte_selector(sig).hex()] = (sig, item.get("inputs", []))
            elif item.get("type") == "event" and not item.get("anonymous"):
                sig = f"{item['name']}({','.join(_type_str(p) for p in item.get('inputs', []))})"
                self.events["0x" + keccak(text=sig).hex()] = item


def _abis(sources: dict[str, Source]) -> dict[str, _Abi]:
    return {a: _Abi(json.loads(s.abi_json)) for a, s in sources.items() if s.verified and s.abi_json}


def _candidates(code_addr: str, impls: dict[str, str]) -> list[str]:
    """The code itself first, then what it delegated to (a proxy's implementation)."""
    out = [code_addr]
    while out[-1] in impls and impls[out[-1]] not in out:
        out.append(impls[out[-1]])
    return out


def _decode_call(c: Call, abis: dict[str, _Abi], impls: dict[str, str]) -> Call:
    addr_int = int(c.to_address, 16)
    if addr_int in PRECOMPILES:
        return c.model_copy(update={"function": PRECOMPILES[addr_int]})
    if c.selector is None:
        return c
    for a in _candidates(c.to_address, impls):
        abi = abis.get(a)
        if abi and c.selector in abi.functions:
            sig, inputs = abi.functions[c.selector]
            types = [_type_str(p) for p in inputs]
            try:
                vals = abi_decode(types, bytes.fromhex(c.input[10:]))
            except Exception:  # noqa: BLE001 - malformed calldata stays undecoded, selector still shown
                return c.model_copy(update={"function": sig})
            args = [DecodedArg(name=p.get("name") or None, type=t, value=_render(t, v)) for p, t, v in zip(inputs, types, vals)]
            return c.model_copy(update={"function": sig, "args": args})
    return c


def _decode_event(e: Event, code_addr: str, abis: dict[str, _Abi], impls: dict[str, str]) -> Event:
    if e.topic0 is None:
        return e
    for a in _candidates(code_addr, impls):
        abi = abis.get(a)
        item = abi.events.get(e.topic0) if abi else None
        if item is None:
            continue
        inputs = item.get("inputs", [])
        indexed = [p for p in inputs if p.get("indexed")]
        plain = [p for p in inputs if not p.get("indexed")]
        if len(indexed) != len(e.topics) - 1:
            continue
        try:
            data_vals = abi_decode([_type_str(p) for p in plain], bytes.fromhex(e.data.removeprefix("0x")))
        except Exception:  # noqa: BLE001
            return e.model_copy(update={"name": item["name"]})
        topic_vals: list[object] = []
        for p, topic in zip(indexed, e.topics[1:]):
            t = _type_str(p)
            dynamic = t in ("string", "bytes") or t.endswith("]") or t.startswith("(")
            topic_vals.append(bytes.fromhex(topic[2:]) if dynamic else abi_decode([t], bytes.fromhex(topic[2:]))[0])
        it_topic, it_data = iter(topic_vals), iter(data_vals)
        args = []
        for p in inputs:
            t = _type_str(p)
            v = next(it_topic) if p.get("indexed") else next(it_data)
            if p.get("indexed") and (t in ("string", "bytes") or t.endswith("]") or t.startswith("(")):
                t = "bytes32"  # indexed dynamic values are stored as their hash
            args.append(DecodedArg(name=p.get("name") or None, type=t, value=_render(t, v)))
        return e.model_copy(update={"name": item["name"], "args": args})
    return e


def decode(
    calls: list[Call], events: list[Event], sources: dict[str, Source], impls: dict[str, str]
) -> tuple[list[Call], list[Event]]:
    abis = _abis(sources)
    by_id = {c.id: c for c in calls}
    out_calls = [_decode_call(c, abis, impls) for c in calls]
    out_events = [_decode_event(e, by_id[e.call_id].to_address, abis, impls) for e in events]
    return out_calls, out_events
