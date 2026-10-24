# 42_calldata_note_dust_eth

**Description:** Pay Dana 2,500 USDC for October

**Expected verdict:** ASK  **Computed:** ASK

The trace shows 2 effects the description does not mention:
- 0.000000000000000001 ETH Safe -> Dana (evidence c7, b0, b1)
- Safe transfers 0.000000000000000001 ETH (1 wei) to Dana. (evidence c7, b0, b1)

**Question for the signers:** The transaction also does the following, which the description does not mention. Is that intended? 0.000000000000000001 ETH Safe -> Dana; Safe transfers 0.000000000000000001 ETH (1 wei) to Dana.

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
- [notable] Safe transfers 0.000000000000000001 ETH (1 wei) to Dana. (no matched item shares its evidence; c7, b0, b1)

Info (bookkeeping):
- Safe makes a zero-value call with calldata to Dana, an account with no code.
- Safe increments its nonce from 1 to 2 and emits ExecutionSuccess.

## Attribution

- `real_finding`: observed, unexplained [notable]: 0.000000000000000001 ETH Safe -> Dana
- `real_finding (same evidence as the item above)`: observed, unexplained [notable]: Safe transfers 0.000000000000000001 ETH (1 wei) to Dana.
- `real_finding`: forward vs truth (missing): movement 0.000000000000000001 ETH Safe -> Dana
- `bookkeeping`: info: Safe makes a zero-value call with calldata to Dana, an account with no code.
- `bookkeeping`: info: Safe increments its nonce from 1 to 2 and emits ExecutionSuccess.
