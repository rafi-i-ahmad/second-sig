# 32_pay_dana_wrong_wallet

**Description:** Pay Dana 2,500 USDC for October

**Expected verdict:** ASK  **Computed:** ASK

The trace shows 2 effects the description does not mention:
- 2,500 USDC Safe -> 0x97f8fD4720c6b29a0664cf3A8b3550bd1171c277 (evidence b0, b1, e1)
- The Safe transfers 2,500 USDC to 0x97f8fD4720c6b29a0664cf3A8b3550bd1171c277. (evidence c4, c5, s0, s1, b0, b1, e1)

**Question for the signers:** The transaction also does the following, which the description does not mention. Is that intended? 2,500 USDC Safe -> 0x97f8fD4720c6b29a0664cf3A8b3550bd1171c277; The Safe transfers 2,500 USDC to 0x97f8fD4720c6b29a0664cf3A8b3550bd1171c277.

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements | 2500 USDC Safe -> 0x97f8fD4720c6b29a0664cf3A8b3550bd1171c277 | 2,500 USDC Safe -> Dana | 2,500 USDC Safe -> 0x97f8fD4720c6b29a0664cf3A8b3550bd1171c277 |
| permissions |  |  |  |
| configs |  |  |  |

## Each pass against the truth

**Forward vs truth:** 1 difference
- wrong_party: movement 2,500 USDC Safe -> Dana (truth 2500 USDC Safe -> 0x97f8fD4720c6b29a0664cf3A8b3550bd1171c277)

**Backward vs truth:** agrees.

## Forward against backward

| matched | tier |
| --- | --- |

Observed, unexplained:
- [notable] 2,500 USDC Safe -> 0x97f8fD4720c6b29a0664cf3A8b3550bd1171c277 (no expected movement matches (asset, route, amount); b0, b1, e1)
- [notable] The Safe transfers 2,500 USDC to 0x97f8fD4720c6b29a0664cf3A8b3550bd1171c277. (no matched item shares its evidence; c4, c5, s0, s1, b0, b1, e1)

Expected, not observed:
- movement 2,500 USDC Safe -> Dana

Info (bookkeeping):
- The Safe increments its transaction nonce from 1 to 2.

## Attribution

- `real_finding`: observed, unexplained [notable]: 2,500 USDC Safe -> 0x97f8fD4720c6b29a0664cf3A8b3550bd1171c277
- `real_finding (same evidence as the item above)`: observed, unexplained [notable]: The Safe transfers 2,500 USDC to 0x97f8fD4720c6b29a0664cf3A8b3550bd1171c277.
- `real_finding`: expected, not observed: movement 2,500 USDC Safe -> Dana
- `real_finding (wrong recipient)`: forward vs truth (wrong_party): movement 2,500 USDC Safe -> Dana (truth 2500 USDC Safe -> 0x97f8fD4720c6b29a0664cf3A8b3550bd1171c277)
- `bookkeeping`: info: The Safe increments its transaction nonce from 1 to 2.
