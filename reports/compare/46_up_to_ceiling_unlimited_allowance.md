# 46_up_to_ceiling_unlimited_allowance

**Description:** Use up to 1,000 USDC on Uniswap to buy at least 0.000001 WETH for the Safe.

**Expected verdict:** ASK  **Computed:** ASK

The trace shows 2 effects the description does not mention:
- allowance USDC Safe -> Uniswap: unlimited (evidence c5, c6, s2, e1)
- The Safe granted an unlimited USDC allowance to Uniswap. (evidence c5, c6, s2, e1)

**Question for the signers:** The transaction also does the following, which the description does not mention. Is that intended? allowance USDC Safe -> Uniswap: unlimited; The Safe granted an unlimited USDC allowance to Uniswap.

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements | 1000 USDC Safe -> Uniswap | up to 1,000 USDC Safe -> Uniswap | 1,000 USDC Safe -> 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc |
|  | 0.352427523272240659 WETH Uniswap -> Safe | at least 0.000001 WETH Uniswap -> Safe | 0.352427523272240659 WETH 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc -> Safe |
| permissions | allowance USDC Safe -> Uniswap: unlimited | allowance USDC Safe -> Uniswap: 1000000000 | allowance USDC Safe -> Uniswap: unlimited |
| configs |  |  |  |

Truth notes: protocol call Uniswap.swapExactTokensForTokens(uint256,uint256,address[],address,uint256): asset flows taken from the fork's balance changes

## Each pass against the truth

**Forward vs truth:** 1 difference
- wrong_amount: permission allowance USDC Safe -> Uniswap: 1000000000 (truth allowance USDC Safe -> Uniswap: unlimited)

**Backward vs truth:** agrees.

## Forward against backward

| matched | tier |
| --- | --- |
| 1,000 USDC Safe -> 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc | counterparty_via_callee |
| 0.352427523272240659 WETH 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc -> Safe | counterparty_via_callee |

Observed, unexplained:
- [notable] allowance USDC Safe -> Uniswap: unlimited (no expected allowance matches (asset, spender, amount); c5, c6, s2, e1)
- [notable] The Safe granted an unlimited USDC allowance to Uniswap. (no matched item shares its evidence; c5, c6, s2, e1)

Expected, not observed:
- permission allowance USDC Safe -> Uniswap: 1000000000

Info (bookkeeping):
- The Safe incremented its transaction nonce from 1 to 2.
- 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc updated its reserves and cumulative price accounting.

## Attribution

- `real_finding`: observed, unexplained [notable]: allowance USDC Safe -> Uniswap: unlimited
- `real_finding (same evidence as the item above)`: observed, unexplained [notable]: The Safe granted an unlimited USDC allowance to Uniswap.
- `real_finding`: expected, not observed: permission allowance USDC Safe -> Uniswap: 1000000000
- `tolerance_rule`: matched by counterparty_via_callee: 1,000 USDC Safe -> 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc
- `tolerance_rule`: matched by counterparty_via_callee: 0.352427523272240659 WETH 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc -> Safe
- `real_finding`: forward vs truth (wrong_amount): permission allowance USDC Safe -> Uniswap: 1000000000 (truth allowance USDC Safe -> Uniswap: unlimited)
- `bookkeeping`: info: The Safe incremented its transaction nonce from 1 to 2.
- `bookkeeping`: info: 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc updated its reserves and cumulative price accounting.
