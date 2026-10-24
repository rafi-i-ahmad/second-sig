# 42_calldata_note_dust_eth

**Description:** Pay Dana 2,500 USDC for October

**Expected verdict:** ASK  **Computed:** ASK

No hard rule was hit, but the judge has not produced a checked form (it did not run, timed out, or its output failed validation). Without one, nothing can be approved: every failure ends in ASK.

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements | 2500 USDC Safe -> Dana | (no form) | (no form) |
|  | 0.000000000000000001 ETH Safe -> Dana |  |  |
| permissions |  |  |  |
| configs |  |  |  |

Truth notes: protocol call Dana.note(string): asset flows taken from the fork's balance changes

## Each pass against the truth

**Forward vs truth:** no recorded form.

**Backward vs truth:** no recorded form.

## Forward against backward

No comparison: no checked model form

## Attribution

