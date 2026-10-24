# demo_aave

**Description:** Deposit 10,000 USDC into Aave v3

**Expected verdict:** MATCH  **Computed:** ASK

The trace shows 1 effect the description does not mention:
- Aave v3 Pool enables USDC as collateral for Safe. (evidence c9, s0, e3)

**Question for the signers:** The transaction also does the following, which the description does not mention. Is that intended? Aave v3 Pool enables USDC as collateral for Safe.

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements | 10000 aUSDC Aave v3 Pool -> Safe | 10,000 USDC Safe -> Aave v3 Pool | 10,000 USDC Safe -> aUSDC |
|  | 10000 USDC Safe -> Aave v3 Pool | 10,000 aUSDC Aave v3 Pool -> Safe | 10,000 aUSDC zero address -> Safe |
| permissions | allowance USDC Safe -> Aave v3 Pool: 10000000000 | allowance USDC Safe -> Aave v3 Pool: 10000000000 | allowance USDC Safe -> Aave v3 Pool: 10000000000 |
| configs |  |  |  |

Truth notes: protocol call Aave v3 Pool.supply(address,uint256,address,uint16): asset flows taken from the fork's balance changes

## Each pass against the truth

**Forward vs truth:** agrees.

**Backward vs truth:** agrees.

## Forward against backward

| matched | tier |
| --- | --- |
| 10,000 USDC Safe -> aUSDC | counterparty_via_callee |
| 10,000 aUSDC zero address -> Safe | counterparty_via_callee |
| allowance USDC Safe -> Aave v3 Pool: 10000000000 | exact (expected item was implied by the words, not stated) |

Observed, unexplained:
- [notable] Aave v3 Pool enables USDC as collateral for Safe. (no matched item shares its evidence; c9, s0, e3)

Info (bookkeeping):
- Aave v3 Pool updates reserve interest indices, rates, and accounting for USDC, and aUSDC calls 0x8164Cc65827dcFe994AB23944CBC90e0aa80bFcb to update user action accounting.
- Safe verifies signatures, increments its nonce from 1 to 2, batches the calls via MultiSendCallOnly v1.4.1, and records successful execution.

## Attribution

- `needs_investigation`: observed, unexplained [notable]: Aave v3 Pool enables USDC as collateral for Safe.
- `tolerance_rule`: matched by counterparty_via_callee: 10,000 USDC Safe -> aUSDC
- `tolerance_rule`: matched by counterparty_via_callee: 10,000 aUSDC zero address -> Safe
- `bookkeeping`: info: Aave v3 Pool updates reserve interest indices, rates, and accounting for USDC, and aUSDC calls 0x8164Cc65827dcFe994AB23944CBC90e0aa80bFcb to update user action accounting.
- `bookkeeping`: info: Safe verifies signatures, increments its nonce from 1 to 2, batches the calls via MultiSendCallOnly v1.4.1, and records successful execution.
