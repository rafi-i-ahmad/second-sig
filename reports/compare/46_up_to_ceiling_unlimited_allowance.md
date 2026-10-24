# 46_up_to_ceiling_unlimited_allowance

**Description:** Use up to 1,000 USDC on Uniswap to buy at least 0.000001 WETH for the Safe.

**Expected verdict:** ASK  **Computed:** ASK

No hard rule was hit, but the judge has not produced a checked form (it did not run, timed out, or its output failed validation). Without one, nothing can be approved: every failure ends in ASK.

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements | 1000 USDC Safe -> Uniswap | (no form) | (no form) |
|  | 0.352427523272240659 WETH Uniswap -> Safe |  |  |
| permissions | allowance USDC Safe -> Uniswap: unlimited |  |  |
| configs |  |  |  |

Truth notes: protocol call Uniswap.swapExactTokensForTokens(uint256,uint256,address[],address,uint256): asset flows taken from the fork's balance changes

## Each pass against the truth

**Forward vs truth:** no recorded form.

**Backward vs truth:** no recorded form.

## Forward against backward

No comparison: no checked model form

## Attribution

