# 03_move_eth_usdc_hot

**Description:** Move 20 ETH and 10,000 USDC to the hot wallet

**Expected verdict:** MATCH  **Computed:** MATCH

Every effect in the trace is accounted for by the description, and everything the description promises is in the trace (2 matched; tiers used: exact).

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements | 20 ETH Safe -> hot wallet | 20 ETH Safe -> hot wallet | 20 ETH Safe -> hot wallet |
|  | 10000 USDC Safe -> hot wallet | 10,000 USDC Safe -> hot wallet | 10,000 USDC Safe -> hot wallet |
| permissions |  |  |  |
| configs |  |  |  |

## Each pass against the truth

**Forward vs truth:** agrees.

**Backward vs truth:** agrees.

## Forward against backward

| matched | tier |
| --- | --- |
| 20 ETH Safe -> hot wallet | exact |
| 10,000 USDC Safe -> hot wallet | exact |

Info (bookkeeping):
- Safe increments its transaction nonce from 1 to 2 and emits ExecutionSuccess.

## Attribution

- `bookkeeping`: info: Safe increments its transaction nonce from 1 to 2 and emits ExecutionSuccess.
