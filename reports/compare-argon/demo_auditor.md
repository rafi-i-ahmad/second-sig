# demo_auditor

**Description:** Pay our auditor 100 USDC

**Expected verdict:** ASK  **Computed:** ASK

The trace shows 2 effects the description does not mention:
- allowance USDC Safe -> auditor: unlimited (evidence c7, c8, s2, e2)
- The Safe grants an unlimited USDC allowance to auditor. (evidence c7, c8, s2, e2)

**Question for the signers:** The transaction also does the following, which the description does not mention. Is that intended? allowance USDC Safe -> auditor: unlimited; The Safe grants an unlimited USDC allowance to auditor.

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
- [notable] The Safe grants an unlimited USDC allowance to auditor. (no matched item shares its evidence; c7, c8, s2, e2)

Info (bookkeeping):
- The Safe increments its nonce from 1 to 2 and logs successful execution of the MultiSendCallOnly v1.4.1 batch.

## Attribution

- `real_finding`: observed, unexplained [notable]: allowance USDC Safe -> auditor: unlimited
- `real_finding (same evidence as the item above)`: observed, unexplained [notable]: The Safe grants an unlimited USDC allowance to auditor.
- `real_finding`: forward vs truth (missing): permission allowance USDC Safe -> auditor: unlimited
- `bookkeeping`: info: The Safe increments its nonce from 1 to 2 and logs successful execution of the MultiSendCallOnly v1.4.1 batch.
