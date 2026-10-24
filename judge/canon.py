"""Layer 4: canonical form.

Turns the forward form (ExpectedEffects), the backward form (Narration) and the fixture
ground truth into one shape, CanonEffects, so compare.py can lay them side by side.

Resolution rules (deterministic, no model):
- Parties: 'Safe' and the Safe's address resolve to the Safe; address-book names resolve to
  their address; a 0x address resolves to itself; the zero address is kept as "zero"; a
  label that only a contract name in bundle.sources matches resolves via "sources"; anything
  else stays unresolved. Identity is the address. Chain-read symbols and contract names are
  display only and never decide a match.
- Assets: 'ETH' is ether; an address-book name or a 0x address resolves directly; a backward
  item can resolve through the evidence it cites (a balance entry's asset, a Transfer or
  Approval event's emitting contract), which is address data, not a symbol; otherwise the
  asset is unresolved and compare.py may still match it under the asset_unresolved tier.
- Amounts: base units, using decimals from the bundle's balance entries (or 18 for ETH, 6
  for mainnet USDC). A forward amount the words do not fix is None.
- Severity: Narration's structured lists carry none, so each inherits the highest severity
  of the effects whose citations overlap its own; default notable.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from eth_utils import is_address, to_checksum_address

from judge import checker
from judge.schemas import (
    Asset, BalanceChange, CanonConfig, CanonEffect, CanonEffects, CanonMovement, CanonPermission, Direction,
    Event, EvidenceBundle, ExpectedEffects, Narration, Party, Severity,
)

ZERO = "0x0000000000000000000000000000000000000000"
UINT256_MAX = 2**256 - 1
KNOWN_DECIMALS = {
    "ETH": 18,
    "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48": 6,  # mainnet USDC
    "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2": 18,  # WETH9
}
SEVERITY_RANK: dict[Severity, int] = {"info": 0, "notable": 1, "critical": 2}
_SAFE_WORDS = {"safe", "the safe", "this safe", "our safe", "proposing safe", "the proposing safe"}
_ARTICLES = re.compile(r"^(the|our|this)\s+", re.I)
_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
_UNLIMITED = re.compile(r"\b(unlimited|infinite|max|maximum|all of it|everything|the (?:whole|entire|remaining) balance)\b", re.I)
_UPPER_BOUND = re.compile(
    r"\b(at most|up to|no more than|not more than|not exceeding|a maximum of|max(?:imum)?\s+of|capped at|under|below"
    r"|less than)\b|<=?\s*\d|≤", re.I)
_LOWER_BOUND = re.compile(
    r"\b(at least|a minimum of|min(?:imum)?\s+of|no less than|not less than|or more|and above|over|above|more than"
    r"|exceeding)\b|>=?\s*\d|≥", re.I)
_APPROX = re.compile(r"\b(about|around|roughly|approximately|approx\.?|circa|close to|nearly|some)\b|~\s*\d|≈", re.I)
_PERCENT = re.compile(r"\d\s*(%|percent\b|per cent\b)|\b(half|a third|a quarter|two thirds)\b", re.I)
APPROX_TOLERANCE = 0.10  # 'about 2 ETH' accepts 1.8 to 2.2
_APPROVE_WORDS = re.compile(r"\b(approv\w*|allow\w*|permi\w*|spend\w*|authori[sz]\w*)\b", re.I)


def _norm_label(label: str) -> str:
    return _ARTICLES.sub("", label.strip()).lower()


class Resolver:
    """Address book + bundle, read-only. One per case."""

    def __init__(self, bundle: EvidenceBundle, address_book: dict[str, str]) -> None:
        self.bundle = bundle
        self.safe = to_checksum_address(bundle.safe_address)
        self.book = {_norm_label(k): to_checksum_address(v) for k, v in address_book.items()}
        self.names = {to_checksum_address(v): k for k, v in address_book.items()}
        self.decimals: dict[str, int] = dict(KNOWN_DECIMALS)
        for b in bundle.balance_diff:
            if b.decimals is not None:
                self.decimals[b.asset if b.asset == "ETH" else to_checksum_address(b.asset)] = b.decimals
        self.source_names = {
            _norm_label(s.name): to_checksum_address(a) for a, s in bundle.sources.items() if s.name
        }
        self.frames = {c.id: c for c in bundle.call_tree}

    # ----------------------------------------------------------------- parties

    def party(self, label: str | None) -> Party:
        if label is None:
            return Party(label="", via="unresolved")
        raw = label.strip()
        if _norm_label(raw) in _SAFE_WORDS:
            return Party(label="Safe", address=self.safe, via="safe")
        if is_address(raw):
            addr = to_checksum_address(raw)
            if addr == self.safe:
                return Party(label="Safe", address=addr, via="safe")
            if addr == ZERO:
                return Party(label="zero address", address=addr, via="zero")
            return Party(label=self.names.get(addr, addr), address=addr, via="address")
        key = _norm_label(raw)
        if key in self.book:
            return Party(label=raw, address=self.book[key], via="address_book")
        if key in self.source_names:
            return Party(label=raw, address=self.source_names[key], via="sources")
        return Party(label=raw, via="unresolved")

    def display(self, address: str) -> str:
        if address == self.safe:
            return "Safe"
        return self.names.get(address, address)

    # ----------------------------------------------------------------- assets

    def asset(self, label: str, cites: list[str] = ()) -> Asset:
        raw = label.strip()
        if raw.upper() in ("ETH", "ETHER", "WEI"):
            return Asset(label="ETH", address="ETH", via="eth", decimals=18)
        if is_address(raw):
            addr = to_checksum_address(raw)
            return Asset(label=self.names.get(addr, addr), address=addr, via="address", decimals=self.decimals.get(addr))
        key = _norm_label(raw)
        if key in self.book:
            addr = self.book[key]
            return Asset(label=raw, address=addr, via="address_book", decimals=self.decimals.get(addr))
        for cid in cites:
            e = self.bundle.entry(cid)
            if isinstance(e, BalanceChange):
                addr = e.asset if e.asset == "ETH" else to_checksum_address(e.asset)
                return Asset(label=raw, address=addr, via="evidence", decimals=self.decimals.get(addr, e.decimals))
            if isinstance(e, Event) and e.name in ("Transfer", "Approval"):
                addr = to_checksum_address(e.address)
                return Asset(label=raw, address=addr, via="evidence", decimals=self.decimals.get(addr))
        return Asset(label=raw, via="unresolved")

    # ----------------------------------------------------------------- amounts

    def to_base(self, human: str | None, asset: Asset) -> int | None:
        value = parse_amount(human)
        if value is None or value == "unlimited":
            return None
        if asset.decimals is None:
            return None
        return int(value * (Decimal(10) ** asset.decimals))

    def direction(self, from_party: Party, to_party: Party) -> Direction:
        f, t = from_party.address == self.safe, to_party.address == self.safe
        if f and t:
            return "self"
        if f:
            return "out"
        if t:
            return "in"
        return "third_party"

    # ----------------------------------------------------------------- call tree

    def frame_ids_for(self, cites: list[str]) -> list[str]:
        """The call frames a set of citations points at: c-ids directly, e-ids via call_id."""
        out: list[str] = []
        for cid in cites:
            e = self.bundle.entry(cid)
            if isinstance(e, Event):
                out.append(e.call_id)
            elif cid in self.frames:
                out.append(cid)
        return out

    def inside_call_to(self, cites: list[str], address: str | None) -> bool:
        """True if any cited frame is, or sits under, a CALL into ``address``."""
        if address is None:
            return False
        for fid in self.frame_ids_for(cites):
            cur = self.frames.get(fid)
            while cur is not None:
                if cur.kind == "CALL" and to_checksum_address(cur.to_address) == address:
                    return True
                cur = self.frames.get(cur.parent) if cur.parent else None
        return False


def parse_amount(human: str | None) -> Decimal | str | None:
    """'2,500 USDC' -> 2500; 'at most 1 ETH' -> 1 (see is_upper_bound); 'unlimited' or 'max' with
    no number -> 'unlimited'; a percentage or fraction of something ('10%', 'half') -> None, since
    the words fix no amount of the asset; nothing numeric -> None."""
    if human is None:
        return None
    text = human.strip().lower()
    if not text:
        return None
    if _PERCENT.search(text):
        return None
    m = _NUMBER.search(text)
    if m:
        try:
            return Decimal(m.group(0).replace(",", ""))
        except InvalidOperation:
            return None
    if _UNLIMITED.search(text) or text.startswith("all "):
        return "unlimited"
    return None


def is_upper_bound(human: str | None) -> bool:
    """'at most 1 ETH', 'up to 500 USDC': the words fix a ceiling, not the amount."""
    return bool(human) and bool(_UPPER_BOUND.search(human))


def is_lower_bound(human: str | None) -> bool:
    """'at least 0.1 WETH', 'a minimum of 5 ETH': the words fix a floor, not the amount."""
    return bool(human) and bool(_LOWER_BOUND.search(human))


def is_approximate(human: str | None) -> bool:
    """'about 2 ETH', '~500 USDC': the words fix a figure loosely."""
    return bool(human) and bool(_APPROX.search(human))


def bounds(human: str | None, base: int | None) -> dict[str, Any]:
    """The CanonMovement amount fields for a forward-pass amount: exact, a ceiling, a floor, a
    loose figure, or nothing fixed. Both a floor and a ceiling ('between') is treated as a floor
    and a ceiling together."""
    if base is None:
        return {"amount_base": None}
    upper, lower, approx = is_upper_bound(human), is_lower_bound(human), is_approximate(human)
    if not (upper or lower or approx):
        return {"amount_base": base}
    out: dict[str, Any] = {"amount_base": None}
    if upper:
        out["amount_max_base"] = base
    if lower:
        out["amount_min_base"] = base
    if approx and not (upper or lower):
        out["amount_approx"] = True
        out["amount_min_base"] = int(base * (1 - APPROX_TOLERANCE))
        out["amount_max_base"] = int(base * (1 + APPROX_TOLERANCE)) + 1
    return out


def allowance_value(human: str | None, base: int | None) -> int | str | None:
    """Canonical allowance: 'unlimited', 'zero', an int, or None when unknown."""
    if base is not None:
        if base >= UINT256_MAX:
            return "unlimited"
        return "zero" if base == 0 else base
    v = parse_amount(human)
    if v == "unlimited":
        return "unlimited"
    if v is None:
        return None
    return "zero" if v == 0 else None  # a bare number without decimals is resolved by the caller


# --------------------------------------------------------------------------- rendering


def render_party(p: Party) -> str:
    return p.label if p.resolved or not p.label else f"{p.label}?"


def render_movement(m: CanonMovement) -> str:
    amt = m.amount_human or (str(m.amount_base) if m.amount_base is not None else "any amount")
    label = m.asset.label
    what = amt if label.lower() in amt.lower() else f"{amt} {label}"
    return f"{what} {render_party(m.from_party)} -> {render_party(m.to_party)}"


def render_permission(p: CanonPermission) -> str:
    allow = "any" if p.new_allowance is None else str(p.new_allowance)
    return f"allowance {p.asset.label} {render_party(p.owner)} -> {render_party(p.spender)}: {allow}"


def render_config(c: CanonConfig) -> str:
    old = f" (was {c.old})" if c.old is not None else ""
    return f"{c.field} = {c.new}{old}"


# --------------------------------------------------------------------------- forward


def from_forward(form: ExpectedEffects, description: str, r: Resolver) -> CanonEffects:
    out = CanonEffects(source="forward", nothing_else=form.nothing_else, questions=list(form.questions_for_human))
    words_approve = bool(_APPROVE_WORDS.search(description))
    for m in form.movements:
        asset = r.asset(m.asset)
        f, t = r.party(m.from_name), r.party(m.to_name)
        ok = checker.phrase_supported(m.cites, description)
        base = r.to_base(m.amount_human, asset)
        cm = CanonMovement(
            asset=asset, from_party=f, to_party=t, **bounds(m.amount_human, base), amount_human=m.amount_human,
            direction=r.direction(f, t), cites=[m.cites], cited_ok=ok, source="forward",
        )
        out.movements.append(cm)
        if not ok:
            out.unsupported.append(render_movement(cm))
    for p in form.permission_changes:
        asset = r.asset(p.asset)
        base = r.to_base(p.amount_human, asset)
        ok = checker.phrase_supported(p.cites, description)
        cp = CanonPermission(
            asset=asset, owner=r.party(p.owner_name), spender=r.party(p.spender_name),
            new_allowance=allowance_value(p.amount_human, base), implied=not words_approve,
            cites=[p.cites], cited_ok=ok, source="forward",
        )
        out.permissions.append(cp)
        if not ok:
            out.unsupported.append(render_permission(cp))
    for c in form.safe_config_changes:
        ok = checker.phrase_supported(c.cites, description)
        for cc in _config_items(c.kind, c.owner_name, c.threshold_after, [c.cites], r, "forward"):
            cc.cited_ok = ok
            out.configs.append(cc)
            if not ok:
                out.unsupported.append(render_config(cc))
    return out


def _config_items(kind: str, owner: str | None, threshold_after: int | None, cites: list[str], r: Resolver,
                  source: str) -> list[CanonConfig]:
    items: list[CanonConfig] = []
    field = {"add_owner": "owners_add", "remove_owner": "owners_remove", "swap_owner": "owners_swap"}.get(kind)
    if field and owner:
        p = r.party(owner)
        items.append(CanonConfig(field=field, new=p.address or p.label, cites=cites, source=source))
    if threshold_after is not None:
        items.append(CanonConfig(field="threshold", new=str(threshold_after), cites=cites, source=source))
    return items


# --------------------------------------------------------------------------- backward


def from_backward(narr: Narration, r: Resolver) -> CanonEffects:
    bundle = r.bundle
    out = CanonEffects(source="backward")
    for e in narr.effects:
        missing = checker.check_citations(e.cites, bundle)
        ce = CanonEffect(sentence=e.sentence, severity=e.severity, cites=list(e.cites), cited_ok=not missing)
        out.effects.append(ce)
        if missing:
            out.uncited.append(f"effect '{e.sentence}' cites unknown {missing}")

    def severity_for(cites: list[str]) -> Severity:
        best: Severity = "notable"
        for e in out.effects:
            if set(e.cites) & set(cites) and SEVERITY_RANK[e.severity] > SEVERITY_RANK[best]:
                best = e.severity
        return best

    for m in narr.movements:
        missing = checker.check_citations(m.cites, bundle)
        asset = r.asset(m.asset, m.cites)
        f, t = r.party(m.from_name), r.party(m.to_name)
        base = int(m.amount_base_units) if m.amount_base_units.strip().lstrip("-").isdigit() else None
        cm = CanonMovement(
            asset=asset, from_party=f, to_party=t, amount_base=base, amount_human=m.amount_human,
            direction=r.direction(f, t), severity=severity_for(m.cites), cites=list(m.cites), cited_ok=not missing,
            source="backward",
        )
        out.movements.append(cm)
        if missing:
            out.uncited.append(f"movement {render_movement(cm)} cites unknown {missing}")
    for p in narr.permission_changes:
        missing = checker.check_citations(p.cites, bundle)
        asset = r.asset(p.asset, p.cites)
        base = r.to_base(p.amount_human, asset)
        cp = CanonPermission(
            asset=asset, owner=r.party(p.owner_name), spender=r.party(p.spender_name),
            new_allowance=allowance_value(p.amount_human, base), severity=severity_for(p.cites), cites=list(p.cites),
            cited_ok=not missing, source="backward",
        )
        out.permissions.append(cp)
        if missing:
            out.uncited.append(f"permission {render_permission(cp)} cites unknown {missing}")
    for c in narr.safe_config_changes:
        missing = checker.check_citations(c.cites, bundle)
        for cc in _config_items(c.kind, c.owner_name, c.threshold_after, list(c.cites), r, "backward"):
            cc.severity = severity_for(c.cites)
            cc.cited_ok = not missing
            out.configs.append(cc)
            if missing:
                out.uncited.append(f"config {render_config(cc)} cites unknown {missing}")
    return out


# --------------------------------------------------------------------------- helpers for truth.py


def movement(r: Resolver, asset: Asset, from_addr: str, to_addr: str, amount_base: int | None, cites: list[str],
             source: str = "truth", human: str | None = None) -> CanonMovement:
    f, t = r.party(from_addr), r.party(to_addr)
    return CanonMovement(
        asset=asset, from_party=f, to_party=t, amount_base=amount_base, amount_human=human,
        direction=r.direction(f, t), cites=cites, source=source,
    )


def human_amount(base: int, asset: Asset) -> str:
    if asset.decimals is None:
        return str(base)
    q = Decimal(base) / (Decimal(10) ** asset.decimals)
    text = f"{q.normalize():f}"
    return f"{text} {asset.label}"


def any_dict(x: Any) -> dict[str, Any]:
    return x.model_dump(mode="json") if hasattr(x, "model_dump") else dict(x)
