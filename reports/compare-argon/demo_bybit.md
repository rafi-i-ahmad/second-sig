# demo_bybit

**Description:** Transfer 500 ETH to the warm wallet

**Expected verdict:** REJECT  **Computed:** REJECT

Rejected by the hard floor before any model ran. 3 hard rule hits (delegatecall_not_allowlisted, protected_slot_write, unverified_code). These rules have no honest counterexample, so the description is irrelevant: whatever it says, this transaction must not execute.

The transaction makes the Safe run another contract's code as if it were the Safe's own (a delegatecall), and that contract is not the standard Safe batching helper (MultiSendCallOnly). Code run this way can change anything inside the Safe, including who owns it and which contract it trusts as its master copy. This is the shape of the Bybit attack. No honest payment, deposit or swap needs it. What the rehearsal showed: The Safe delegatecalls 0x9622…7242, which is not MultiSendCallOnly: that code runs with the Safe's own storage and funds. (evidence c4).

The transaction changes one of the Safe's own settings: its master copy (the contract that holds all of its logic), its guard, its fallback handler, or its list of modules. Ordinary transactions never touch these. Changing them hands control of the Safe to whoever wrote the new value, and the owners' signatures would no longer mean anything. What the rehearsal showed: The Safe's singleton (slot 0) changes from 0x4167…461a to 0xbDd0…9516. (evidence s0).

The transaction calls a contract whose source code is not verified on Etherscan. Nobody, human or model, can read what that code does, so approving it would mean trusting it blind. Attackers deploy their contracts unverified for exactly this reason. What the rehearsal showed: 0x9622…7242 has no verified source. (evidence c4).

## The three canonical lists

| | truth (bytes) | forward (words) | backward (trace) |
| --- | --- | --- | --- |
| movements |  | 500 ETH Safe -> warm wallet |  |
| permissions |  |  |  |
| configs |  |  |  |

Truth notes: delegatecall to Bybit attackers' contract (not in the address book): no asset flow derivable from calldata

## Each pass against the truth

**Forward vs truth:** 1 difference
- extra: movement 500 ETH Safe -> warm wallet

**Backward vs truth:** agrees.

## Forward against backward

No comparison: delegatecall_not_allowlisted: The Safe delegatecalls 0x9622…7242, which is not MultiSendCallOnly: that code runs with the Safe's own storage and funds.; protected_slot_write: The Safe's singleton (slot 0) changes from 0x4167…461a to 0xbDd0…9516.; unverified_code: 0x9622…7242 has no verified source.

## Attribution

- `real_finding`: forward vs truth (extra): movement 500 ETH Safe -> warm wallet
