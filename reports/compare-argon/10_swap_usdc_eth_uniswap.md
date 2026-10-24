# 10_swap_usdc_eth_uniswap

**Description:** Swap 5,000 USDC for ETH on Uniswap

**Expected verdict:** MATCH  **Computed:** MATCH

Every effect in the trace is accounted for by the description, and everything the description promises is in the trace (3 matched; tiers used: exact, amount_unconstrained, counterparty_via_callee).

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements | 1.761817265430573461 ETH (ETH…) Uniswap router -> Safe | 5,000 USDC Safe -> Uniswap router | 5,000 USDC Safe -> 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc |
|  | 5000 USDC Safe -> Uniswap router | any amount ETH Uniswap router -> Safe | 1.761817265430573461 ETH Uniswap router -> Safe |
| permissions | allowance USDC Safe -> Uniswap router: 5000000000 | allowance USDC Safe -> Uniswap router: 5000000000 | allowance USDC Safe -> Uniswap router: 5000000000 |
| configs |  |  |  |

Truth notes: protocol call Uniswap router.swapExactTokensForETH(uint256,uint256,address[],address,uint256): asset flows taken from the fork's balance changes

## Each pass against the truth

**Forward vs truth:** agrees.

**Backward vs truth:** agrees.

## Forward against backward

| matched | tier |
| --- | --- |
| 5,000 USDC Safe -> 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc | counterparty_via_callee |
| 1.761817265430573461 ETH Uniswap router -> Safe | amount_unconstrained |
| allowance USDC Safe -> Uniswap router: 5000000000 | exact (expected item was implied by the words, not stated) |

Info (bookkeeping):
- 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc updates its token reserves and cumulative price accumulators.
- Safe increments its nonce from 1 to 2 and executes the batch via MultiSendCallOnly v1.4.1.

## Attribution

- `tolerance_rule`: matched by counterparty_via_callee: 5,000 USDC Safe -> 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc
- `tolerance_rule`: matched by amount_unconstrained: 1.761817265430573461 ETH Uniswap router -> Safe
- `bookkeeping`: info: 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc updates its token reserves and cumulative price accumulators.
- `bookkeeping`: info: Safe increments its nonce from 1 to 2 and executes the batch via MultiSendCallOnly v1.4.1.
