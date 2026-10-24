# 09_routine_transfer_vague

**Description:** Routine transfer

**Expected verdict:** ASK  **Computed:** ASK

The trace shows 2 effects the description does not mention:
- 1 ETH Safe -> 0xE1D9a0eADCb8082d7989D7304061c017bE296C31 (evidence c4, b0, b1)
- The Safe transfers 1 ETH to 0xE1D9a0eADCb8082d7989D7304061c017bE296C31. (evidence c4, b0, b1)

**Question for the signers:** The transaction also does the following, which the description does not mention. Is that intended? 1 ETH Safe -> 0xE1D9a0eADCb8082d7989D7304061c017bE296C31; The Safe transfers 1 ETH to 0xE1D9a0eADCb8082d7989D7304061c017bE296C31.

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements | 1 ETH Safe -> 0xE1D9a0eADCb8082d7989D7304061c017bE296C31 |  | 1 ETH Safe -> 0xE1D9a0eADCb8082d7989D7304061c017bE296C31 |
| permissions |  |  |  |
| configs |  |  |  |

## Each pass against the truth

**Forward vs truth:** 1 difference
- missing: movement 1 ETH Safe -> 0xE1D9a0eADCb8082d7989D7304061c017bE296C31

**Backward vs truth:** agrees.

## Forward against backward

| matched | tier |
| --- | --- |

Observed, unexplained:
- [notable] 1 ETH Safe -> 0xE1D9a0eADCb8082d7989D7304061c017bE296C31 (no expected movement matches (asset, route, amount); c4, b0, b1)
- [notable] The Safe transfers 1 ETH to 0xE1D9a0eADCb8082d7989D7304061c017bE296C31. (no matched item shares its evidence; c4, b0, b1)

Info (bookkeeping):
- The Safe increments its transaction nonce from 1 to 2 and logs successful execution.

## Attribution

- `real_finding`: observed, unexplained [notable]: 1 ETH Safe -> 0xE1D9a0eADCb8082d7989D7304061c017bE296C31
- `real_finding (same evidence as the item above)`: observed, unexplained [notable]: The Safe transfers 1 ETH to 0xE1D9a0eADCb8082d7989D7304061c017bE296C31.
- `real_finding`: forward vs truth (missing): movement 1 ETH Safe -> 0xE1D9a0eADCb8082d7989D7304061c017bE296C31
- `bookkeeping`: info: The Safe increments its transaction nonce from 1 to 2 and logs successful execution.
