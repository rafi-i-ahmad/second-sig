# 07_pay_three_contractors

**Description:** Pay three contractors their October invoices: Alice 1,200 USDC, Bob 3,400 USDC, Chen 800 USDC

**Expected verdict:** MATCH  **Computed:** MATCH

Every effect in the trace is accounted for by the description, and everything the description promises is in the trace (3 matched; tiers used: exact).

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements | 1200 USDC Safe -> Alice | 1,200 USDC Safe -> Alice | 1,200 USDC Safe -> Alice |
|  | 3400 USDC Safe -> Bob | 3,400 USDC Safe -> Bob | 3,400 USDC Safe -> Bob |
|  | 800 USDC Safe -> Chen | 800 USDC Safe -> Chen | 800 USDC Safe -> Chen |
| permissions |  |  |  |
| configs |  |  |  |

## Each pass against the truth

**Forward vs truth:** agrees.

**Backward vs truth:** agrees.

## Forward against backward

| matched | tier |
| --- | --- |
| 1,200 USDC Safe -> Alice | exact |
| 3,400 USDC Safe -> Bob | exact |
| 800 USDC Safe -> Chen | exact |

Info (bookkeeping):
- Safe increments its transaction nonce from 1 to 2 and records successful execution of the MultiSendCallOnly v1.4.1 batch.

## Attribution

- `bookkeeping`: info: Safe increments its transaction nonce from 1 to 2 and records successful execution of the MultiSendCallOnly v1.4.1 batch.
