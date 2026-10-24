"""web/display.py: what the demo pages see after the 24 October verification-loop changes (interface.md).

All offline, by replay: no model, no fork.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from judge import model, pipeline
from web.display import book_names, show_calls, show_verdict

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def case(cid: str) -> dict:
    (p,) = (FIXTURES / "cases").glob(f"*/{cid}.json")
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def isolated_records(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "PROPOSALS", tmp_path / "proposals")


def shown(cid: str) -> dict:
    res = pipeline.judge(pipeline.Proposal.from_case(case(cid)), pipeline.recorded_bundle(cid), replay=True)
    return show_verdict(res)


def test_ask_with_every_row_matched_says_why() -> None:
    v = shown("45_conflicting_human_and_base_units")
    assert v["decision"] == "ASK"
    assert v["rows"] and all(r["state"] == "match" for r in v["rows"])
    assert v["why"] == ["The description raises a question"]


def test_contradiction_is_an_ask_with_its_gap_kind() -> None:
    v = shown("32_pay_dana_wrong_wallet")
    assert v["decision"] == "ASK" and v["gap"] == "Contradiction"


def test_ignored_label_reaches_the_page_and_is_never_shown_as_a_name() -> None:
    c = case("40_address_book_name_injection")
    v = shown(c["id"])
    assert v["ignored_labels"]
    names = book_names(c["address_book"])
    for addr in v["ignored_labels"]:
        assert addr.lower() not in names


def test_match_by_replay_has_no_why_and_no_model_call() -> None:
    if pipeline.recorded_leftovers("demo_aave")[0] is None:
        pytest.skip("no recorded leftovers classification for demo_aave")
    v = shown("demo_aave")
    assert v["decision"] == "MATCH" and v["why"] == [] and v["gap"] is None and v["calls"] == []


def test_calls_carry_tokens_and_cost_from_the_log(tmp_path, monkeypatch) -> None:
    log = tmp_path / "calls.jsonl"
    log.write_text("\n".join(json.dumps(x) for x in [
        {"interaction_id": "iid-a", "usage": {"input": 1000, "output": 200, "thought": 50, "cached": 0}, "est_usd": 0.004},
        {"interaction_id": "iid-b", "usage": {"input": 90000, "output": 900, "thought": 0, "cached": 0}, "est_usd": 0.2},
    ]) + "\n", encoding="utf-8")
    monkeypatch.setattr(model, "LOG_PATH", log)
    out = show_calls(["forward gemini-3.8-flash 6487 ms iid-a", "leftovers gemini-4-argon 30000 ms 98038 tokens iid-b",
                      "leftovers unavailable: ModelUnavailable"])
    assert out[0] == {"stage": "forward", "model": "gemini-3.8-flash", "ms": 6487, "tokens": 1250, "usd": 0.004}
    assert out[1]["stage"] == "leftovers" and out[1]["tokens"] == 90900 and out[1]["usd"] == 0.2
    assert out[2] == {"stage": "leftovers", "text": "leftovers unavailable: ModelUnavailable"}
