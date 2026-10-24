"""Live forward-pass test over fixtures/cases/{match,ask,reject}/.

For every case, run judge/jobs/forward.py on the description and address book alone,
then compare the form with the case's ``intent``: same multiset of movements, same
permission and config changes, ``nothing_else`` agreeing, and a question where the
intent expects one. The reject cases belong here too: their words describe an honest
transaction, so the forward pass should read them like one. The demos in cases/demo/ are
never read (CLAUDE.md invariant 8). Each model output is saved as
``fixtures/outputs/<id>.forward.json``.

Run:  uv run pytest tests/test_forward_cases.py --live -s
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from judge.jobs import forward
from judge.schemas import ExpectedEffects

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
CASES_DIR = FIXTURES / "cases"
OUTPUTS_DIR = FIXTURES / "outputs"
FORWARD_FOLDERS = ("match", "ask", "reject")  # never "demo"
CASE_FILES = sorted(p for folder in FORWARD_FOLDERS for p in (CASES_DIR / folder).glob("*.json"))
MODEL = "gemini-3.8-flash"
THINKING = "low"


# --------------------------------------------------------------------------- normalise


def _name(s: str | None) -> str:
    """'The Ops Wallet' and 'ops wallet' are the same party."""
    s = (s or "").strip().lower()
    s = re.sub(r"^(the|our)\s+", "", s)
    return re.sub(r"\s+", " ", s)


def _amount(s: str | None) -> str | None:
    """'2,500 USDC', '2500 USDC' and '2500.00 usdc' are the same amount."""
    if s is None:
        return None
    s = s.lower().replace(",", "").replace(" ", "")
    s = re.sub(r"(\d+)\.0+(?=\D|$)", r"\1", s)
    return s


def _movements(items: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    out = []
    for it in items:
        out.append((it["asset"].upper(), _amount(it.get("amount_human")),
                    _name(it["from_name"]), _name(it["to_name"])))
    return sorted(out, key=str)


def _permissions(items: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    return sorted(
        (it["asset"].upper(), _name(it["owner_name"]), _name(it["spender_name"]), _amount(it["amount_human"]))
        for it in items
    )


def _config(items: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    return sorted(
        (it["kind"], _name(it.get("owner_name")), it.get("threshold_after"))
        for it in items
    )


def _match_with_wildcards(got: list[tuple[Any, ...]], want: list[tuple[Any, ...]]) -> bool:
    """Equal as multisets, except a None amount in ``want`` matches any amount."""
    if len(got) != len(want):
        return False
    pool = list(got)
    for w in want:
        for i, g in enumerate(pool):
            if all(wf is None or wf == gf for wf, gf in zip(w, g)):
                pool.pop(i)
                break
        else:
            return False
    return True


def compare(form: ExpectedEffects, intent: dict[str, Any]) -> list[str]:
    """Return the list of mismatches; empty means the case passes."""
    got = form.model_dump(mode="json")
    problems: list[str] = []
    if not _match_with_wildcards(_movements(got["movements"]), _movements(intent["movements"])):
        problems.append(f"movements: got {_movements(got['movements'])}, want {_movements(intent['movements'])}")
    if _permissions(got["permission_changes"]) != _permissions(intent["permission_changes"]):
        problems.append(
            f"permissions: got {_permissions(got['permission_changes'])}, "
            f"want {_permissions(intent['permission_changes'])}"
        )
    if _config(got["safe_config_changes"]) != _config(intent["safe_config_changes"]):
        problems.append(
            f"config: got {_config(got['safe_config_changes'])}, want {_config(intent['safe_config_changes'])}"
        )
    if got["nothing_else"] != intent["nothing_else"]:
        problems.append(f"nothing_else: got {got['nothing_else']}, want {intent['nothing_else']}")
    if intent.get("expect_question") and not got["questions_for_human"]:
        problems.append("expected at least one question_for_human, got none")
    return problems


# --------------------------------------------------------------------------- tests


def test_cases_exist_and_never_include_demos() -> None:
    assert len(CASE_FILES) == 30, sorted(p.stem for p in CASE_FILES)
    for path in CASE_FILES:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert not data["id"].startswith("demo_"), f"{path} is a demo scenario; those stay in cases/demo/"
        assert data["expected_verdict"].lower() == path.parent.name, f"{path} is in the wrong folder"
        assert set(data["intent"]) >= {"movements", "permission_changes", "safe_config_changes", "nothing_else"}
    assert sorted((CASES_DIR / "demo").glob("*.json")), "cases/demo/ should hold the three demo scenarios"


def test_compare_helper_wildcard_amount() -> None:
    form = ExpectedEffects(
        reasoning="",
        movements=[{"asset": "eth", "amount_human": "1.9 ETH", "from_name": "The Uniswap router",
                    "to_name": "Safe", "cites": "x"}],
        nothing_else=True,
        confidence="high",
    )
    intent = {"movements": [{"asset": "ETH", "amount_human": None, "from_name": "Uniswap router", "to_name": "Safe"}],
              "permission_changes": [], "safe_config_changes": [], "nothing_else": True}
    assert compare(form, intent) == []


def test_address_book_is_spotlit_and_a_label_that_is_not_a_name_is_dropped() -> None:
    """Case 40: the address book can be written by the proposer. Its names reach the model only
    inside spotlight tags, and a label that is not a plain name does not reach it at all."""
    (path,) = CASES_DIR.glob("*/40_address_book_name_injection.json")
    case = json.loads(path.read_text(encoding="utf-8"))
    injected = next(k for k in case["address_book"] if len(k) > 48)
    user = forward.build_user_turn(case["description"], case["address_book"], case["safe"])
    assert injected not in user and "0x97f8fD4720c6b29a0664cf3A8b3550bd1171c277" not in user
    tags = re.findall(r"<untrusted_([0-9a-f]{12})>", user)
    assert len(set(tags)) == 2, "address book and description, each in its own tags"
    book_block = user.split(f"<untrusted_{tags[0]}>")[2].split(f"</untrusted_{tags[0]}>")[0]
    assert '"Dana"' in book_block and '"Dana"' not in user.split("<untrusted_")[0]


def test_an_owners_answer_gets_its_own_tags_and_the_owner_stays_outside() -> None:
    """An answer to an ASK is untrusted text in its own tags; the owner address, which our tooling
    sets, is outside them. A turn with no answers says nothing about answers."""
    book, safe = {"auditor": "0x46F43A4Cb3c2cD27c36f07cfd691E8a22Dd60A4C"}, {"version": "1.4.1"}
    owner = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"
    plain = forward.build_user_turn("Pay our auditor 100 USDC", book, safe)
    assert "Answer 1" not in plain and "owners answered" not in plain
    user = forward.build_user_turn("Pay our auditor 100 USDC", book, safe,
                                   [(owner, "Yes, grant the auditor an unlimited USDC allowance.")])
    tags = re.findall(r"<untrusted_([0-9a-f]{12})>", user)
    assert len(set(tags)) == 3, "address book, description and the answer, each in its own tags"
    answer_block = user.split(f"<untrusted_{tags[-1]}>")[2].split(f"</untrusted_{tags[-1]}>")[0]
    assert "unlimited USDC allowance" in answer_block and owner not in answer_block
    assert f"from Safe owner {owner}." in user.split(f"<untrusted_{tags[-1]}>")[0]


@pytest.mark.live
@pytest.mark.parametrize("case_path", CASE_FILES, ids=[p.stem for p in CASE_FILES])
def test_forward_case(case_path: Path) -> None:
    case = json.loads(case_path.read_text(encoding="utf-8"))
    form, interaction_id, latency_ms = forward.run(
        case["description"], case["address_book"], case["safe"], model=MODEL, thinking=THINKING
    )

    OUTPUTS_DIR.mkdir(exist_ok=True)
    out_path = OUTPUTS_DIR / f"{case_path.stem}.forward.json"
    out_path.write_text(
        json.dumps(
            {"model": MODEL, "thinking": THINKING, "interaction_id": interaction_id,
             "latency_ms": latency_ms, "expected_effects": form.model_dump(mode="json")},
            indent=2,
        ) + "\n",
        encoding="utf-8", newline="\n",
    )

    problems = compare(form, case["intent"])
    status = "PASS" if not problems else "FAIL"
    print(f"\n{status} {case['id']:28s} {latency_ms:6d} ms  {interaction_id}")
    for p in problems:
        print(f"      {p}")
    assert not problems, "\n".join(problems)
