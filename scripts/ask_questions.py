"""Run the escalation step on cases the table did not approve, by replay of the saved reports.

For each case id, load reports/compare/<id>.json (verdict with its CompareResult, the canonical
forward and backward lists), ask jobs/escalate.py for the signer's question, save it as
fixtures/outputs/<id>.question.json and write the table in reports/compare/QUESTIONS.md for the
cases named. A recorded question whose verdict still holds is replayed, not asked again; --rerun
asks anyway.

    uv run python scripts/ask_questions.py [--rerun] demo_auditor 09_routine_transfer_vague 31_revoke_ravi_usdc ...
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from judge.jobs import escalate
from judge.schemas import CanonEffects, HumanQuestion, Verdict

REPO = Path(__file__).resolve().parent.parent
REPORTS = REPO / "reports" / "compare"
OUTPUTS = REPO / "fixtures" / "outputs"


def main(argv: list[str]) -> int:
    rerun = "--rerun" in argv
    ids = [a for a in argv if not a.startswith("--")]
    if not ids:
        print(__doc__)
        return 2
    rows = []
    for cid in ids:
        rep = json.loads((REPORTS / f"{cid}.json").read_text(encoding="utf-8"))
        (case_path,) = (REPO / "fixtures" / "cases").glob(f"*/{cid}.json")
        case = json.loads(case_path.read_text(encoding="utf-8"))
        verdict = Verdict.model_validate(rep["verdict"])
        expected = CanonEffects.model_validate(rep["forward"]) if rep.get("forward") else None
        observed = CanonEffects.model_validate(rep["backward"]) if rep.get("backward") else None
        saved = OUTPUTS / f"{cid}.question.json"
        old = json.loads(saved.read_text(encoding="utf-8")) if saved.exists() else None
        if old and old.get("verdict") == verdict.decision.value and not rerun:
            form, ms = HumanQuestion.model_validate(old["question"]), 0  # recorded, and the verdict still holds
        else:
            form, iid, ms = escalate.run(rep["description"], case["address_book"], case["safe"], verdict, expected,
                                         observed)
            saved.write_text(json.dumps({
                "model": escalate.DEFAULT_MODEL, "thinking": escalate.DEFAULT_THINKING, "interaction_id": iid,
                "latency_ms": ms, "verdict": verdict.decision.value, "question": form.model_dump(mode="json"),
            }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        text = escalate.compose(form, verdict.decision.value)
        print(f"== {cid}  ({verdict.decision.value}, {ms} ms)")
        print(f"   gap: {form.gap_kind}   honest proposer: {form.would_an_honest_proposer_write_this}   "
              f"confidence: {form.confidence}")
        print(f"   {'STATEMENT' if verdict.decision.value == 'REJECT' else 'TO THE SIGNERS'}: {text}")
        for c in form.what_to_check:
            print(f"   - {c}")
        rows.append((cid, rep["description"], verdict.decision.value, form, text))

    md = ["# What the escalation step tells the signers", "",
          f"Model: `{escalate.DEFAULT_MODEL}`, thinking {escalate.DEFAULT_THINKING}. Inputs: the saved comparison for each "
          "case (reports/compare/<id>.json). The decision was made by code before the model was asked; the "
          "model's reading of the gap is advisory. For ASK the text is the kind of gap, then the question. "
          "For REJECT it is a statement of why; no question is asked. The model's view of whether an honest "
          "proposer would write these words is kept as a note in its own column and never changes the text.", "",
          "| Case | Description | Verdict (code) | Gap kind (model) | Honest proposer? | What the signers see |",
          "| --- | --- | --- | --- | --- | --- |"]
    for cid, desc, dec, f, text in rows:
        md.append(f"| {cid} | {desc} | {dec} | {f.gap_kind} | {f.would_an_honest_proposer_write_this} | {text} |")
    md += [""]
    for cid, _, dec, f, text in rows:
        md += [f"## {cid} ({dec})", "", text, "", "What to check:"] + [f"- {c}" for c in f.what_to_check]
        md += ["", f"<details><summary>reasoning</summary>\n\n{f.reasoning}\n\n</details>", ""]
    (REPORTS / "QUESTIONS.md").write_text("\n".join(md), encoding="utf-8", newline="\n")
    print(f"\nwritten to {REPORTS / 'QUESTIONS.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
