# What the escalation step asks the signers

Model: `gemini-4-argon`, thinking medium. Inputs: the saved comparison for each case (reports/compare/<id>.json). The decision was made by code before the model was asked; the model's reading of the gap is advisory.

| Case | Description | Verdict (code) | Gap kind (model) | Honest proposer? | Question |
| --- | --- | --- | --- | --- | --- |
| demo_auditor | Pay our auditor 100 USDC | ASK | omission | no | In addition to transferring 100 USDC, this transaction grants auditor (0x46F43A4Cb3c2cD27c36f07cfd691E8a22Dd60A4C) an unlimited allowance to spend the Safe's USDC. Did you intend to give auditor unlimited access to the Safe's USDC balance? |
| 09_routine_transfer_vague | Routine transfer | ASK | vague_description | yes | Did you intend for this routine transfer to send 1 ETH from the Safe to 0xE1D9a0eADCb8082d7989D7304061c017bE296C31? |
| 31_revoke_ravi_usdc | Revoke Ravi's USDC allowance | ASK | contradiction | no | The description says this revokes Ravi's USDC allowance, but the transaction actually grants Ravi an unlimited USDC allowance. Did you intend to grant an unlimited USDC allowance to Ravi instead of setting it to zero? |
| 32_pay_dana_wrong_wallet | Pay Dana 2,500 USDC for October | ASK | contradiction | no | This transaction sends 2,500 USDC to 0x97f8fD4720c6b29a0664cf3A8b3550bd1171c277 instead of Dana's address on file (0x4716b53aC6fd6AeFbb0E6a4687eAE260011bd315). Did Dana provide a new payment address for October, or is this the wrong recipient? |
| 33_pay_ravi_but_approve | Pay Ravi 2,500 USDC for October | ASK | contradiction | unlikely | This transaction approves Ravi to spend up to 2,500 USDC from the Safe rather than transferring 2,500 USDC directly to Ravi. Did you intend to grant a spending allowance instead of making a direct payment? |
| 34_uniswap_output_diverted | Buy 1,000 USDC on Uniswap, spending at most 1 ETH | ASK | contradiction | no | Why does this swap send the purchased 1,000 USDC to 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3 instead of the Safe? |
| 35_add_owner_then_lower_threshold | Add Ravi as a backup owner; keep approval at 2 signatures | REJECT | contradiction | no | The description states that the approval threshold will remain at 2 signatures after adding Ravi, why does the transaction lower the Safe's signature threshold from 2 to 1? |

## demo_auditor

**Question:** In addition to transferring 100 USDC, this transaction grants auditor (0x46F43A4Cb3c2cD27c36f07cfd691E8a22Dd60A4C) an unlimited allowance to spend the Safe's USDC. Did you intend to give auditor unlimited access to the Safe's USDC balance?

What to check:
- Check why an approve call on USDC (0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48) is bundled with a direct transfer in the MultiSend batch.
- Verify with the proposer whether auditor (0x46F43A4Cb3c2cD27c36f07cfd691E8a22Dd60A4C) is a contract that requires an allowance or a standard recipient that only needed the 100 USDC transfer.
- Confirm whether the unlimited USDC allowance should be removed before signing.

<details><summary>reasoning</summary>

The description states that the transaction pays the auditor 100 USDC, which matches the 100 USDC transfer in the trace. However, the transaction also grants the auditor an unlimited USDC allowance from the Safe, which is completely omitted from the description and unnecessary for a direct transfer.

</details>

## 09_routine_transfer_vague

**Question:** Did you intend for this routine transfer to send 1 ETH from the Safe to 0xE1D9a0eADCb8082d7989D7304061c017bE296C31?

What to check:
- Verify that 0xE1D9a0eADCb8082d7989D7304061c017bE296C31 is the intended recipient address.
- Confirm that 1 ETH is the exact amount and asset expected for this transfer.

<details><summary>reasoning</summary>

The proposer described the transaction merely as a 'Routine transfer', specifying no asset, amount, or recipient. The trace shows a transfer of 1 ETH from the Safe to 0xE1D9a0eADCb8082d7989D7304061c017bE296C31. Because the description fixes no details that can be checked against the trace, this is a vague description.

</details>

## 31_revoke_ravi_usdc

**Question:** The description says this revokes Ravi's USDC allowance, but the transaction actually grants Ravi an unlimited USDC allowance. Did you intend to grant an unlimited USDC allowance to Ravi instead of setting it to zero?

What to check:
- Confirm whether Ravi (0x2C81904f370e7f6490aEa328CA847AEFdc3853D3) should have their USDC allowance revoked (set to 0) or set to unlimited.
- Verify the allowance amount parameter in the USDC (0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48) approval call.

<details><summary>reasoning</summary>

The proposer's description promises to revoke Ravi's USDC allowance (setting it to zero). However, the transaction trace shows the exact opposite: the Safe grants an unlimited USDC allowance to Ravi. This is a direct contradiction.

</details>

## 32_pay_dana_wrong_wallet

**Question:** This transaction sends 2,500 USDC to 0x97f8fD4720c6b29a0664cf3A8b3550bd1171c277 instead of Dana's address on file (0x4716b53aC6fd6AeFbb0E6a4687eAE260011bd315). Did Dana provide a new payment address for October, or is this the wrong recipient?

What to check:
- Verify directly with Dana via an out-of-band channel whether 0x97f8fD4720c6b29a0664cf3A8b3550bd1171c277 is her valid new address.
- Check the October invoice or payment request from Dana to see which wallet address was specified.
- Update the Safe address book if Dana has officially changed her receiving address.

<details><summary>reasoning</summary>

The proposer's description promises to pay 2,500 USDC to Dana, whose known address in the address book is 0x4716b53aC6fd6AeFbb0E6a4687eAE260011bd315. However, the transaction trace shows the 2,500 USDC being transferred to an unknown address, 0x97f8fD4720c6b29a0664cf3A8b3550bd1171c277. This is a direct contradiction in the recipient of the funds.

</details>

## 33_pay_ravi_but_approve

**Question:** This transaction approves Ravi to spend up to 2,500 USDC from the Safe rather than transferring 2,500 USDC directly to Ravi. Did you intend to grant a spending allowance instead of making a direct payment?

What to check:
- Verify whether the transaction was meant to call `transfer` rather than `approve` on the USDC contract.
- Check if Ravi (0x2C81904f370e7f6490aEa328CA847AEFdc3853D3) is a smart contract or automated pull-payment system that requires an allowance to pull the 2,500 USDC.
- Confirm whether Ravi already has an existing USDC allowance or if a direct transfer should be queued instead.

<details><summary>reasoning</summary>

The proposer's description promises a direct payment (transfer) of 2,500 USDC from the Safe to Ravi. However, the transaction trace shows no token transfer; instead, it grants Ravi an ERC-20 allowance to spend up to 2,500 USDC (2,500,000,000 raw units) from the Safe. Per the definition, an approval where a payment was promised is a contradiction.

</details>

## 34_uniswap_output_diverted

**Question:** Why does this swap send the purchased 1,000 USDC to 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3 instead of the Safe?

What to check:
- Verify who owns or controls the recipient address 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3.
- Check whether the recipient parameter (`to`) in the Uniswap router call was intended to be the Safe's address (0x5afe5afE5afE5afE5afE5aFe5aFe5Afe5Afe5AfE).
- Confirm with the proposer whether this transaction is supposed to be a payment to a third party rather than a treasury swap.

<details><summary>reasoning</summary>

The description says the Safe is buying 1,000 USDC on Uniswap for at most 1 ETH, which implies the Safe itself will receive the purchased USDC. The trace shows the Safe spends ~0.3546 ETH via Uniswap, but the resulting 1,000 USDC is sent to an external address (0x2C81904f370e7f6490aEa328CA847AEFdc3853D3) rather than back to the Safe (0x5afe5afE5afE5afE5afE5aFe5aFe5Afe5Afe5AfE).

</details>

## 35_add_owner_then_lower_threshold

**Question:** The description states that the approval threshold will remain at 2 signatures after adding Ravi, why does the transaction lower the Safe's signature threshold from 2 to 1?

What to check:
- Verify whether the Safe's signature threshold is supposed to be lowered to 1 or remain at 2.
- Inspect the batched calls in the MultiSendCallOnly v1.4.1 payload for an extra changeThreshold call setting the threshold to 1.
- Confirm with the proposer why the transaction bytes contradict the stated threshold of 2.

<details><summary>reasoning</summary>

The proposer's description promises to add Ravi (0x2C81904f370e7f6490aEa328CA847AEFdc3853D3) as an owner and keep the approval threshold at 2 signatures. While the transaction trace does add Ravi with a threshold of 2, it also executes a further change lowering the Safe's signature threshold from 2 to 1. This directly contradicts the explicit promise to keep the threshold at 2.

</details>
