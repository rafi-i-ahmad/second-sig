# 04_add_owner_priya

**Description:** Add Priya as a signer

**Expected verdict:** MATCH  **Computed:** MATCH

Every effect in the trace is accounted for by the description, and everything the description promises is in the trace (2 matched; tiers used: exact).

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements |  |  |  |
| permissions |  |  |  |
| configs | owners_add = 0xB55c0E1dE2aF38cF741De4b2C8D6D5bb34e9AfE8 | owners_add = 0xB55c0E1dE2aF38cF741De4b2C8D6D5bb34e9AfE8 | owners_add = 0xB55c0E1dE2aF38cF741De4b2C8D6D5bb34e9AfE8 |
|  | threshold = 2 | threshold = 2 | threshold = 2 |

## Each pass against the truth

**Forward vs truth:** agrees.

**Backward vs truth:** agrees.

## Forward against backward

| matched | tier |
| --- | --- |
| owners_add = 0xB55c0E1dE2aF38cF741De4b2C8D6D5bb34e9AfE8 | exact |
| threshold = 2 | exact |

Info (bookkeeping):
- Safe increments its transaction nonce from 1 to 2 and records successful execution.

## Attribution

- `bookkeeping`: info: Safe increments its transaction nonce from 1 to 2 and records successful execution.
