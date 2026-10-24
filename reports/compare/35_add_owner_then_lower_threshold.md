# 35_add_owner_then_lower_threshold

**Description:** Add Ravi as a backup owner; keep approval at 2 signatures

**Expected verdict:** REJECT  **Computed:** REJECT

2 critical effects in the trace that nothing in the description accounts for:
- threshold = 1 (evidence c7, c8, s1, e2; no expected Safe config change matches)
- Safe's signature threshold is lowered from 2 to 1. (evidence c7, c8, s1, e2; no matched item shares its evidence)

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements |  |  |  |
| permissions |  |  |  |
| configs | owners_add = 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3 | owners_add = 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3 | owners_add = 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3 |
|  | threshold = 2 | threshold = 2 | threshold = 2 |
|  | threshold = 1 |  | threshold = 1 |

## Each pass against the truth

**Forward vs truth:** 1 difference
- missing: config threshold = 1

**Backward vs truth:** agrees.

## Forward against backward

| matched | tier |
| --- | --- |
| owners_add = 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3 | exact |
| threshold = 2 | exact |

Observed, unexplained:
- [critical] threshold = 1 (no expected Safe config change matches; c7, c8, s1, e2)
- [critical] Safe's signature threshold is lowered from 2 to 1. (no matched item shares its evidence; c7, c8, s1, e2)

Info (bookkeeping):
- Safe's transaction nonce increases from 1 to 2.

## Attribution

- `real_finding`: observed, unexplained [critical]: threshold = 1
- `real_finding (same evidence as the item above)`: observed, unexplained [critical]: Safe's signature threshold is lowered from 2 to 1.
- `real_finding`: forward vs truth (missing): config threshold = 1
- `bookkeeping`: info: Safe's transaction nonce increases from 1 to 2.
