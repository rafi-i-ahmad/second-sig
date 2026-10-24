# 48_weth_payment_funded_by_wrapping

**Description:** Pay Dana 0.5 WETH.

**Expected verdict:** ASK  **Computed:** ASK

No hard rule was hit, but the judge has not produced a checked form (it did not run, timed out, or its output failed validation). Without one, nothing can be approved: every failure ends in ASK.

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements | 0.5 WETH Safe -> Dana | (no form) | (no form) |
|  | 0.5 ETH (ETH…) Safe -> WETH |  |  |
| permissions |  |  |  |
| configs |  |  |  |

Truth notes: protocol call WETH.deposit(): asset flows taken from the fork's balance changes

## Each pass against the truth

**Forward vs truth:** no recorded form.

**Backward vs truth:** no recorded form.

## Forward against backward

No comparison: no checked model form

## Attribution

