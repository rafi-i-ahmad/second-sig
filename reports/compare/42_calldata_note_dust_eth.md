# 42_calldata_note_dust_eth

**Description:** Pay Dana 2,500 USDC for October

**Expected verdict:** ASK  **Computed:** ASK

The trace shows 3 effects the description does not mention:
- 0.000000000000000001 ETH Safe -> Dana (evidence c7, b0, b1)
- The Safe transfers 1 wei of ETH to Dana. (evidence c7, b0, b1)
- The Safe calls Dana with calldata carrying an unparsed function payload. (evidence c8)

**Question for the signers:** The transaction also does the following, which the description does not mention. Is that intended? 0.000000000000000001 ETH Safe -> Dana; The Safe transfers 1 wei of ETH to Dana.; The Safe calls Dana with calldata carrying an unparsed function payload.

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements | 2500 USDC Safe -> Dana | 2,500 USDC Safe -> Dana | 2,500 USDC Safe -> Dana |
|  | 0.000000000000000001 ETH Safe -> Dana |  | 0.000000000000000001 ETH Safe -> Dana |
| permissions |  |  |  |
| configs |  |  |  |

Truth notes: protocol call Dana.note(string): asset flows taken from the fork's balance changes

## Each pass against the truth

**Forward vs truth:** 1 difference
- missing: movement 0.000000000000000001 ETH Safe -> Dana

**Backward vs truth:** agrees.

## Forward against backward

| matched | tier |
| --- | --- |
| 2,500 USDC Safe -> Dana | exact |

Observed, unexplained:
- [notable] 0.000000000000000001 ETH Safe -> Dana (no expected movement matches (asset, route, amount); c7, b0, b1)
- [notable] The Safe transfers 1 wei of ETH to Dana. (no matched item shares its evidence; c7, b0, b1)
- [notable] The Safe calls Dana with calldata carrying an unparsed function payload. (no matched item shares its evidence; c8)

Info (bookkeeping):
- The Safe's transaction nonce increases from 1 to 2.

## Attribution

- `real_finding`: observed, unexplained [notable]: 0.000000000000000001 ETH Safe -> Dana
- `real_finding (same evidence as the item above)`: observed, unexplained [notable]: The Safe transfers 1 wei of ETH to Dana.
- `needs_investigation`: observed, unexplained [notable]: The Safe calls Dana with calldata carrying an unparsed function payload.
- `real_finding`: forward vs truth (missing): movement 0.000000000000000001 ETH Safe -> Dana
- `bookkeeping`: info: The Safe's transaction nonce increases from 1 to 2.
