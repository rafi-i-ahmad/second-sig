# demo_auditor

**Description:** Pay our auditor 100 USDC

**Expected verdict:** ASK  **Computed:** ASK

The trace shows 2 effects the description does not mention:
- allowance USDC Safe -> auditor: unlimited (evidence c7, c8, s2, e2)
- Safe grants auditor an unlimited USDC allowance. (evidence c7, c8, s2, e2)

**Question for the signers:** The transaction also does the following, which the description does not mention. Is that intended? allowance USDC Safe -> auditor: unlimited; Safe grants auditor an unlimited USDC allowance.

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements | 100 USDC Safe -> auditor | 100 USDC Safe -> auditor | 100 USDC Safe -> auditor |
| permissions | allowance USDC Safe -> auditor: unlimited |  | allowance USDC Safe -> auditor: unlimited |
| configs |  |  |  |

## Each pass against the truth

**Forward vs truth:** 1 difference
- missing: permission allowance USDC Safe -> auditor: unlimited

**Backward vs truth:** agrees.

## Forward against backward

| matched | tier |
| --- | --- |
| 100 USDC Safe -> auditor | exact |

Observed, unexplained:
- [notable] allowance USDC Safe -> auditor: unlimited (no expected allowance matches (asset, spender, amount); c7, c8, s2, e2)
- [notable] Safe grants auditor an unlimited USDC allowance. (no matched item shares its evidence; c7, c8, s2, e2)

Info (bookkeeping):
- The Safe's transaction nonce is incremented from 1 to 2.

## Attribution

- `real_finding`: observed, unexplained [notable]: allowance USDC Safe -> auditor: unlimited
- `real_finding (same evidence as the item above)`: observed, unexplained [notable]: Safe grants auditor an unlimited USDC allowance.
- `real_finding`: forward vs truth (missing): permission allowance USDC Safe -> auditor: unlimited
- `bookkeeping`: info: The Safe's transaction nonce is incremented from 1 to 2.
