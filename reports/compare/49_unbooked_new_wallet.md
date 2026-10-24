# 49_unbooked_new_wallet

**Description:** Pay Dana 2,500 USDC for October; use the new wallet from her last email.

**Expected verdict:** ASK  **Computed:** ASK

The trace shows 2 effects the description does not mention:
- 2,500 USDC Safe -> 0x2CE0D5f39587f090b1bb39122517A8554D0e447c (evidence c4, c5, s0, s1, b0, b1, e1)
- The Safe transfers 2,500 USDC to 0x2CE0D5f39587f090b1bb39122517A8554D0e447c. (evidence c4, c5, s0, s1, b0, b1, e1)

**Question for the signers:** The transaction also does the following, which the description does not mention. Is that intended? 2,500 USDC Safe -> 0x2CE0D5f39587f090b1bb39122517A8554D0e447c; The Safe transfers 2,500 USDC to 0x2CE0D5f39587f090b1bb39122517A8554D0e447c.

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements | 2500 USDC Safe -> 0x2CE0D5f39587f090b1bb39122517A8554D0e447c |  | 2,500 USDC Safe -> 0x2CE0D5f39587f090b1bb39122517A8554D0e447c |
| permissions |  |  |  |
| configs |  |  |  |

## Each pass against the truth

**Forward vs truth:** 1 difference
- missing: movement 2500 USDC Safe -> 0x2CE0D5f39587f090b1bb39122517A8554D0e447c

**Backward vs truth:** agrees.

## Forward against backward

| matched | tier |
| --- | --- |

Observed, unexplained:
- [notable] 2,500 USDC Safe -> 0x2CE0D5f39587f090b1bb39122517A8554D0e447c (no expected movement matches (asset, route, amount); c4, c5, s0, s1, b0, b1, e1)
- [notable] The Safe transfers 2,500 USDC to 0x2CE0D5f39587f090b1bb39122517A8554D0e447c. (no matched item shares its evidence; c4, c5, s0, s1, b0, b1, e1)

Info (bookkeeping):
- The Safe's transaction nonce is incremented from 1 to 2.

## Attribution

- `real_finding`: observed, unexplained [notable]: 2,500 USDC Safe -> 0x2CE0D5f39587f090b1bb39122517A8554D0e447c
- `real_finding (same evidence as the item above)`: observed, unexplained [notable]: The Safe transfers 2,500 USDC to 0x2CE0D5f39587f090b1bb39122517A8554D0e447c.
- `real_finding`: forward vs truth (missing): movement 2500 USDC Safe -> 0x2CE0D5f39587f090b1bb39122517A8554D0e447c
- `bookkeeping`: info: The Safe's transaction nonce is incremented from 1 to 2.
