# 06_approve_uniswap_finite

**Description:** Approve the Uniswap router to spend 1,000 USDC for next week's swap

**Expected verdict:** MATCH  **Computed:** MATCH

Every effect in the trace is accounted for by the description, and everything the description promises is in the trace (1 matched; tiers used: exact).

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements |  |  |  |
| permissions | allowance USDC Safe -> Uniswap router: 1000000000 | allowance USDC Safe -> Uniswap router: 1000000000 | allowance USDC Safe -> Uniswap router: 1000000000 |
| configs |  |  |  |

## Each pass against the truth

**Forward vs truth:** agrees.

**Backward vs truth:** agrees.

## Forward against backward

| matched | tier |
| --- | --- |
| allowance USDC Safe -> Uniswap router: 1000000000 | exact |

Info (bookkeeping):
- The Safe's nonce increments from 1 to 2.

## Attribution

- `bookkeeping`: info: The Safe's nonce increments from 1 to 2.
