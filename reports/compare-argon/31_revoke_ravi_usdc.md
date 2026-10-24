# 31_revoke_ravi_usdc

**Description:** Revoke Ravi's USDC allowance

**Expected verdict:** ASK  **Computed:** ASK

The trace shows 2 effects the description does not mention:
- allowance USDC Safe -> Ravi: unlimited (evidence c4, c5, s0, e1)
- Safe grants Ravi an unlimited USDC allowance. (evidence c4, c5, s0, e1)

**Question for the signers:** The transaction also does the following, which the description does not mention. Is that intended? allowance USDC Safe -> Ravi: unlimited; Safe grants Ravi an unlimited USDC allowance.

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements |  |  |  |
| permissions | allowance USDC Safe -> Ravi: unlimited | allowance USDC Safe -> Ravi: zero | allowance USDC Safe -> Ravi: unlimited |
| configs |  |  |  |

## Each pass against the truth

**Forward vs truth:** 1 difference
- wrong_amount: permission allowance USDC Safe -> Ravi: zero (truth allowance USDC Safe -> Ravi: unlimited)

**Backward vs truth:** agrees.

## Forward against backward

| matched | tier |
| --- | --- |

Observed, unexplained:
- [notable] allowance USDC Safe -> Ravi: unlimited (no expected allowance matches (asset, spender, amount); c4, c5, s0, e1)
- [notable] Safe grants Ravi an unlimited USDC allowance. (no matched item shares its evidence; c4, c5, s0, e1)

Expected, not observed:
- permission allowance USDC Safe -> Ravi: zero

Info (bookkeeping):
- Safe increments its transaction nonce from 1 to 2 and logs successful execution.

## Attribution

- `real_finding`: observed, unexplained [notable]: allowance USDC Safe -> Ravi: unlimited
- `real_finding (same evidence as the item above)`: observed, unexplained [notable]: Safe grants Ravi an unlimited USDC allowance.
- `real_finding`: expected, not observed: permission allowance USDC Safe -> Ravi: zero
- `real_finding`: forward vs truth (wrong_amount): permission allowance USDC Safe -> Ravi: zero (truth allowance USDC Safe -> Ravi: unlimited)
- `bookkeeping`: info: Safe increments its transaction nonce from 1 to 2 and logs successful execution.
