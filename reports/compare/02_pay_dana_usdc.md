# 02_pay_dana_usdc

**Description:** Pay Dana 2,500 USDC for October

**Expected verdict:** MATCH  **Computed:** MATCH

Every effect in the trace is accounted for by the description, and everything the description promises is in the trace (1 matched; tiers used: exact).

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements | 2500 USDC Safe -> Dana | 2,500 USDC Safe -> Dana | 2,500 USDC Safe -> Dana |
| permissions |  |  |  |
| configs |  |  |  |

## Each pass against the truth

**Forward vs truth:** agrees.

**Backward vs truth:** agrees.

## Forward against backward

| matched | tier |
| --- | --- |
| 2,500 USDC Safe -> Dana | exact |

Info (bookkeeping):
- Safe nonce incremented from 1 to 2.

## Attribution

- `bookkeeping`: info: Safe nonce incremented from 1 to 2.
