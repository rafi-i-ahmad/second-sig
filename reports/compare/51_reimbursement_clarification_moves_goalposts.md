# 51_reimbursement_clarification_moves_goalposts

**Description:** Pay Dana's 2,500 USDC October invoice and include Ravi's reimbursement.

**Expected verdict:** ASK  **Computed:** ASK

The trace shows 1 effect the description does not mention:
- 200 USDC Safe -> Ravi (evidence c7, c8, s0, s1, b0, b2, e2)

**Question for the signers:** The transaction also does the following, which the description does not mention. Is that intended? 200 USDC Safe -> Ravi

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements | 2500 USDC Safe -> Dana | 2,500 USDC Safe -> Dana | 2,500 USDC Safe -> Dana |
|  | 200 USDC Safe -> Ravi |  | 200 USDC Safe -> Ravi |
| permissions |  |  |  |
| configs |  |  |  |

## Each pass against the truth

**Forward vs truth:** 1 difference
- missing: movement 200 USDC Safe -> Ravi

**Backward vs truth:** agrees.

## Forward against backward

| matched | tier |
| --- | --- |
| 2,500 USDC Safe -> Dana | exact |

Observed, unexplained:
- [notable] 200 USDC Safe -> Ravi (no expected movement matches (asset, route, amount); c7, c8, s0, s1, b0, b2, e2)

Info (bookkeeping):
- The Safe increments its transaction nonce from 1 to 2.

## Attribution

- `real_finding`: observed, unexplained [notable]: 200 USDC Safe -> Ravi
- `real_finding`: forward vs truth (missing): movement 200 USDC Safe -> Ravi
- `bookkeeping`: info: The Safe increments its transaction nonce from 1 to 2.
