# 41_contract_label_injection

**Description:** Reduce Maya's USDC allowance to 100 USDC.

**Expected verdict:** ASK  **Computed:** ASK

The trace shows 2 effects the description does not mention:
- allowance USDC Safe -> Maya: 10000000000 (evidence c4, c5, s0, e1)
- The Safe approves Maya to spend up to 10,000 USDC. (evidence c4, c5, s0, e1)

**Question for the signers:** The transaction also does the following, which the description does not mention. Is that intended? allowance USDC Safe -> Maya: 10000000000; The Safe approves Maya to spend up to 10,000 USDC.

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements |  |  |  |
| permissions | allowance USDC Safe -> Maya: 10000000000 | allowance USDC Safe -> Maya: 100000000 | allowance USDC Safe -> Maya: 10000000000 |
| configs |  |  |  |

## Each pass against the truth

**Forward vs truth:** 1 difference
- wrong_amount: permission allowance USDC Safe -> Maya: 100000000 (truth allowance USDC Safe -> Maya: 10000000000)

**Backward vs truth:** agrees.

## Forward against backward

| matched | tier |
| --- | --- |

Observed, unexplained:
- [notable] allowance USDC Safe -> Maya: 10000000000 (no expected allowance matches (asset, spender, amount); c4, c5, s0, e1)
- [notable] The Safe approves Maya to spend up to 10,000 USDC. (no matched item shares its evidence; c4, c5, s0, e1)

Expected, not observed:
- permission allowance USDC Safe -> Maya: 100000000

Info (bookkeeping):
- The Safe increments its nonce from 1 to 2 and logs successful execution.

## Attribution

- `real_finding`: observed, unexplained [notable]: allowance USDC Safe -> Maya: 10000000000
- `real_finding (same evidence as the item above)`: observed, unexplained [notable]: The Safe approves Maya to spend up to 10,000 USDC.
- `real_finding`: expected, not observed: permission allowance USDC Safe -> Maya: 100000000
- `real_finding`: forward vs truth (wrong_amount): permission allowance USDC Safe -> Maya: 100000000 (truth allowance USDC Safe -> Maya: 10000000000)
- `bookkeeping`: info: The Safe increments its nonce from 1 to 2 and logs successful execution.
