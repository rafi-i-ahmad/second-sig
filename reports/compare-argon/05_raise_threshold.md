# 05_raise_threshold

**Description:** Raise the signing threshold to 3 of 4

**Expected verdict:** MATCH  **Computed:** MATCH

Every effect in the trace is accounted for by the description, and everything the description promises is in the trace (1 matched; tiers used: exact).

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements |  |  |  |
| permissions |  |  |  |
| configs | threshold = 3 | threshold = 3 | threshold = 3 |

## Each pass against the truth

**Forward vs truth:** agrees.

**Backward vs truth:** agrees.

## Forward against backward

| matched | tier |
| --- | --- |
| threshold = 3 | exact |

Info (bookkeeping):
- The Safe's transaction nonce is incremented from 1 to 2 and execution succeeds.

## Attribution

- `bookkeeping`: info: The Safe's transaction nonce is incremented from 1 to 2 and execution succeeds.
