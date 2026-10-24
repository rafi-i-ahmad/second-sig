# 34_uniswap_output_diverted

**Description:** Buy 1,000 USDC on Uniswap, spending at most 1 ETH

**Expected verdict:** REJECT  **Computed:** ASK

The trace shows 2 effects the description does not mention:
- 1,000 USDC 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc -> 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3 (evidence b2, b3, c9, c10, e5, s0, s1)
- The Uniswap V2 pair 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc transfers 1,000 USDC to recipient 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3. (evidence c8, c9, c10, b2, b3, e4, e5, s0, s1)

**Question for the signers:** The transaction also does the following, which the description does not mention. Is that intended? 1,000 USDC 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc -> 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3; The Uniswap V2 pair 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc transfers 1,000 USDC to recipient 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3.

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements | 0.354583927628692837 ETH (ETH…) Safe -> Uniswap | at most 1 ETH Safe -> Uniswap | 0.354583927628692837 ETH Safe -> WETH |
|  |  | 1,000 USDC Uniswap -> Safe | 1,000 USDC 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc -> 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3 |
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

Observed, unexplained:
- [notable] 1,000 USDC 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc -> 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3 (no expected movement matches (asset, route, amount); b2, b3, c9, c10, e5, s0, s1)
- [notable] The Uniswap V2 pair 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc transfers 1,000 USDC to recipient 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3. (no matched item shares its evidence; c8, c9, c10, b2, b3, e4, e5, s0, s1)

Expected, not observed:
- movement 1,000 USDC Uniswap -> Safe

Info (bookkeeping):
- The Safe's transaction nonce increases from 1 to 2.
- Uniswap deposits 0.354583927628692837 ETH into WETH and transfers it to the Uniswap V2 pair 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc.
- Uniswap refunds the remaining 0.645416072371307163 ETH of unused funds back to the Safe.

## Attribution

- `real_finding`: observed, unexplained [notable]: 1,000 USDC 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc -> 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3
- `real_finding (same evidence as the item above)`: observed, unexplained [notable]: The Uniswap V2 pair 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc transfers 1,000 USDC to recipient 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3.
- `real_finding`: expected, not observed: movement 1,000 USDC Uniswap -> Safe
- `tolerance_rule`: matched by counterparty_via_callee: 0.354583927628692837 ETH Safe -> WETH
- `real_finding`: forward vs truth (extra): movement 1,000 USDC Uniswap -> Safe
- `bookkeeping`: info: The Safe's transaction nonce increases from 1 to 2.
- `bookkeeping`: info: Uniswap deposits 0.354583927628692837 ETH into WETH and transfers it to the Uniswap V2 pair 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc.
- `bookkeeping`: info: Uniswap refunds the remaining 0.645416072371307163 ETH of unused funds back to the Safe.
