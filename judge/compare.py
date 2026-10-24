"""Layer 4: reconcile what the words promised with what the bytes did.

``reconcile(expected, observed, resolver)`` matches the backward pass's canonical items
against the forward pass's and returns a CompareResult. Pure, deterministic, no model.

Tiers, best first. Each match records the weakest rule it needed:
- exact: same asset, direction, parties and amount.
- amount_bounded: the words fixed a ceiling ('up to'), a floor ('at least') or a loose figure
  ('about'), and the observed amount is inside it.
- amount_unconstrained: the words fixed no amount; any amount for that asset and route.
- counterparty_via_callee: the counterparty differs, but the observed movement happened
  inside the Safe's call into the expected counterparty (USDC lands in Aave's aToken
  contract because the Pool put it there; a swap's output leaves WETH9 because the router
  unwrapped it). Where a called contract puts the money is that contract's business; the
  Safe's exposure is the same.
- party_unresolved: the words named a party the address book does not know; the trace
  shows a raw address in that position with everything else agreeing.
- asset_unresolved: likewise for the asset (the words say 'aUSDC', the book has no entry).
- inbound_from_callee: the Safe receives an asset the words did not name, from inside its
  call into a contract the words license (a deposit's receipt token, minted by the Pool).
  Receiving can never drain the Safe; the outbound side still has to match on its own.
- internal_to_callee: an observed movement touching neither side of the Safe, inside a call
  the Safe made (pair -> router legs), between contracts, of an asset the words do not expect
  the Safe to receive. Bookkeeping, logged, never a finding on its own. A licensed call that
  delivers the Safe's purchase to someone else is not internal and stays unexplained.

What leaves the Safe must be pinned down by the words. An outbound movement is explained only
by an expected one with a known asset, a known recipient and an amount or a bound, so the
weaker tiers (amount_unconstrained, party_unresolved, asset_unresolved) apply to what the Safe
receives, never to what it sends: "pay Dana's new wallet", "send 1,000 USDT" with no USDT in the
book, or "pay Dana" with no amount explain nothing and the signers are asked. Likewise an
allowance is explained only by an expected one with a known token, a known spender and an amount.

Only notable and critical observed items take part in the verdict. Info effects go to the
log, with one exception: an info effect that cites a storage write no code layout and no
corroborated source claim has labelled is *not* explained. A model calling an unknown write
"bookkeeping" with nothing behind it would be lowering suspicion on its own; the write stays
unexplained at notable until judge/corroborate.py labels it. ``raised`` carries writes the
source reader read as control or asset changes; those are unexplained whatever the backward
pass said. An observed item whose citations do not resolve is never explained (fail closed).
An expected item whose phrase is not in the description explains nothing.

Coverage: the backward pass may add detail but cannot leave anything out. Code checks the
narration against the bundle: every net decrease of a Safe balance must equal the net of the
listed movements in that asset, every Approval the Safe granted needs a listed allowance for that
token and spender, and every owner or threshold change the Safe announced needs a listed config
change with that value. A gap is unexplained: notable, or critical for the Safe's configuration.
A forged event can only add something to account for, never take anything away.
"""

from __future__ import annotations

from decimal import Decimal

from eth_utils import to_checksum_address

from judge.canon import (
    Resolver, render_config, render_movement, render_permission,
)
from judge.schemas import (
    CanonConfig, CanonEffects, CanonMovement, CanonPermission, CompareResult, Event, Match, MatchTier, Unexplained,
)

# Tiers that leave something open: fine for what the Safe receives, never for what it sends.
_OPEN_TIERS: set[MatchTier] = {"amount_unconstrained", "party_unresolved", "asset_unresolved"}

TIER_RANK: dict[MatchTier, int] = {
    "exact": 0, "amount_bounded": 1, "amount_unconstrained": 2, "counterparty_via_callee": 3, "party_unresolved": 4,
    "asset_unresolved": 5, "inbound_from_callee": 6, "internal_to_callee": 7, "unmatched": 9,
}


def _worst(*tiers: MatchTier) -> MatchTier:
    return max(tiers, key=lambda t: TIER_RANK[t])


# --------------------------------------------------------------------------- item matchers


def _asset_tier(exp, obs) -> MatchTier | None:
    if exp.asset.resolved and obs.asset.resolved:
        return "exact" if exp.asset.address == obs.asset.address else None
    if not exp.asset.resolved and obs.asset.resolved:
        return "asset_unresolved"
    if exp.asset.resolved and not obs.asset.resolved:
        return None  # the trace side always has an address; refusing here fails closed
    return "asset_unresolved" if exp.asset.label.lower() == obs.asset.label.lower() else None


def _amount_tier(exp: CanonMovement, obs: CanonMovement, r: Resolver) -> MatchTier | None:
    if obs.amount_base is None:
        return None
    if exp.amount_base is not None:
        return "exact" if exp.amount_base == obs.amount_base else None
    if exp.amount_max_base is not None or exp.amount_min_base is not None:
        # 'up to', 'at least', 'about': inside the bound is what the words allow
        lo = exp.amount_min_base if exp.amount_min_base is not None else 0
        hi = exp.amount_max_base if exp.amount_max_base is not None else None
        inside = obs.amount_base >= lo and (hi is None or obs.amount_base <= hi)
        return "amount_bounded" if inside else None
    if exp.amount_human is not None and obs.asset.decimals is not None:
        # the words fixed a number but the asset's decimals were only known from the trace
        from judge.canon import bounds
        base = r.to_base(exp.amount_human, obs.asset)
        if base is not None:
            b = bounds(exp.amount_human, base)
            if b.get("amount_base") is not None:
                return "exact" if base == obs.amount_base else None
            lo = b.get("amount_min_base", 0) or 0
            hi = b.get("amount_max_base")
            return "amount_bounded" if obs.amount_base >= lo and (hi is None or obs.amount_base <= hi) else None
    return "amount_unconstrained"


def _party_tier(exp_party, obs_party, obs_cites: list[str], r: Resolver) -> MatchTier | None:
    if exp_party.resolved and obs_party.resolved:
        if exp_party.address == obs_party.address:
            return "exact"
        if r.inside_call_to(obs_cites, exp_party.address):
            return "counterparty_via_callee"
        return None
    if not exp_party.resolved and obs_party.resolved:
        return "party_unresolved"
    return None


def match_movement(exp: CanonMovement, obs: CanonMovement, r: Resolver) -> Match | None:
    if exp.direction != obs.direction:
        return None
    a = _asset_tier(exp, obs)
    if a is None:
        return None
    amt = _amount_tier(exp, obs, r)
    if amt is None:
        return None
    f = _party_tier(exp.from_party, obs.from_party, obs.cites, r)
    t = _party_tier(exp.to_party, obs.to_party, obs.cites, r)
    if f is None or t is None:
        return None
    if obs.direction == "out" and _OPEN_TIERS & {a, amt, f, t}:
        return None  # an outflow the words leave open (asset, recipient or amount) explains nothing
    tier = _worst(a, amt, f, t)
    notes = []
    if exp.implied:
        notes.append("expected item was implied by the words, not stated")
    return Match(kind="movement", expected=render_movement(exp), observed=render_movement(obs), tier=tier, notes=notes)


def match_permission(exp: CanonPermission, obs: CanonPermission, r: Resolver) -> Match | None:
    if exp.new_allowance is None or not exp.asset.resolved or not exp.spender.resolved:
        return None  # "set Ravi's allowance": an allowance the words leave open explains nothing
    a = _asset_tier(exp, obs)
    if a is None:
        return None
    o = _party_tier(exp.owner, obs.owner, obs.cites, r)
    s = _party_tier(exp.spender, obs.spender, obs.cites, r)
    if o is None or s is None or s == "counterparty_via_callee":
        return None  # an allowance to a different spender is never explained by the call path
    if exp.new_allowance != obs.new_allowance:
        return None
    notes = ["expected item was implied by the words, not stated"] if exp.implied else []
    return Match(kind="permission", expected=render_permission(exp), observed=render_permission(obs),
                 tier=_worst(a, o, s, "exact"), notes=notes)


def match_config(exp: CanonConfig, obs: CanonConfig) -> Match | None:
    if exp.field != obs.field:
        return None
    if exp.new is not None and obs.new is not None and exp.new.lower() != obs.new.lower():
        return None
    tier: MatchTier = "exact" if exp.new is not None else "amount_unconstrained"
    return Match(kind="config", expected=render_config(exp), observed=render_config(obs), tier=tier)


# --------------------------------------------------------------------------- reconcile


def reconcile(expected: CanonEffects, observed: CanonEffects, r: Resolver, raised: dict[str, str] | None = None,
              explained_slots: list[str] | None = None) -> CompareResult:
    res = CompareResult(
        uncited=list(observed.uncited), unsupported=list(expected.unsupported),
        nothing_else=expected.nothing_else, questions=list(expected.questions),
        explained_slots=list(explained_slots or []),
    )
    raised = raised or {}
    unlabelled = {w.id for w in r.bundle.storage_diff if not w.label}
    explained_cites: set[str] = set()
    used_expected: set[int] = set()

    def usable(items):
        return [(i, x) for i, x in enumerate(items) if x.cited_ok and i not in used_expected]

    # movements
    for obs in observed.movements:
        if not obs.cited_ok:
            res.observed_unexplained.append(Unexplained(
                kind="movement", item=render_movement(obs), severity=obs.severity or "notable", cites=obs.cites,
                reason="citations do not resolve; treated as unexplained"))
            continue
        if obs.severity == "info":
            res.info_effects.append(f"movement {render_movement(obs)}")
            explained_cites |= set(obs.cites)
            continue
        best: tuple[int, Match] | None = None
        for i, exp in usable(expected.movements):
            m = match_movement(exp, obs, r)
            if m and (best is None or TIER_RANK[m.tier] < TIER_RANK[best[1].tier]):
                best = (i, m)
        callees = _callees(expected, r)
        if best:
            used_expected.add(best[0])
            res.matched.append(best[1])
            explained_cites |= set(obs.cites)
        elif obs.direction == "in" and any(r.inside_call_to(obs.cites, p.address) for p in callees):
            res.matched.append(Match(kind="movement", expected="(received from inside a call the words license)",
                                     observed=render_movement(obs), tier="inbound_from_callee",
                                     notes=["receiving an asset cannot drain the Safe"]))
            explained_cites |= set(obs.cites)
        elif obs.direction == "third_party" and _is_internal(obs, expected, callees, r):
            res.matched.append(Match(kind="movement", expected="(inside a call the words license)",
                                     observed=render_movement(obs), tier="internal_to_callee"))
            res.info_effects.append(f"internal movement {render_movement(obs)}")
            explained_cites |= set(obs.cites)
        else:
            res.observed_unexplained.append(Unexplained(
                kind="movement", item=render_movement(obs), severity=obs.severity or "notable", cites=obs.cites,
                reason="no expected movement matches (asset, route, amount)"))
    for i, exp in enumerate(expected.movements):
        if i not in used_expected and exp.cited_ok:
            res.expected_unobserved.append(f"movement {render_movement(exp)}")

    # permissions
    used_expected = set()
    for obs in observed.permissions:
        if not obs.cited_ok:
            res.observed_unexplained.append(Unexplained(
                kind="permission", item=render_permission(obs), severity=obs.severity or "notable", cites=obs.cites,
                reason="citations do not resolve; treated as unexplained"))
            continue
        if obs.new_allowance == "zero" and obs.severity == "info":
            res.info_effects.append(f"permission {render_permission(obs)}")
            explained_cites |= set(obs.cites)
            continue
        best = None
        for i, exp in usable(expected.permissions):
            m = match_permission(exp, obs, r)
            if m and (best is None or TIER_RANK[m.tier] < TIER_RANK[best[1].tier]):
                best = (i, m)
        if best:
            used_expected.add(best[0])
            res.matched.append(best[1])
            explained_cites |= set(obs.cites)
        else:
            res.observed_unexplained.append(Unexplained(
                kind="permission", item=render_permission(obs), severity=obs.severity or "notable", cites=obs.cites,
                reason="no expected allowance matches (asset, spender, amount)"))
    for i, exp in enumerate(expected.permissions):
        if i not in used_expected and exp.cited_ok:
            res.expected_unobserved.append(f"permission {render_permission(exp)}")

    # config
    used_expected = set()
    for obs in observed.configs:
        if not obs.cited_ok:
            res.observed_unexplained.append(Unexplained(
                kind="config", item=render_config(obs), severity=obs.severity or "critical", cites=obs.cites,
                reason="citations do not resolve; treated as unexplained"))
            continue
        best = None
        for i, exp in usable(expected.configs):
            m = match_config(exp, obs)
            if m and (best is None or TIER_RANK[m.tier] < TIER_RANK[best[1].tier]):
                best = (i, m)
        if best:
            used_expected.add(best[0])
            res.matched.append(best[1])
            explained_cites |= set(obs.cites)
        else:
            res.observed_unexplained.append(Unexplained(
                kind="config", item=render_config(obs), severity=obs.severity or "critical", cites=obs.cites,
                reason="no expected Safe config change matches"))
    for i, exp in enumerate(expected.configs):
        if i not in used_expected and exp.cited_ok:
            res.expected_unobserved.append(f"config {render_config(exp)}")

    # sentences: everything the trace showed must be covered by something matched
    for e in observed.effects:
        hot = [c for c in e.cites if c in raised]
        dark = [c for c in e.cites if c in unlabelled]
        if not e.cited_ok:
            res.observed_unexplained.append(Unexplained(
                kind="effect", item=e.sentence, severity=e.severity, cites=e.cites,
                reason="citations do not resolve; treated as unexplained"))
        elif hot:
            res.observed_unexplained.append(Unexplained(
                kind="effect", item=e.sentence, severity="notable" if e.severity == "info" else e.severity,
                cites=e.cites, reason=f"the source reader read {hot[0]} as {raised[hot[0]]}"))
        elif e.severity == "info" and dark:
            res.observed_unexplained.append(Unexplained(
                kind="effect", item=e.sentence, severity="notable", cites=e.cites,
                reason=f"cites storage writes nobody has labelled ({', '.join(dark)}); 'info' from a model with "
                       "no layout and no source does not explain them"))
        elif e.severity == "info":
            res.info_effects.append(e.sentence)
        elif set(e.cites) & explained_cites:
            pass
        else:
            res.observed_unexplained.append(Unexplained(
                kind="effect", item=e.sentence, severity=e.severity, cites=e.cites,
                reason="no matched item shares its evidence"))

    res.observed_unexplained += _coverage(observed, r)
    res.ignored_labels = list(r.ignored_labels)
    res.tiers = sorted({m.tier for m in res.matched}, key=lambda t: TIER_RANK[t])
    return res


# --------------------------------------------------------------------------- coverage


_CONFIG_EVENTS = {"AddedOwner": ("owners_add", "owners_swap"), "RemovedOwner": ("owners_remove", "owners_swap"),
                  "ChangedThreshold": ("threshold",)}


def _human(base: int, decimals: int | None) -> str:
    if decimals is None:
        return f"{base} base units"
    return f"{Decimal(base).scaleb(-decimals).normalize():f}"


def _coverage(observed: CanonEffects, r: Resolver) -> list[Unexplained]:
    """What the bundle shows happened to the Safe that the narration does not account for."""
    out: list[Unexplained] = []
    bundle, safe = r.bundle, r.safe
    for b in bundle.balance_diff:
        if to_checksum_address(b.holder) != safe or b.delta >= 0:
            continue
        asset = "ETH" if b.asset == "ETH" else to_checksum_address(b.asset)
        net = 0
        for m in observed.movements:
            if m.cited_ok and m.asset.address == asset and m.amount_base is not None:
                net += {"out": -m.amount_base, "in": m.amount_base}.get(m.direction, 0)
        if net != b.delta:
            out.append(Unexplained(
                kind="movement", severity="notable", cites=[b.id],
                item=f"the Safe's {b.symbol or asset} balance falls by {_human(-b.delta, b.decimals)}; the listed "
                     f"movements account for {_human(-net, b.decimals)}",
                reason="the narration leaves part of this balance change out"))
    for e in bundle.events:
        values = [a.value for a in e.args or []]
        if e.name == "Approval" and len(values) >= 2 and _is_addr(values[0]) and to_checksum_address(values[0]) == safe:
            token, spender = to_checksum_address(e.address), to_checksum_address(values[1]) if _is_addr(values[1]) else None
            if not any(p.cited_ok and p.asset.address == token and p.spender.address == spender
                       for p in observed.permissions):
                out.append(Unexplained(
                    kind="permission", severity="notable", cites=[e.id],
                    item=f"the Safe granted an allowance on {r.display(token)} to {r.display(spender or '?')} "
                         f"({e.id}) that the narration does not list",
                    reason="the narration leaves out an allowance the Safe granted"))
        if e.name in _CONFIG_EVENTS and to_checksum_address(e.address) == safe and values:
            value = to_checksum_address(values[0]) if _is_addr(values[0]) else str(values[0])
            fields = _CONFIG_EVENTS[e.name]
            if not any(c.cited_ok and c.field in fields and (c.new or "").lower() == value.lower()
                       for c in observed.configs):
                out.append(Unexplained(
                    kind="config", severity="critical", cites=[e.id],
                    item=f"the Safe announced {e.name} {r.display(value) if value.startswith('0x') else value} "
                         f"({e.id}) and the narration does not list it",
                    reason="the narration leaves out a change to the Safe's owners or threshold"))
    return out


def _is_addr(value: object) -> bool:
    return isinstance(value, str) and value.startswith("0x") and len(value) == 42


def _is_internal(obs: CanonMovement, expected: CanonEffects, callees, r: Resolver) -> bool:
    """Bookkeeping between contracts inside a licensed call, and nothing more. Refused when:
    - the asset is one the words expect the Safe to *receive* and it goes anywhere but a contract
      the words license (a swap's output delivered to a third party is a diversion, not plumbing;
      WETH unwrapping the output into the router the words name is plumbing, and the router's
      delivery to the Safe is still checked against the words), or
    - the recipient has no code (a plain address inside a protocol call is someone's wallet)."""
    if not any(r.inside_call_to(obs.cites, p.address) for p in callees):
        return False
    expected_in = {m.asset.address for m in expected.movements if m.direction == "in" and m.asset.resolved}
    expected_in_labels = {m.asset.label.lower() for m in expected.movements if m.direction == "in"}
    licensed = {p.address for p in callees}
    if (obs.asset.address in expected_in or obs.asset.label.lower() in expected_in_labels) \
            and obs.to_party.address not in licensed:
        return False
    to = obs.to_party.address
    if to is None:
        return False
    src = r.bundle.sources.get(to)
    return bool(src and src.has_code)


def _callees(expected: CanonEffects, r: Resolver):
    """Contracts the words license the Safe to deal with: every resolved non-Safe party."""
    out = []
    for m in expected.movements:
        for p in (m.from_party, m.to_party):
            if p.resolved and p.address != r.safe:
                out.append(p)
    for p in expected.permissions:
        if p.spender.resolved:
            out.append(p.spender)
    return out
