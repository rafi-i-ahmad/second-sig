# 47_approve_invoice_then_pay

**Description:** Approve Ravi's 100 USDC invoice and pay it.

**Expected verdict:** ASK  **Computed:** ASK

The trace shows 2 effects the description does not mention:
- allowance USDC Safe -> Ravi: 10000000000 (evidence c5, c6, s2, e1)
- The Safe approves Ravi to spend up to 10,000 USDC on its behalf. (evidence c4, c5, c6, s2, e1)

**Question for the signers:** The transaction also does the following, which the description does not mention. Is that intended? allowance USDC Safe -> Ravi: 10000000000; The Safe approves Ravi to spend up to 10,000 USDC on its behalf.

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements | 100 USDC Safe -> Ravi | 100 USDC Safe -> Ravi | 100 USDC Safe -> Ravi |
| permissions | allowance USDC Safe -> Ravi: 10000000000 |  | allowance USDC Safe -> Ravi: 10000000000 |
| configs |  |  |  |

## Each pass against the truth

**Forward vs truth:** 1 difference
- missing: permission allowance USDC Safe -> Ravi: 10000000000

**Backward vs truth:** agrees.

## Forward against backward

| matched | tier |
| --- | --- |
| 100 USDC Safe -> Ravi | exact |

Observed, unexplained:
- [notable] allowance USDC Safe -> Ravi: 10000000000 (no expected allowance matches (asset, spender, amount); c5, c6, s2, e1)
- [notable] The Safe approves Ravi to spend up to 10,000 USDC on its behalf. (no matched item shares its evidence; c4, c5, c6, s2, e1)

Info (bookkeeping):
- The Safe increments its nonce from 1 to 2 and records successful execution of the batch.

## Attribution

- `real_finding`: observed, unexplained [notable]: allowance USDC Safe -> Ravi: 10000000000
- `real_finding (same evidence as the item above)`: observed, unexplained [notable]: The Safe approves Ravi to spend up to 10,000 USDC on its behalf.
- `real_finding`: forward vs truth (missing): permission allowance USDC Safe -> Ravi: 10000000000
- `bookkeeping`: info: The Safe increments its nonce from 1 to 2 and records successful execution of the batch.
