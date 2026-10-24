# 01_send_eth_ops

**Description:** Send 5 ETH to the ops wallet

**Expected verdict:** MATCH  **Computed:** MATCH

Every effect in the trace is accounted for by the description, and everything the description promises is in the trace (1 matched; tiers used: exact).

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements | 5 ETH Safe -> ops wallet | 5 ETH Safe -> ops wallet | 5 ETH Safe -> ops wallet |
| permissions |  |  |  |
| configs |  |  |  |

## Each pass against the truth

**Forward vs truth:** agrees.

**Backward vs truth:** agrees.

## Forward against backward

| matched | tier |
| --- | --- |
| 5 ETH Safe -> ops wallet | exact |

Info (bookkeeping):
- The Safe's nonce increments from 1 to 2.

## Attribution

- `bookkeeping`: info: The Safe's nonce increments from 1 to 2.
