# 50_add_owner_threshold_side_effect

**Description:** Add Ravi as a backup owner.

**Expected verdict:** REJECT  **Computed:** REJECT

1 critical effect in the trace that nothing in the description accounts for:
- threshold = 1 (evidence c4, c5, s1, e2; no expected Safe config change matches)

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements |  |  |  |
| permissions |  |  |  |
| configs | owners_add = 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3 | owners_add = 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3 | owners_add = 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3 |
|  | threshold = 1 | threshold = 2 | threshold = 1 |

## Each pass against the truth

**Forward vs truth:** 2 differences
- missing: config threshold = 1
- extra: config threshold = 2

**Backward vs truth:** agrees.

## Forward against backward

| matched | tier |
| --- | --- |
| owners_add = 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3 | exact |

Observed, unexplained:
- [critical] threshold = 1 (no expected Safe config change matches; c4, c5, s1, e2)

Expected, not observed:
- config threshold = 2

Info (bookkeeping):
- The Safe verifies signatures, increments its nonce from 1 to 2, and records successful execution.

## Attribution

- `real_finding`: observed, unexplained [critical]: threshold = 1
- `real_finding`: expected, not observed: config threshold = 2
- `real_finding`: forward vs truth (missing): config threshold = 1
- `real_finding`: forward vs truth (extra): config threshold = 2
- `bookkeeping`: info: The Safe verifies signatures, increments its nonce from 1 to 2, and records successful execution.
