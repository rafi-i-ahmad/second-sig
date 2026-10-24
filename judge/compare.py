"""Layer 4: reconcile what the words promised with what the bytes did.

``reconcile(expected, observed, resolver)`` matches the backward pass's canonical items
against the forward pass's and returns a CompareResult. Pure, deterministic, no model.

Tiers, best first. Each match records the weakest rule it needed:
- exact: same asset, direction, parties and amount.
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

Only notable and critical observed items take part in the verdict. Info effects go to the
log. An observed item whose citations do not resolve is never explained (fail closed).
An expected item whose phrase is not in the description explains nothing.
"""

from __future__ import annotations

from judge.canon import (
    Resolver, render_config, render_movement, render_permission,
)
from judge.schemas import (
    CanonConfig, CanonEffects, CanonMovement, CanonPermission, CompareResult, Match, MatchTier, Unexplained,
)

TIER_RANK: dict[MatchTier, int] = {
    "exact": 0, "amount_unconstrained": 1, "counterparty_via_callee": 2, "party_unresolved": 3,
    "asset_unresolved": 4, "inbound_from_callee": 5, "internal_to_callee": 6, "unmatched": 9,
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
    if exp.amount_max_base is not None:
        # 'at most 1 ETH': anything up to the ceiling is what the words allow
        return "amount_unconstrained" if obs.amount_base <= exp.amount_max_base else None
    if exp.amount_human is not None and obs.asset.decimals is not None and not exp.amount_max_base:
        # the words fixed a number but the asset's decimals were only known from the trace
        base = r.to_base(exp.amount_human, obs.asset)
        if base is not None:
            from judge.canon import is_upper_bound
            if is_upper_bound(exp.amount_human):
                return "amount_unconstrained" if obs.amount_base <= base else None
            return "exact" if base == obs.amount_base else None
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
    tier = _worst(a, amt, f, t)
    notes = []
    if exp.implied:
        notes.append("expected item was implied by the words, not stated")
    return Match(kind="movement", expected=render_movement(exp), observed=render_movement(obs), tier=tier, notes=notes)


def match_permission(exp: CanonPermission, obs: CanonPermission, r: Resolver) -> Match | None:
    a = _asset_tier(exp, obs)
    if a is None:
        return None
    o = _party_tier(exp.owner, obs.owner, obs.cites, r)
    s = _party_tier(exp.spender, obs.spender, obs.cites, r)
    if o is None or s is None or s == "counterparty_via_callee":
        return None  # an allowance to a different spender is never explained by the call path
    if exp.new_allowance is None:
        amt: MatchTier = "amount_unconstrained"
    elif exp.new_allowance == obs.new_allowance:
        amt = "exact"
    else:
        return None
    notes = ["expected item was implied by the words, not stated"] if exp.implied else []
    return Match(kind="permission", expected=render_permission(exp), observed=render_permission(obs),
                 tier=_worst(a, o, s, amt), notes=notes)


def match_config(exp: CanonConfig, obs: CanonConfig) -> Match | None:
    if exp.field != obs.field:
        return None
    if exp.new is not None and obs.new is not None and exp.new.lower() != obs.new.lower():
        return None
    tier: MatchTier = "exact" if exp.new is not None else "amount_unconstrained"
    return Match(kind="config", expected=render_config(exp), observed=render_config(obs), tier=tier)


# --------------------------------------------------------------------------- reconcile


def reconcile(expected: CanonEffects, observed: CanonEffects, r: Resolver) -> CompareResult:
    res = CompareResult(
        uncited=list(observed.uncited), unsupported=list(expected.unsupported),
        nothing_else=expected.nothing_else, questions=list(expected.questions),
    )
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
        if not e.cited_ok:
            res.observed_unexplained.append(Unexplained(
                kind="effect", item=e.sentence, severity=e.severity, cites=e.cites,
                reason="citations do not resolve; treated as unexplained"))
        elif e.severity == "info":
            res.info_effects.append(e.sentence)
        elif set(e.cites) & explained_cites:
            pass
        else:
            res.observed_unexplained.append(Unexplained(
                kind="effect", item=e.sentence, severity=e.severity, cites=e.cites,
                reason="no matched item shares its evidence"))

    res.tiers = sorted({m.tier for m in res.matched}, key=lambda t: TIER_RANK[t])
    return res


def _is_internal(obs: CanonMovement, expected: CanonEffects, callees, r: Resolver) -> bool:
    """Bookkeeping between contracts inside a licensed call, and nothing more. Refused when:
    - the asset is one the words expect the Safe to *receive* (a swap's output delivered to a
      third party is a diversion, not plumbing), or
    - the recipient has no code (a plain address inside a protocol call is someone's wallet)."""
    if not any(r.inside_call_to(obs.cites, p.address) for p in callees):
        return False
    expected_in = {m.asset.address for m in expected.movements if m.direction == "in" and m.asset.resolved}
    expected_in_labels = {m.asset.label.lower() for m in expected.movements if m.direction == "in"}
    if obs.asset.address in expected_in or obs.asset.label.lower() in expected_in_labels:
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
