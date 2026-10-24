# 48_weth_payment_funded_by_wrapping

**Description:** Pay Dana 0.5 WETH.

**Expected verdict:** ASK  **Computed:** ASK

The trace shows 2 effects the description does not mention:
- 0.5 ETH Safe -> WETH (evidence c5, b0, b1, e1)
- The Safe wraps 0.5 ETH into WETH by depositing 0.5 ETH into WETH. (evidence c5, b0, b1, e1)

**Question for the signers:** The transaction also does the following, which the description does not mention. Is that intended? 0.5 ETH Safe -> WETH; The Safe wraps 0.5 ETH into WETH by depositing 0.5 ETH into WETH.

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements | 0.5 WETH Safe -> Dana | 0.5 WETH Safe -> Dana | 0.5 ETH Safe -> WETH |
|  | 0.5 ETH (ETH…) Safe -> WETH |  | 0.5 WETH Safe -> Dana |
| permissions |  |  |  |
| configs |  |  |  |

Truth notes: protocol call WETH.deposit(): asset flows taken from the fork's balance changes

## Each pass against the truth

**Forward vs truth:** 1 difference
- missing: movement 0.5 ETH (ETH…) Safe -> WETH

**Backward vs truth:** agrees.

## Forward against backward

| matched | tier |
| --- | --- |
| 0.5 WETH Safe -> Dana | exact |

Observed, unexplained:
- [notable] 0.5 ETH Safe -> WETH (no expected movement matches (asset, route, amount); c5, b0, b1, e1)
- [notable] The Safe wraps 0.5 ETH into WETH by depositing 0.5 ETH into WETH. (no matched item shares its evidence; c5, b0, b1, e1)

Info (bookkeeping):
- The Safe's nonce increments from 1 to 2.

## Attribution

- `real_finding`: observed, unexplained [notable]: 0.5 ETH Safe -> WETH
- `real_finding (same evidence as the item above)`: observed, unexplained [notable]: The Safe wraps 0.5 ETH into WETH by depositing 0.5 ETH into WETH.
- `real_finding`: forward vs truth (missing): movement 0.5 ETH (ETH…) Safe -> WETH
- `bookkeeping`: info: The Safe's nonce increments from 1 to 2.
