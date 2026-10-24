"""Run the escalation step on cases the table did not approve, by replay of the saved reports.

For each case id, load reports/compare/<id>.json (verdict with its CompareResult, the canonical
forward and backward lists), ask jobs/escalate.py for the signer's question, save it as
fixtures/outputs/<id>.question.json and append a table to reports/compare/QUESTIONS.md.

    uv run python scripts/ask_questions.py demo_auditor 09_routine_transfer_vague 31_revoke_ravi_usdc ...
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from judge.jobs import escalate
from judge.schemas import CanonEffects, Verdict

REPO = Path(__file__).resolve().parent.parent
REPORTS = REPO / "reports" / "compare"
OUTPUTS = REPO / "fixtures" / "outputs"


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    rows = []
    for cid in argv:
        rep = json.loads((REPORTS / f"{cid}.json").read_text(encoding="utf-8"))
        (case_path,) = (REPO / "fixtures" / "cases").glob(f"*/{cid}.json")
        case = json.loads(case_path.read_text(encoding="utf-8"))
        verdict = Verdict.model_validate(rep["verdict"])
        expected = CanonEffects.model_validate(rep["forward"]) if rep.get("forward") else None
        observed = CanonEffects.model_validate(rep["backward"]) if rep.get("backward") else None
        form, iid, ms = escalate.run(rep["description"], case["address_book"], case["safe"], verdict, expected, observed)
        (OUTPUTS / f"{cid}.question.json").write_text(json.dumps({
            "model": escalate.DEFAULT_MODEL, "thinking": escalate.DEFAULT_THINKING, "interaction_id": iid,
            "latency_ms": ms, "verdict": verdict.decision.value, "question": form.model_dump(mode="json"),
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        print(f"== {cid}  ({verdict.decision.value}, {ms} ms)")
        print(f"   gap: {form.gap_kind}   honest proposer: {form.would_an_honest_proposer_write_this}   "
              f"confidence: {form.confidence}")
        print(f"   Q: {form.question}")
        for c in form.what_to_check:
            print(f"   - {c}")
        rows.append((cid, rep["description"], verdict.decision.value, form))

    md = ["# What the escalation step asks the signers", "",
          f"Model: `{escalate.DEFAULT_MODEL}`, thinking {escalate.DEFAULT_THINKING}. Inputs: the saved comparison for each "
          "case (reports/compare/<id>.json). The decision was made by code before the model was asked; the "
          "model's reading of the gap is advisory.", "",
          "| Case | Description | Verdict (code) | Gap kind (model) | Honest proposer? | Question |",
          "| --- | --- | --- | --- | --- | --- |"]
    for cid, desc, dec, f in rows:
        md.append(f"| {cid} | {desc} | {dec} | {f.gap_kind} | {f.would_an_honest_proposer_write_this} | {f.question} |")
    md += [""]
    for cid, _, _, f in rows:
        md += [f"## {cid}", "", f"**Question:** {f.question}", "", "What to check:"] + [f"- {c}" for c in f.what_to_check]
        md += ["", f"<details><summary>reasoning</summary>\n\n{f.reasoning}\n\n</details>", ""]
    (REPORTS / "QUESTIONS.md").write_text("\n".join(md), encoding="utf-8", newline="\n")
    print(f"\nwritten to {REPORTS / 'QUESTIONS.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
