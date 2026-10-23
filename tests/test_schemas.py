from judge.schemas import Decision, Stamp, Verdict


def test_stamp_roundtrip() -> None:
    s = Stamp(safeTxHash="0x" + "00" * 32, forkBlock=21895238, judgeVersion="second-sig-0.1.0")
    assert Stamp.model_validate(s.model_dump()) == s


def test_verdict_decision_enum() -> None:
    assert Verdict(decision=Decision.REJECT).decision == "REJECT"
