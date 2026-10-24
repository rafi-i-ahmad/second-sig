# 08_refund_sam

**Description:** Refund Sam the 0.5 ETH he overpaid

**Expected verdict:** MATCH  **Computed:** MATCH

Every effect in the trace is accounted for by the description, and everything the description promises is in the trace (1 matched; tiers used: exact).

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements | 0.5 ETH Safe -> Sam | 0.5 ETH Safe -> Sam | 0.5 ETH Safe -> Sam |
| permissions |  |  |  |
| configs |  |  |  |

## Each pass against the truth

**Forward vs truth:** agrees.

**Backward vs truth:** agrees.

## Forward against backward

| matched | tier |
| --- | --- |
| 0.5 ETH Safe -> Sam | exact |

Info (bookkeeping):
- The Safe's nonce increments from 1 to 2.
- The Safe emits an ExecutionSuccess event.

## Attribution

- `bookkeeping`: info: The Safe's nonce increments from 1 to 2.
- `bookkeeping`: info: The Safe emits an ExecutionSuccess event.
