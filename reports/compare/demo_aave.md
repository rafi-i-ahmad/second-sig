# demo_aave

**Description:** Deposit 10,000 USDC into Aave v3

**Expected verdict:** MATCH  **Computed:** MATCH

Every effect in the trace is accounted for by the description, and everything the description promises is in the trace (3 matched; tiers used: exact, counterparty_via_callee, inbound_from_callee).

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements | 10000 aEthUSDC (0x98C2…) Aave v3 Pool -> Safe | 10,000 USDC Safe -> Aave v3 Pool | 10,000 USDC Safe -> 0x98C23E9d8f34FEFb1B7BD6a91B7FF122F4e16F5c |
|  | 10000 USDC Safe -> Aave v3 Pool |  | 10,000 aEthUSDC zero address -> Safe |
| permissions | allowance USDC Safe -> Aave v3 Pool: 10000000000 | allowance USDC Safe -> Aave v3 Pool: 10000000000 | allowance USDC Safe -> Aave v3 Pool: 10000000000 |
| configs |  |  |  |

Truth notes: protocol call Aave v3 Pool.supply(address,uint256,address,uint16): asset flows taken from the fork's balance changes

## Each pass against the truth

**Forward vs truth:** 1 difference
- missing: movement 10000 aEthUSDC (0x98C2…) Aave v3 Pool -> Safe

**Backward vs truth:** agrees.

## Forward against backward

| matched | tier |
| --- | --- |
| 10,000 USDC Safe -> 0x98C23E9d8f34FEFb1B7BD6a91B7FF122F4e16F5c | counterparty_via_callee |
| 10,000 aEthUSDC zero address -> Safe | inbound_from_callee (receiving an asset cannot drain the Safe) |
| allowance USDC Safe -> Aave v3 Pool: 10000000000 | exact (expected item was implied by the words, not stated) |

Info (bookkeeping):
- The Safe increases its nonce from 1 to 2.
- Aave v3 Pool updates reserve accounting data and interest rates for USDC.

## Attribution

- `tolerance_rule`: matched by counterparty_via_callee: 10,000 USDC Safe -> 0x98C23E9d8f34FEFb1B7BD6a91B7FF122F4e16F5c
- `tolerance_rule`: matched by inbound_from_callee: 10,000 aEthUSDC zero address -> Safe
- `bookkeeping`: info: The Safe increases its nonce from 1 to 2.
- `bookkeeping`: info: Aave v3 Pool updates reserve accounting data and interest rates for USDC.
