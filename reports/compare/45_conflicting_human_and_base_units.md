# 45_conflicting_human_and_base_units

**Description:** Pay Dana 1 USDC for the invoice (1,000,000,000 base units).

**Expected verdict:** ASK  **Computed:** ASK

Everything matched, but reading the description raised a question the signers must settle before anything is approved.

**Question for the signers:** The description specifies '1 USDC' but also lists '(1,000,000,000 base units)', which equals 1,000 USDC. Which amount is intended?

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements | 1 USDC Safe -> Dana | 1 USDC Safe -> Dana | 1 USDC Safe -> Dana |
| permissions |  |  |  |
| configs |  |  |  |

## Each pass against the truth

**Forward vs truth:** agrees.

**Backward vs truth:** agrees.

## Forward against backward

| matched | tier |
| --- | --- |
| 1 USDC Safe -> Dana | exact |

Info (bookkeeping):
- The Safe's nonce increased from 1 to 2.

## Attribution

- `bookkeeping`: info: The Safe's nonce increased from 1 to 2.
