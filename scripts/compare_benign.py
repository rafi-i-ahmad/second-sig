"""Three-way comparison report: ground truth vs forward vs backward, per case.

For every case in fixtures/cases/match, ask and demo (reject with --include-reject), load the
bundle and the recorded forward and backward forms from fixtures/outputs/. With --live, run
the pass whose output is missing (and save it in the same format the tests use); without it,
a missing form is reported and the verdict is ASK, as the pipeline would say.

Writes reports/compare/<id>.md and <id>.json, then prints a summary table. The JSON is
self-contained: every residual carries the bundle entries it cites, slot labels, and the
frames that could have written each residual slot, so another agent can pick one up later
without re-running anything.

    uv run python scripts/compare_benign.py [--live] [--include-reject] [--only <id>[,<id>...]]

With --live, a pass whose recorded output is missing is run and saved; a recorded one is never
re-run, and neither is a recorded source-reader classification (the ~98k-token Argon call).

Ablation: --backward-variant NAME [--backward-model M --backward-thinking T] reads and records the
backward form as <id>.backward.NAME.json instead, and writes the reports to reports/compare-NAME/,
so a second model's narration can be set against the recorded forward forms and the truth.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from judge import canon, compare, truth, verdict
from judge.canon import Resolver, render_config, render_movement, render_permission
from judge.schemas import CanonEffects, CompareResult, EvidenceBundle, ExpectedEffects, Narration, SlotWrite, Verdict

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "fixtures"
OUTPUTS = FIXTURES / "outputs"
REPORTS = REPO / "reports" / "compare"


# --------------------------------------------------------------------------- loading


def load_case(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_bundle(cid: str) -> EvidenceBundle | None:
    p = FIXTURES / "bundles" / f"{cid}.bundle.json"
    return EvidenceBundle.model_validate_json(p.read_text(encoding="utf-8")) if p.exists() else None


def load_forward(cid: str) -> ExpectedEffects | None:
    p = OUTPUTS / f"{cid}.forward.json"
    return ExpectedEffects.model_validate(json.loads(p.read_text(encoding="utf-8"))["expected_effects"]) if p.exists() else None


def backward_path(cid: str, variant: str | None = None) -> Path:
    return OUTPUTS / (f"{cid}.backward.{variant}.json" if variant else f"{cid}.backward.json")


def load_backward(cid: str, variant: str | None = None) -> Narration | None:
    p = backward_path(cid, variant)
    return Narration.model_validate(json.loads(p.read_text(encoding="utf-8"))["narration"]) if p.exists() else None


def _save(path: Path, model: str, thinking: str, interaction_id: str, latency_ms: int, key: str, form: Any) -> None:
    OUTPUTS.mkdir(exist_ok=True)
    path.write_text(json.dumps({"model": model, "thinking": thinking, "interaction_id": interaction_id,
                                "latency_ms": latency_ms, key: form.model_dump(mode="json")}, indent=2) + "\n",
                    encoding="utf-8", newline="\n")


def run_forward_live(case: dict[str, Any]) -> ExpectedEffects:
    from judge.jobs import forward
    form, iid, ms = forward.run(case["description"], case["address_book"], case["safe"])
    _save(OUTPUTS / f"{case['id']}.forward.json", forward.DEFAULT_MODEL, forward.DEFAULT_THINKING, iid, ms,
          "expected_effects", form)
    print(f"  forward  live {ms:6d} ms  {iid}")
    return form


def run_backward_live(case: dict[str, Any], bundle: EvidenceBundle, variant: str | None = None,
                      model: str | None = None, thinking: str | None = None) -> Narration:
    from judge.jobs import backward
    model, thinking = model or backward.DEFAULT_MODEL, thinking or backward.DEFAULT_THINKING
    timeout = 120.0 if model == backward.DEFAULT_MODEL else 600.0
    form, iid, ms = backward.run(bundle, case["address_book"], case["safe"], model=model, thinking=thinking,
                                 timeout_s=timeout)
    _save(backward_path(case["id"], variant), model, thinking, iid, ms, "narration", form)
    print(f"  backward live {ms:6d} ms  {iid}  ({model}, {thinking})")
    return form


# --------------------------------------------------------------------------- grading a pass against truth


def _same_asset(a, b) -> bool:
    if a.asset.resolved and b.asset.resolved:
        return a.asset.address == b.asset.address
    return a.asset.label.lower() == b.asset.label.lower()


def grade(truth_c: CanonEffects, pass_c: CanonEffects, r: Resolver) -> dict[str, list[str]]:
    """missing: in truth, not in the pass. extra: in the pass, not in truth. wrong_amount / wrong_party:
    the pass found the item but got a number or a counterparty wrong (callee-internal recipients allowed)."""
    g: dict[str, list[str]] = {"missing": [], "extra": [], "wrong_amount": [], "wrong_party": []}
    used: set[int] = set()
    for t in truth_c.movements:
        cands = [(i, m) for i, m in enumerate(pass_c.movements)
                 if i not in used and _same_asset(t, m) and m.direction == t.direction]
        if not cands:
            g["missing"].append(f"movement {render_movement(t)}")
            continue
        i, m = cands[0]
        used.add(i)
        if m.amount_base is not None and t.amount_base is not None and m.amount_base != t.amount_base:
            g["wrong_amount"].append(f"movement {render_movement(m)} (truth {render_movement(t)})")
        other_t = t.to_party if t.direction == "out" else t.from_party
        other_m = m.to_party if m.direction == "out" else m.from_party
        if other_t.resolved and other_m.resolved and other_t.address != other_m.address \
                and not r.inside_call_to(m.cites, other_t.address) and not r.inside_call_to(t.cites, other_m.address):
            g["wrong_party"].append(f"movement {render_movement(m)} (truth {render_movement(t)})")
    for i, m in enumerate(pass_c.movements):
        if i not in used and m.direction != "third_party" and m.severity != "info":
            g["extra"].append(f"movement {render_movement(m)}")

    used = set()
    for t in truth_c.permissions:
        cands = [(i, p) for i, p in enumerate(pass_c.permissions) if i not in used and _same_asset(t, p)
                 and (not (t.spender.resolved and p.spender.resolved) or t.spender.address == p.spender.address)]
        if not cands:
            g["missing"].append(f"permission {render_permission(t)}")
            continue
        i, p = cands[0]
        used.add(i)
        if p.new_allowance is not None and p.new_allowance != t.new_allowance:
            g["wrong_amount"].append(f"permission {render_permission(p)} (truth {render_permission(t)})")
    for i, p in enumerate(pass_c.permissions):
        if i not in used:
            g["extra"].append(f"permission {render_permission(p)}")

    used = set()
    for t in truth_c.configs:
        cands = [(i, c) for i, c in enumerate(pass_c.configs) if i not in used and c.field == t.field
                 and (c.new is None or t.new is None or c.new.lower() == t.new.lower())]
        if not cands:
            g["missing"].append(f"config {render_config(t)}")
            continue
        used.add(cands[0][0])
    for i, c in enumerate(pass_c.configs):
        if i not in used:
            g["extra"].append(f"config {render_config(c)}")
    return g


# --------------------------------------------------------------------------- attribution


def attribute(cmp: CompareResult, fwd_grade: dict[str, list[str]] | None, bwd_grade: dict[str, list[str]] | None,
              tiers_by_observed: dict[str, str], expected_verdict: str | None) -> list[dict[str, str]]:
    """One line per discrepancy, by rule. Grades are None when a pass has no recorded form.

    For a case whose expected verdict is MATCH, a gap between the passes is one pass's fault.
    For a case expected to ASK or REJECT, the forward pass *should* lack what the bytes do (the
    words omit or contradict it): that gap is the real finding, not a fault."""
    out: list[dict[str, str]] = []
    benign = expected_verdict == "MATCH"

    def in_grade(g, key, text) -> bool:
        return g is not None and any(text in x for x in g[key])

    by_cites: dict[frozenset[str], str] = {}
    for u in cmp.observed_unexplained:
        if u.kind == "effect":
            continue  # sentences are attributed after the structured items, by shared evidence
        item = u.item
        if u.reason.startswith("citations do not resolve"):
            why = "backward_fault"  # a claim with no evidence behind it
        elif in_grade(bwd_grade, "extra", item):
            why = "backward_fault"  # backward alone has it; truth does not
        elif bwd_grade is not None and fwd_grade is not None and fwd_grade["missing"]:
            why = "forward_fault" if benign else "real_finding"  # truth and backward have it, forward does not
        elif not benign and bwd_grade is not None and not any(bwd_grade.values()):
            why = "real_finding"  # backward agrees with the bytes; the words are what differ
        else:
            why = "needs_investigation"
        by_cites[frozenset(u.cites)] = why
        out.append({"item": f"observed, unexplained [{u.severity}]: {item}", "attribution": why})
    for u in cmp.observed_unexplained:
        if u.kind != "effect":
            continue
        shared = next((why for cites, why in by_cites.items() if cites & set(u.cites)), None)
        if u.reason.startswith("citations do not resolve"):
            why = "backward_fault"
        elif shared:
            why = f"{shared} (same evidence as the item above)"
        else:
            why = "needs_investigation"
        out.append({"item": f"observed, unexplained [{u.severity}]: {u.item}", "attribution": why})
    for x in cmp.expected_unobserved:
        if in_grade(fwd_grade, "extra", x.split(" ", 1)[1] if " " in x else x):
            why = "forward_fault" if benign else "real_finding"  # forward alone has it: the words promise what the bytes do not do
        elif bwd_grade is not None and bwd_grade["missing"]:
            why = "backward_fault"  # truth and forward have it, backward does not
        elif not benign:
            why = "real_finding"  # the words promise what the bytes do not do
        else:
            why = "needs_investigation"
        out.append({"item": f"expected, not observed: {x}", "attribution": why})
    for obs, tier in tiers_by_observed.items():
        if tier in ("party_unresolved", "asset_unresolved"):
            out.append({"item": f"matched by {tier}: {obs}", "attribution": "address_book_gap"})
        elif tier in ("counterparty_via_callee", "inbound_from_callee", "internal_to_callee", "amount_unconstrained",
                      "amount_bounded"):
            out.append({"item": f"matched by {tier}: {obs}", "attribution": "tolerance_rule"})
    if not benign and fwd_grade is not None:
        for key in ("missing", "extra", "wrong_amount", "wrong_party"):
            for x in fwd_grade[key]:
                out.append({"item": f"forward vs truth ({key}): {x}",
                            "attribution": "real_finding" if key != "wrong_party" else "real_finding (wrong recipient)"})
    for x in cmp.info_effects:
        out.append({"item": f"info: {x}", "attribution": "bookkeeping"})
    if fwd_grade and bwd_grade:
        for key in ("extra", "missing", "wrong_amount", "wrong_party"):
            both = set(fwd_grade[key]) & set(bwd_grade[key])
            for x in both:
                out.append({"item": f"both passes agree, truth differs ({key}): {x}",
                            "attribution": "fixture_or_truth_error"})
    return out


# --------------------------------------------------------------------------- residual detail


def residual_detail(cmp: CompareResult, bundle: EvidenceBundle) -> list[dict[str, Any]]:
    frames = {c.id: c for c in bundle.call_tree}
    out = []
    for u in cmp.observed_unexplained:
        entries = []
        for cid in u.cites:
            e = bundle.entry(cid)
            if e is None:
                entries.append({"id": cid, "missing": True})
                continue
            d = e.model_dump(mode="json")
            if isinstance(e, SlotWrite):
                d["writers"] = [
                    {"id": f.id, "to": f.to_address, "function": f.function, "storage_context": f.storage_context}
                    for f in bundle.call_tree
                    if f.storage_context.lower() == e.contract.lower() and f.kind in ("CALL", "DELEGATECALL")
                ]
            entries.append(d)
        out.append({"item": u.item, "kind": u.kind, "severity": u.severity, "reason": u.reason, "evidence": entries})
    return out


# --------------------------------------------------------------------------- report


def lists(c: CanonEffects | None) -> dict[str, list[str]]:
    if c is None:
        return {"movements": ["(no form)"], "permissions": [], "configs": []}
    return {"movements": [render_movement(m) for m in c.movements],
            "permissions": [render_permission(p) for p in c.permissions],
            "configs": [render_config(x) for x in c.configs]}


def side_by_side(t: CanonEffects, f: CanonEffects | None, b: CanonEffects | None) -> str:
    lt, lf, lb = lists(t), lists(f), lists(b)
    rows = ["| | truth (bytes) | forward (words) | backward (trace) |", "| --- | --- | --- | --- |"]
    for key in ("movements", "permissions", "configs"):
        n = max(len(lt[key]), len(lf[key]), len(lb[key]), 1)
        for i in range(n):
            cell = lambda xs: xs[i] if i < len(xs) else ""  # noqa: E731
            rows.append(f"| {key if i == 0 else ''} | {cell(lt[key])} | {cell(lf[key])} | {cell(lb[key])} |")
    return "\n".join(rows)


def grade_md(name: str, g: dict[str, list[str]] | None) -> str:
    if g is None:
        return f"**{name} vs truth:** no recorded form.\n"
    total = sum(len(v) for v in g.values())
    if not total:
        return f"**{name} vs truth:** agrees.\n"
    lines = [f"**{name} vs truth:** {total} difference{'s' if total != 1 else ''}"]
    for k, v in g.items():
        for x in v:
            lines.append(f"- {k}: {x}")
    return "\n".join(lines) + "\n"


def report_md(case: dict[str, Any], v: Verdict, t: CanonEffects, f: CanonEffects | None, b: CanonEffects | None,
              fg, bg, attribution: list[dict[str, str]]) -> str:
    cmp = v.compare
    md = [f"# {case['id']}", "", f"**Description:** {case['description']}", "",
          f"**Expected verdict:** {case.get('expected_verdict', '?')}  **Computed:** {v.decision.value}", "",
          v.reasoning, ""]
    if v.question:
        md += [f"**Question for the signers:** {v.question}", ""]
    md += ["## The three canonical lists", "", side_by_side(t, f, b), ""]
    if t.notes:
        md += ["Truth notes: " + "; ".join(t.notes), ""]
    md += ["## Each pass against the truth", "", grade_md("Forward", fg), grade_md("Backward", bg)]
    md += ["## Forward against backward", ""]
    if cmp is None:
        md += ["No comparison: " + "; ".join(v.reasons), ""]
    else:
        md += ["| matched | tier |", "| --- | --- |"]
        md += [f"| {m.observed} | {m.tier}{' (' + '; '.join(m.notes) + ')' if m.notes else ''} |" for m in cmp.matched]
        md += [""]
        if cmp.observed_unexplained:
            md += ["Observed, unexplained:"] + [f"- [{u.severity}] {u.item} ({u.reason}; {', '.join(u.cites)})"
                                              for u in cmp.observed_unexplained] + [""]
        if cmp.expected_unobserved:
            md += ["Expected, not observed:"] + [f"- {x}" for x in cmp.expected_unobserved] + [""]
        if cmp.uncited:
            md += ["Uncited:"] + [f"- {x}" for x in cmp.uncited] + [""]
        if cmp.unsupported:
            md += ["Unsupported forward items:"] + [f"- {x}" for x in cmp.unsupported] + [""]
        if cmp.info_effects:
            md += ["Info (bookkeeping):"] + [f"- {x}" for x in cmp.info_effects] + [""]
    md += ["## Attribution", ""] + [f"- `{a['attribution']}`: {a['item']}" for a in attribution] + [""]
    return "\n".join(md)


# --------------------------------------------------------------------------- main


def process(case_path: Path, args: argparse.Namespace) -> dict[str, Any]:
    live, variant = args.live, args.backward_variant
    case = load_case(case_path)
    cid = case["id"]
    print(f"== {cid}")
    bundle = load_bundle(cid)
    if bundle is None:
        print("  no bundle; rehearse it first")
        return {"id": cid, "expected": case.get("expected_verdict"), "computed": "(no bundle)"}
    fwd, bwd = load_forward(cid), load_backward(cid, variant)
    from judge.model import ModelFormError, ModelUnavailable
    try:
        if fwd is None and live:
            fwd = run_forward_live(case)
        if bwd is None and live:
            bwd = run_backward_live(case, bundle, variant, args.backward_model, args.backward_thinking)
    except (ModelUnavailable, ModelFormError) as exc:
        # The pipeline's own rule: a pass that cannot produce a checked form leaves that side
        # missing, and the verdict below is ASK. Report it rather than stop.
        print(f"  model unavailable, continuing with recorded forms only: {str(exc)[:160]}")

    from judge import pipeline
    recorded = pipeline.recorded_leftovers(cid)[0] is not None
    sc = pipeline.source_check(bundle, cid, replay=not live or recorded, live=live)
    bundle = sc.bundle
    if sc.call:
        print(f"  {sc.call}")
    r = Resolver(bundle, case["address_book"])
    t = truth.derive(case, r)
    f = canon.from_forward(fwd, bundle.description, r) if fwd else None
    b = canon.from_backward(bwd, r) if bwd else None
    fg = grade(t, f, r) if f else None
    bg = grade(t, b, r) if b else None
    v = verdict.decide(bundle, expected=fwd, observed=bwd, address_book=case["address_book"],
                       raised=sc.raised, explained_slots=sc.explained)
    cmp = v.compare or CompareResult()
    tiers_by_observed = {m.observed: m.tier for m in cmp.matched}
    attribution = attribute(cmp, fg, bg, tiers_by_observed, case.get("expected_verdict"))

    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"{cid}.md").write_text(report_md(case, v, t, f, b, fg, bg, attribution), encoding="utf-8", newline="\n")
    (REPORTS / f"{cid}.json").write_text(json.dumps({
        "id": cid, "description": case["description"], "expected_verdict": case.get("expected_verdict"),
        "verdict": v.model_dump(mode="json"),
        "truth": t.model_dump(mode="json"), "forward": f.model_dump(mode="json") if f else None,
        "backward": b.model_dump(mode="json") if b else None,
        "forward_vs_truth": fg, "backward_vs_truth": bg, "attribution": attribution,
        "residuals": residual_detail(cmp, bundle),
        "bundle": {"safe_tx_hash": bundle.safe_tx_hash, "fork_block": bundle.fork_block,
                   "storage_diff": [s.model_dump(mode="json") for s in bundle.storage_diff]},
    }, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")

    def n(g):
        return "-" if g is None else sum(len(x) for x in g.values())
    residual = len(cmp.observed_unexplained) + len(cmp.expected_unobserved) + len(cmp.uncited) + len(cmp.unsupported)
    print(f"  {v.decision.value:6s} forward errs {n(fg)}  backward errs {n(bg)}  residuals {residual}  tiers {cmp.tiers}")
    return {"id": cid, "expected": case.get("expected_verdict"), "computed": v.decision.value,
            "forward_errors": n(fg), "backward_errors": n(bg), "residuals": residual,
            "forward_form": fwd is not None, "backward_form": bwd is not None}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--live", action="store_true", help="run a pass whose recorded output is missing")
    ap.add_argument("--include-reject", action="store_true")
    ap.add_argument("--only", help="case ids, comma-separated, run in that order")
    ap.add_argument("--backward-variant", help="read/record <id>.backward.NAME.json; reports to reports/compare-NAME/")
    ap.add_argument("--backward-model", help="model for a live backward pass (default: backward.DEFAULT_MODEL)")
    ap.add_argument("--backward-thinking", choices=["low", "medium", "high"])
    args = ap.parse_args(argv)
    global REPORTS
    if args.backward_variant:
        REPORTS = REPO / "reports" / f"compare-{args.backward_variant}"

    folders = ["match", "ask", "demo"] + (["reject"] if args.include_reject else [])
    paths = sorted(p for d in folders for p in (FIXTURES / "cases" / d).glob("*.json"))
    if args.only:
        by_id = {p.stem: p for p in paths}
        paths = [by_id[i] for i in args.only.split(",") if i in by_id]
    rows = [process(p, args) for p in paths]

    print("\n| case | expected | computed | forward errors | backward errors | residuals |")
    print("| --- | --- | --- | --- | --- | --- |")
    for row in rows:
        flag = "" if row["expected"] == row["computed"] else "  <-- differs"
        print(f"| {row['id']} | {row['expected']} | {row['computed']}{flag} | {row.get('forward_errors', '-')} | "
              f"{row.get('backward_errors', '-')} | {row.get('residuals', '-')} |")
    # an --only run updates its rows in the summary instead of replacing the whole table
    summary = REPORTS / "summary.json"
    merged = {r["id"]: r for r in (json.loads(summary.read_text(encoding="utf-8")) if summary.exists() else [])}
    merged.update({r["id"]: r for r in rows})
    summary.write_text(json.dumps(list(merged.values()), indent=2), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
