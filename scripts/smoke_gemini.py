"""Friday G0 check: one call to each model through judge/model.py.

Usage:
    uv run python scripts/smoke_gemini.py

Runs (a) gemini-3.8-flash with a flat three-field schema and (b) gemini-4-argon with
thinking_level=high on a nested schema where the right verdict is REJECT. Prints the
parsed output, interaction ids and latency. Exits non-zero if either call fails.
Needs GEMINI_API_KEY in the environment or .env. Appends to logs/calls.jsonl as usual.
"""

from __future__ import annotations

import sys
import time
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from judge import model as m

FLASH = "gemini-3.8-flash"
ARGON = "gemini-4-argon"


class Colour(str, Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"


class ThreeField(BaseModel):
    colour: Colour
    count: int
    tags: list[str]


class Finding(BaseModel):
    claim: str
    severity: Literal["low", "high"]


class Judgement(BaseModel):
    reasoning: str = Field(description="Think step by step here first.")
    verdict: Literal["MATCH", "ASK", "REJECT"]
    findings: list[Finding] = Field(default_factory=list)


SYSTEM = (
    "You compare a transaction description with the effects observed on a fork. "
    "Fill the reasoning field first, then the verdict. "
    "MATCH if the effects are exactly what the description says, "
    "ASK if you cannot tell, REJECT if the effects contradict the description."
)
USER = (
    "Description: 'Send 10 USDC from the treasury to our payroll account 0xPAYROLL.'\n"
    "Observed effects on the fork: the Safe's implementation (masterCopy) slot changed "
    "to an unverified contract 0xBAD; no USDC moved; 0xPAYROLL was not touched."
)


def run_a() -> bool:
    print(f"(a) {FLASH}, thinking=low, flat schema")
    t0 = time.perf_counter()
    try:
        parsed, iid = m.complete(
            FLASH,
            "Answer the question in the required JSON shape.",
            "Pick your favourite of red, green or blue, give a count of 7, and list three fruit.",
            ThreeField,
            "low",
        )
    except (m.ModelUnavailable, m.ModelFormError) as exc:
        print(f"    FAIL {type(exc).__name__}: {exc}")
        return False
    print(f"    output      {parsed.model_dump()}")
    print(f"    interaction {iid}")
    print(f"    latency_ms  {int((time.perf_counter() - t0) * 1000)}")
    return True


def run_b() -> bool:
    print(f"(b) {ARGON}, thinking=high, nested schema, expected REJECT")
    t0 = time.perf_counter()
    try:
        parsed, iid = m.complete(ARGON, SYSTEM, USER, Judgement, "high")
    except (m.ModelUnavailable, m.ModelFormError) as exc:
        print(f"    FAIL {type(exc).__name__}: {exc}")
        return False
    print(f"    verdict     {parsed.verdict}")
    print(f"    reasoning   {parsed.reasoning[:300]}")
    print(f"    findings    {[f.model_dump() for f in parsed.findings]}")
    print(f"    interaction {iid}")
    print(f"    latency_ms  {int((time.perf_counter() - t0) * 1000)}")
    if parsed.verdict != "REJECT":
        print("    WARN verdict was not REJECT")
    return True


def main() -> int:
    ok_a = run_a()
    ok_b = run_b()
    print("\nG0:", "PASS" if ok_a and ok_b else "FAIL")
    return 0 if ok_a and ok_b else 1


if __name__ == "__main__":
    sys.exit(main())
