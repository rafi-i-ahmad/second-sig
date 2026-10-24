"""Build the forward-pass fixtures.

Each case is a Safe proposal: the sentence a treasurer would write, the exact bytes the
Safe would execute, and the ground truth (``intent``) the forward pass is checked against.
The forward pass only ever sees ``description`` and ``address_book``; ``safe_tx``,
``calls`` and ``intent`` are for the test harness and for humans reading the file.

Run:  uv run python fixtures/build.py

Writes one JSON file per case:
  fixtures/cases/<id>.json          ten ordinary cases (the forward-pass test set)
  fixtures/bybit/case.json          demo scenario, expected REJECT
  fixtures/aave/case.json           demo scenario, expected MATCH
  fixtures/auditor/case.json        demo scenario, expected ASK
  fixtures/mismatch/<id>.json       description contradicts the bytes, expected REJECT

The demo scenarios never go in fixtures/cases/, so forward-pass tests and any few-shot
examples cannot read them (CLAUDE.md invariant 8).

Plain-language glossary, one sentence each:
  calldata     the bytes a contract receives; the first 4 bytes pick the function, the
               rest are the arguments, each padded to 32 bytes.
  selector     those first 4 bytes, the start of the keccak hash of the function signature.
  operation    0 = CALL (ask another contract to do something), 1 = DELEGATECALL (run
               another contract's code *as the Safe*, with the Safe's storage and funds).
  MultiSend    the Safe runs several calls in one transaction by delegatecalling
               MultiSendCallOnly, which unpacks a byte string of inner calls and CALLs each.
  base units   token amounts on chain have no decimal point: USDC has 6 decimals, so
               2,500 USDC is 2_500_000_000; ETH has 18, so 1 ETH is 10**18 wei.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from eth_abi import encode
from eth_utils import keccak, to_checksum_address

ROOT = Path(__file__).resolve().parent
CASES_DIR = ROOT / "cases"

# ---------------------------------------------------------------------------
# Real mainnet contracts. All exist at the fork block (21,895,238 or later).
# ---------------------------------------------------------------------------
# https://etherscan.io/address/0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48  (FiatTokenProxy)
USDC = to_checksum_address("0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48")
# https://etherscan.io/address/0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2  (Aave v3 Pool proxy)
AAVE_POOL = to_checksum_address("0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2")
# https://etherscan.io/address/0x9641d764fc13c8B624c04430C7356C1C7C8102e2  (MultiSendCallOnly 1.4.1)
MULTISEND_CALL_ONLY = to_checksum_address("0x9641d764fc13c8B624c04430C7356C1C7C8102e2")
# https://etherscan.io/address/0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D  (Uniswap V2 Router02)
UNISWAP_V2_ROUTER = to_checksum_address("0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D")
# https://etherscan.io/address/0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2  (WETH9)
WETH = to_checksum_address("0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2")
# https://etherscan.io/address/0x96221423681A6d52E184D440a8eFCEbB105C7242  (Bybit attackers' contract)
BYBIT_ATTACK_CONTRACT = to_checksum_address("0x96221423681A6d52E184D440a8eFCEbB105C7242")
# https://etherscan.io/address/0xbDd077f651EBe7f7b3cE16fe5F2b025BE2969516  (what it writes into slot 0)
BYBIT_SLOT0_TARGET = to_checksum_address("0xbDd077f651EBe7f7b3cE16fe5F2b025BE2969516")

# The proposing Safe. PROMPT.md asks for "0xSAFE..." but calldata needs 20 real hex bytes
# (S is not a hex digit), so this spells SAFE in hex. Replace it with the fork deployment.
SAFE = to_checksum_address("0x5AFE5AFE5AFE5AFE5AFE5AFE5AFE5AFE5AFE5AFE")
SAFE_PLACEHOLDER_NOTE = "placeholder; replace with the Safe deployed on the fork"

USDC_DECIMALS = 6
ETH_DECIMALS = 18
UINT256_MAX = 2**256 - 1
SWAP_DEADLINE = 1_800_000_000  # 2027-01-15 UTC, comfortably after any fork timestamp


def usdc(amount: float | int) -> int:
    """Human USDC amount to base units (6 decimals)."""
    return int(round(amount * 10**USDC_DECIMALS))


def eth(amount: float | int) -> int:
    """Human ETH amount to wei (18 decimals)."""
    return int(round(amount * 10**ETH_DECIMALS))


def person(name: str) -> str:
    """Invented but deterministic address for a person or wallet; never a real account."""
    return to_checksum_address(keccak(text=f"second-sig fixture: {name}")[-20:])


# ---------------------------------------------------------------------------
# Encoding helpers
# ---------------------------------------------------------------------------
def selector(signature: str) -> bytes:
    return keccak(text=signature)[:4]


def calldata(signature: str, types: list[str], args: list[Any]) -> bytes:
    """Function selector followed by the ABI-encoded arguments."""
    return selector(signature) + encode(types, args)


def hex_(b: bytes) -> str:
    return "0x" + b.hex()


class Call:
    """One inner call, kept with its human-readable decoding for the JSON."""

    def __init__(
        self,
        to: str,
        to_name: str,
        signature: str,
        types: list[str],
        args: list[Any],
        value: int = 0,
        operation: int = 0,
    ) -> None:
        self.to = to
        self.to_name = to_name
        self.signature = signature
        self.types = types
        self.args = args
        self.value = value
        self.operation = operation
        self.data = calldata(signature, types, args) if signature else b""

    def decoded(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "to": self.to,
            "to_name": self.to_name,
            "value_wei": str(self.value),
            "function": self.signature or "(plain ETH transfer, empty calldata)",
            "args": [str(a) if isinstance(a, int) else a for a in self.args],
            "data": hex_(self.data),
        }


def multisend_pack(calls: list[Call]) -> bytes:
    """MultiSendCallOnly's wire format: for each call, 1 byte operation, 20-byte address,
    32-byte value, 32-byte data length, then the data, all concatenated with no padding."""
    out = b""
    for c in calls:
        out += (
            bytes([c.operation])
            + bytes.fromhex(c.to[2:])
            + c.value.to_bytes(32, "big")
            + len(c.data).to_bytes(32, "big")
            + c.data
        )
    return out


def single(call: Call) -> dict[str, Any]:
    """A Safe transaction that is one plain CALL (or, for Bybit, one DELEGATECALL)."""
    return {
        "to": call.to,
        "value": str(call.value),
        "data": hex_(call.data),
        "operation": call.operation,
    }


def batch(calls: list[Call]) -> dict[str, Any]:
    """A Safe transaction that DELEGATECALLs MultiSendCallOnly.multiSend(bytes)."""
    return {
        "to": MULTISEND_CALL_ONLY,
        "value": "0",
        "data": hex_(calldata("multiSend(bytes)", ["bytes"], [multisend_pack(calls)])),
        "operation": 1,
    }


# Common call shapes
def eth_transfer(to: str, to_name: str, amount_wei: int) -> Call:
    return Call(to, to_name, "", [], [], value=amount_wei)


def usdc_transfer(to: str, to_name: str, amount: int) -> Call:
    return Call(USDC, "USDC", "transfer(address,uint256)", ["address", "uint256"], [to, amount])


def usdc_approve(spender: str, spender_name: str, amount: int) -> Call:
    return Call(USDC, "USDC", "approve(address,uint256)", ["address", "uint256"], [spender, amount])


# ---------------------------------------------------------------------------
# Intent helpers (ground truth for the forward pass)
# ---------------------------------------------------------------------------
def move(asset: str, amount_human: str | None, from_name: str, to_name: str) -> dict[str, Any]:
    return {"asset": asset, "amount_human": amount_human, "from_name": from_name, "to_name": to_name}


def approval(asset: str, spender_name: str, amount_human: str) -> dict[str, Any]:
    return {
        "kind": "erc20_approval",
        "asset": asset,
        "owner_name": "Safe",
        "spender_name": spender_name,
        "amount_human": amount_human,
    }


def intent(
    movements: list[dict[str, Any]] | None = None,
    permission_changes: list[dict[str, Any]] | None = None,
    safe_config_changes: list[dict[str, Any]] | None = None,
    nothing_else: bool = True,
    expect_question: bool = False,
    note: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "movements": movements or [],
        "permission_changes": permission_changes or [],
        "safe_config_changes": safe_config_changes or [],
        "nothing_else": nothing_else,
        "expect_question": expect_question,
    }
    if note:
        out["note"] = note
    return out


DEFAULT_SAFE_CONTEXT = {"version": "1.4.1", "owners": 3, "threshold": 2}


def case(
    id_: str,
    description: str,
    calls: list[Call],
    address_book: dict[str, str],
    intent_: dict[str, Any],
    safe_context: dict[str, Any] | None = None,
    expected_verdict: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": id_,
        "description": description,
        "safe": {"address": SAFE, "note": SAFE_PLACEHOLDER_NOTE, **(safe_context or DEFAULT_SAFE_CONTEXT)},
        "address_book": address_book,
        "safe_tx": single(calls[0]) if len(calls) == 1 else batch(calls),
        "calls": [c.decoded() for c in calls],
        "intent": intent_,
    }
    if expected_verdict:
        out["expected_verdict"] = expected_verdict
    if note:
        out["note"] = note
    return out


# ---------------------------------------------------------------------------
# People and wallets (invented)
# ---------------------------------------------------------------------------
OPS = person("ops wallet")
HOT = person("hot wallet")
WARM = person("warm wallet")
DANA = person("Dana")
PRIYA = person("Priya")
SAM = person("Sam")
ALICE = person("Alice")
BOB = person("Bob")
CHEN = person("Chen")
AUDITOR = person("auditor")
RAVI = person("Ravi")


# ---------------------------------------------------------------------------
# The ten forward-pass cases
# ---------------------------------------------------------------------------
CASES: list[dict[str, Any]] = [
    # 1. One plain CALL with value and empty calldata: the simplest thing a Safe can do.
    case(
        "01_send_eth_ops",
        "Send 5 ETH to the ops wallet",
        [eth_transfer(OPS, "ops wallet", eth(5))],
        {"ops wallet": OPS},
        intent([move("ETH", "5 ETH", "Safe", "ops wallet")]),
    ),
    # 2. One ERC-20 transfer: the Safe CALLs the USDC contract, which moves the balance.
    case(
        "02_pay_dana_usdc",
        "Pay Dana 2,500 USDC for October",
        [usdc_transfer(DANA, "Dana", usdc(2_500))],
        {"Dana": DANA, "USDC": USDC},
        intent([move("USDC", "2,500 USDC", "Safe", "Dana")]),
    ),
    # 3. Two assets in one batch: ETH with empty calldata plus a USDC transfer.
    case(
        "03_move_eth_usdc_hot",
        "Move 20 ETH and 10,000 USDC to the hot wallet",
        [eth_transfer(HOT, "hot wallet", eth(20)), usdc_transfer(HOT, "hot wallet", usdc(10_000))],
        {"hot wallet": HOT, "USDC": USDC, "MultiSendCallOnly v1.4.1": MULTISEND_CALL_ONLY},
        intent(
            [
                move("ETH", "20 ETH", "Safe", "hot wallet"),
                move("USDC", "10,000 USDC", "Safe", "hot wallet"),
            ]
        ),
    ),
    # 4. The Safe calls itself: addOwnerWithThreshold adds an owner and sets the threshold.
    #    Threshold stays at 2; the sentence does not say so, which is what the pass must notice.
    case(
        "04_add_owner_priya",
        "Add Priya as a signer",
        [
            Call(
                SAFE,
                "Safe (itself)",
                "addOwnerWithThreshold(address,uint256)",
                ["address", "uint256"],
                [PRIYA, 2],
            )
        ],
        {"Priya": PRIYA},
        intent(
            safe_config_changes=[{"kind": "add_owner", "owner_name": "Priya", "threshold_after": 2}],
            note="Threshold is unchanged at 2; a forward pass that flags the threshold as unstated is acceptable.",
        ),
    ),
    # 5. The Safe calls itself: changeThreshold. Four owners, two needed before, three after.
    case(
        "05_raise_threshold",
        "Raise the signing threshold to 3 of 4",
        [Call(SAFE, "Safe (itself)", "changeThreshold(uint256)", ["uint256"], [3])],
        {},
        intent(safe_config_changes=[{"kind": "change_threshold", "threshold_after": 3}]),
        safe_context={"version": "1.4.1", "owners": 4, "threshold": 2},
    ),
    # 6. A finite approval: no tokens move now; the router may later pull up to 1,000 USDC.
    case(
        "06_approve_uniswap_finite",
        "Approve the Uniswap router to spend 1,000 USDC for next week's swap",
        [usdc_approve(UNISWAP_V2_ROUTER, "Uniswap router", usdc(1_000))],
        {"Uniswap router": UNISWAP_V2_ROUTER, "USDC": USDC},
        intent(permission_changes=[approval("USDC", "Uniswap router", "1,000 USDC")]),
    ),
    # 7. Three USDC transfers in one batch. Amounts are in the sentence so the pass can check them.
    case(
        "07_pay_three_contractors",
        "Pay three contractors their October invoices: Alice 1,200 USDC, Bob 3,400 USDC, Chen 800 USDC",
        [
            usdc_transfer(ALICE, "Alice", usdc(1_200)),
            usdc_transfer(BOB, "Bob", usdc(3_400)),
            usdc_transfer(CHEN, "Chen", usdc(800)),
        ],
        {
            "Alice": ALICE,
            "Bob": BOB,
            "Chen": CHEN,
            "USDC": USDC,
            "MultiSendCallOnly v1.4.1": MULTISEND_CALL_ONLY,
        },
        intent(
            [
                move("USDC", "1,200 USDC", "Safe", "Alice"),
                move("USDC", "3,400 USDC", "Safe", "Bob"),
                move("USDC", "800 USDC", "Safe", "Chen"),
            ]
        ),
    ),
    # 8. A fractional ETH amount.
    case(
        "08_refund_sam",
        "Refund Sam the 0.5 ETH he overpaid",
        [eth_transfer(SAM, "Sam", eth(0.5))],
        {"Sam": SAM},
        intent([move("ETH", "0.5 ETH", "Safe", "Sam")]),
    ),
    # 9. Deliberately vague. The bytes send 1 ETH to the ops wallet, but the sentence names
    #    no asset, amount or recipient, so the right answer is a question, not a guess.
    case(
        "09_routine_transfer_vague",
        "Routine transfer",
        [eth_transfer(OPS, "ops wallet", eth(1))],
        {},
        intent(
            nothing_else=False,
            expect_question=True,
            note="The description licenses nothing specific. The forward pass must ask rather than invent a movement.",
        ),
    ),
    # 10. Approve then swap in one batch. The ETH amount received depends on the market, so
    #     the intent leaves it unspecified; the calldata sets a 1.5 ETH minimum.
    case(
        "10_swap_usdc_eth_uniswap",
        "Swap 5,000 USDC for ETH on Uniswap",
        [
            usdc_approve(UNISWAP_V2_ROUTER, "Uniswap router", usdc(5_000)),
            Call(
                UNISWAP_V2_ROUTER,
                "Uniswap router",
                "swapExactTokensForETH(uint256,uint256,address[],address,uint256)",
                ["uint256", "uint256", "address[]", "address", "uint256"],
                [usdc(5_000), eth(1.5), [USDC, WETH], SAFE, SWAP_DEADLINE],
            ),
        ],
        {
            "Uniswap router": UNISWAP_V2_ROUTER,
            "USDC": USDC,
            "WETH": WETH,
            "MultiSendCallOnly v1.4.1": MULTISEND_CALL_ONLY,
        },
        intent(
            [
                move("USDC", "5,000 USDC", "Safe", "Uniswap router"),
                move("ETH", None, "Uniswap router", "Safe"),
            ],
            permission_changes=[approval("USDC", "Uniswap router", "5,000 USDC")],
            note="amount_human None means the sentence fixes no ETH amount; the swap returns whatever the market gives above the minimum in the calldata.",
        ),
    ),
]


# ---------------------------------------------------------------------------
# The three demo scenarios. Kept out of fixtures/cases/ on purpose.
# ---------------------------------------------------------------------------
DEMOS: list[tuple[Path, dict[str, Any]]] = [
    # Bybit shape: DELEGATECALL (operation 1) to the attackers' contract. Its transfer()
    # writes storage slot 0, and because it runs as the Safe, that is the Safe's master copy.
    (
        ROOT / "bybit" / "case.json",
        case(
            "demo_bybit",
            "Transfer 500 ETH to the warm wallet",
            [
                Call(
                    BYBIT_ATTACK_CONTRACT,
                    "Bybit attackers' contract (not in the address book)",
                    "transfer(address,uint256)",
                    ["address", "uint256"],
                    [BYBIT_SLOT0_TARGET, 0],
                    operation=1,
                )
            ],
            {"warm wallet": WARM},
            intent([move("ETH", "500 ETH", "Safe", "warm wallet")]),
            expected_verdict="REJECT",
            note="The bytes do not do what the sentence says. The delegatecall trips hard-floor rules 1, 2 and 3 before any model runs. Real attack: mainnet block 21,895,238.",
        ),
    ),
    # Honest DeFi: approve the Pool, then supply. The Safe ends up holding aUSDC.
    (
        ROOT / "aave" / "case.json",
        case(
            "demo_aave",
            "Deposit 10,000 USDC into Aave v3",
            [
                usdc_approve(AAVE_POOL, "Aave v3 Pool", usdc(10_000)),
                Call(
                    AAVE_POOL,
                    "Aave v3 Pool",
                    "supply(address,uint256,address,uint16)",
                    ["address", "uint256", "address", "uint16"],
                    [USDC, usdc(10_000), SAFE, 0],
                ),
            ],
            {"Aave v3 Pool": AAVE_POOL, "USDC": USDC, "MultiSendCallOnly v1.4.1": MULTISEND_CALL_ONLY},
            intent(
                [
                    move("USDC", "10,000 USDC", "Safe", "Aave v3 Pool"),
                    move("aUSDC", "10,000 aUSDC", "Aave v3 Pool", "Safe"),
                ],
                permission_changes=[approval("USDC", "Aave v3 Pool", "10,000 USDC")],
                note="The approval is implied by a deposit and is consumed by supply().",
            ),
            expected_verdict="MATCH",
        ),
    ),
    # True but incomplete: the payment is real, but an unlimited approval rides along.
    (
        ROOT / "auditor" / "case.json",
        case(
            "demo_auditor",
            "Pay our auditor 100 USDC",
            [
                usdc_transfer(AUDITOR, "auditor", usdc(100)),
                usdc_approve(AUDITOR, "auditor", UINT256_MAX),
            ],
            {"auditor": AUDITOR, "USDC": USDC, "MultiSendCallOnly v1.4.1": MULTISEND_CALL_ONLY},
            intent(
                [move("USDC", "100 USDC", "Safe", "auditor")],
                note="The intent has no permission change: the sentence licenses none. The calldata's unlimited approve is the unexplained leftover the judge must ask about.",
            ),
            expected_verdict="ASK",
        ),
    ),
]

# ---------------------------------------------------------------------------
# Mismatch cases: the description says one thing, the bytes do another. Expected REJECT.
# Not in fixtures/cases/ (that set has no expected verdicts) and not demos. No floor rule
# catches these: the floor only knows attack shapes, so the model has to see the gap.
# ---------------------------------------------------------------------------
MISMATCH_DIR = ROOT / "mismatch"

MISMATCH: list[dict[str, Any]] = [
    # "Revoke" means approve(Ravi, 0). The bytes approve the maximum instead: the words
    # describe the opposite of what happens. Ravi is a plain address, so nothing can pull the
    # USDC automatically, but he can now take all of it whenever he likes.
    case(
        "31_revoke_ravi_usdc",
        "Revoke Ravi's USDC allowance",
        [usdc_approve(RAVI, "Ravi", UINT256_MAX)],
        {"Ravi": RAVI, "USDC": USDC},
        intent(
            permission_changes=[approval("USDC", "Ravi", "0 USDC")],
            note="The sentence licenses an allowance of zero. The calldata grants an unlimited one.",
        ),
        expected_verdict="REJECT",
    ),
]


def write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    for c in CASES:
        write(CASES_DIR / f"{c['id']}.json", c)
        print(f"wrote cases/{c['id']}.json  ({len(c['calls'])} call(s), op={c['safe_tx']['operation']})")
    for path, c in DEMOS:
        write(path, c)
        print(f"wrote {path.relative_to(ROOT).as_posix()}  expected {c['expected_verdict']}")
    for c in MISMATCH:
        write(MISMATCH_DIR / f"{c['id']}.json", c)
        print(f"wrote mismatch/{c['id']}.json  expected {c['expected_verdict']}")


if __name__ == "__main__":
    main()
