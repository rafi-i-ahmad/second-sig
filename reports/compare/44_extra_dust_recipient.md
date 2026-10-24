# 44_extra_dust_recipient

**Description:** Pay the Q3 invoice from Acme, 8,000 USDC.

**Expected verdict:** ASK  **Computed:** ASK

The trace shows 1 effect the description does not mention:
- 1 USDC Safe -> 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3 (evidence c7, c8, s0, s1, b0, b2, e2)

**Question for the signers:** The transaction also does the following, which the description does not mention. Is that intended? 1 USDC Safe -> 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements | 8000 USDC Safe -> Acme | 8,000 USDC Safe -> Acme | 8,000 USDC Safe -> Acme |
|  | 1 USDC Safe -> 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3 |  | 1 USDC Safe -> 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3 |
| permissions |  |  |  |
| configs |  |  |  |

## Each pass against the truth

**Forward vs truth:** 1 difference
- missing: movement 1 USDC Safe -> 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3

**Backward vs truth:** agrees.

## Forward against backward

| matched | tier |
| --- | --- |
| 8,000 USDC Safe -> Acme | exact |

Observed, unexplained:
- [notable] 1 USDC Safe -> 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3 (no expected movement matches (asset, route, amount); c7, c8, s0, s1, b0, b2, e2)

Info (bookkeeping):
- The Safe increments its nonce from 1 to 2.

## Attribution

- `real_finding`: observed, unexplained [notable]: 1 USDC Safe -> 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3
- `real_finding`: forward vs truth (missing): movement 1 USDC Safe -> 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3
- `bookkeeping`: info: The Safe increments its nonce from 1 to 2.
