# 34_uniswap_output_diverted

**Description:** Buy 1,000 USDC on Uniswap, spending at most 1 ETH

**Expected verdict:** ASK  **Computed:** ASK

The trace shows 1 effect the description does not mention:
- 1,000 USDC 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc -> 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3 (evidence c9, c10, b2, b3, e5, s0, s1)

**Question for the signers:** The transaction also does the following, which the description does not mention. Is that intended? 1,000 USDC 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc -> 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements | 0.354583927628692837 ETH (ETH…) Safe -> Uniswap | at most 1 ETH Safe -> Uniswap | 0.354583927628692837 ETH Safe -> WETH |
|  |  | 1,000 USDC Uniswap -> Safe | 0.354583927628692837 WETH Uniswap -> 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc |
|  |  |  | 1,000 USDC 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc -> 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3 |
| permissions |  |  |  |
| configs |  |  |  |

Truth notes: protocol call Uniswap V2 Router.swapETHForExactTokens(uint256,address[],address,uint256): asset flows taken from the fork's balance changes

## Each pass against the truth

**Forward vs truth:** 1 difference
- extra: movement 1,000 USDC Uniswap -> Safe

**Backward vs truth:** agrees.

## Forward against backward

| matched | tier |
| --- | --- |
| 0.354583927628692837 ETH Safe -> WETH | counterparty_via_callee |
| 0.354583927628692837 WETH Uniswap -> 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc | internal_to_callee |

Observed, unexplained:
- [notable] 1,000 USDC 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc -> 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3 (no expected movement matches (asset, route, amount); c9, c10, b2, b3, e5, s0, s1)

Expected, not observed:
- movement 1,000 USDC Uniswap -> Safe

Info (bookkeeping):
- internal movement 0.354583927628692837 WETH Uniswap -> 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc
- The Safe's transaction nonce incremented from 1 to 2.

## Attribution

- `real_finding`: observed, unexplained [notable]: 1,000 USDC 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc -> 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3
- `real_finding`: expected, not observed: movement 1,000 USDC Uniswap -> Safe
- `tolerance_rule`: matched by counterparty_via_callee: 0.354583927628692837 ETH Safe -> WETH
- `tolerance_rule`: matched by internal_to_callee: 0.354583927628692837 WETH Uniswap -> 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc
- `real_finding`: forward vs truth (extra): movement 1,000 USDC Uniswap -> Safe
- `bookkeeping`: info: internal movement 0.354583927628692837 WETH Uniswap -> 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc
- `bookkeeping`: info: The Safe's transaction nonce incremented from 1 to 2.
