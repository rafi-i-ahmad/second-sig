# 33_pay_ravi_but_approve

**Description:** Pay Ravi 2,500 USDC for October

**Expected verdict:** ASK  **Computed:** ASK

The trace shows 2 effects the description does not mention:
- allowance USDC Safe -> Ravi: 2500000000 (evidence c4, c5, s0, e1)
- The Safe grants Ravi an allowance of 2,500 USDC. (evidence c4, c5, s0, e1)

**Question for the signers:** The transaction also does the following, which the description does not mention. Is that intended? allowance USDC Safe -> Ravi: 2500000000; The Safe grants Ravi an allowance of 2,500 USDC.

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements |  | 2,500 USDC Safe -> Ravi |  |
| permissions | allowance USDC Safe -> Ravi: 2500000000 |  | allowance USDC Safe -> Ravi: 2500000000 |
| configs |  |  |  |

## Each pass against the truth

**Forward vs truth:** 2 differences
- missing: permission allowance USDC Safe -> Ravi: 2500000000
- extra: movement 2,500 USDC Safe -> Ravi

**Backward vs truth:** agrees.

## Forward against backward

| matched | tier |
| --- | --- |

Observed, unexplained:
- [notable] allowance USDC Safe -> Ravi: 2500000000 (no expected allowance matches (asset, spender, amount); c4, c5, s0, e1)
- [notable] The Safe grants Ravi an allowance of 2,500 USDC. (no matched item shares its evidence; c4, c5, s0, e1)

Expected, not observed:
- movement 2,500 USDC Safe -> Ravi

Info (bookkeeping):
- The Safe increments its transaction nonce from 1 to 2.

## Attribution

- `real_finding`: observed, unexplained [notable]: allowance USDC Safe -> Ravi: 2500000000
- `real_finding (same evidence as the item above)`: observed, unexplained [notable]: The Safe grants Ravi an allowance of 2,500 USDC.
- `real_finding`: expected, not observed: movement 2,500 USDC Safe -> Ravi
- `real_finding`: forward vs truth (missing): permission allowance USDC Safe -> Ravi: 2500000000
- `real_finding`: forward vs truth (extra): movement 2,500 USDC Safe -> Ravi
- `bookkeeping`: info: The Safe increments its transaction nonce from 1 to 2.
