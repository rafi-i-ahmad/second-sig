# What the escalation step tells the signers

Model: `gemini-4-argon`, thinking medium. Inputs: the saved comparison for each case (reports/compare/<id>.json). The decision was made by code before the model was asked; the model's reading of the gap is advisory. For ASK the text is: the kind of gap, a caution when the model judges that an honest proposer would not have written the description, then the question. For REJECT it is a statement of why; no question is asked.

| Case | Description | Verdict (code) | Gap kind (model) | Honest proposer? | What the signers see |
| --- | --- | --- | --- | --- | --- |
| demo_auditor | Pay our auditor 100 USDC | ASK | omission | unlikely | The description leaves out something the transaction does. Note: the gap between the words and the bytes is one a careful proposer would not normally leave. Check the answer independently before signing. In addition to paying 100 USDC, this transaction grants auditor (0x46F43A4Cb3c2cD27c36f07cfd691E8a22Dd60A4C) an unlimited allowance to spend the Safe's USDC. Did you intend to give auditor unlimited access to the Safe's USDC balance? |
| 09_routine_transfer_vague | Routine transfer | ASK | vague_description | unlikely | The description is too thin to check the transaction against. Note: the gap between the words and the bytes is one a careful proposer would not normally leave. Check the answer independently before signing. Did you intend for this routine transfer to send 1 ETH from the Safe to 0xE1D9a0eADCb8082d7989D7304061c017bE296C31? |
| 31_revoke_ravi_usdc | Revoke Ravi's USDC allowance | ASK | contradiction | no | The description says one thing and the transaction does another. Caution: the words and the bytes disagree in a way an honest proposer is unlikely to have written. Treat this proposal as suspect, and do not sign on the proposer's say-so alone. The description says this revokes Ravi's USDC allowance, but the transaction actually grants Ravi an unlimited USDC allowance. Did you intend to grant Ravi unlimited access to the Safe's USDC instead of setting the allowance to zero? |
| 32_pay_dana_wrong_wallet | Pay Dana 2,500 USDC for October | ASK | contradiction | no | The description says one thing and the transaction does another. Caution: the words and the bytes disagree in a way an honest proposer is unlikely to have written. Treat this proposal as suspect, and do not sign on the proposer's say-so alone. The description says this pays 2,500 USDC to Dana (0x4716b53aC6fd6AeFbb0E6a4687eAE260011bd315), but the transaction actually sends 2,500 USDC to the unrecognized address 0x97f8fD4720c6b29a0664cf3A8b3550bd1171c277. Did Dana change their payment address, or was the wrong recipient entered? |
| 33_pay_ravi_but_approve | Pay Ravi 2,500 USDC for October | ASK | contradiction | unlikely | The description says one thing and the transaction does another. Note: the gap between the words and the bytes is one a careful proposer would not normally leave. Check the answer independently before signing. This transaction approves Ravi (0x2C81904f370e7f6490aEa328CA847AEFdc3853D3) to spend up to 2,500 USDC from the Safe instead of transferring the 2,500 USDC directly. Did you intend to grant an allowance rather than send a direct payment? |
| 34_uniswap_output_diverted | Buy 1,000 USDC on Uniswap, spending at most 1 ETH | ASK | contradiction | no | The description says one thing and the transaction does another. Caution: the words and the bytes disagree in a way an honest proposer is unlikely to have written. Treat this proposal as suspect, and do not sign on the proposer's say-so alone. Why does this Uniswap swap send the 1,000 USDC proceeds to 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3 instead of the Safe? |
| 35_add_owner_then_lower_threshold | Add Ravi as a backup owner; keep approval at 2 signatures | REJECT | contradiction | no | This transaction was refused because it contradicts the description regarding the Safe's approval threshold. While it adds Ravi (0x2C81904f370e7f6490aEa328CA847AEFdc3853D3) as a fourth owner as promised, it also lowers the required signature threshold from 2 to 1 instead of keeping it at 2. Executing this would allow any single owner to unilaterally execute transactions from the Safe. |
| demo_bybit | Transfer 500 ETH to the warm wallet | REJECT | contradiction | no | This transaction was refused because it does not transfer 500 ETH to the warm wallet as described. Instead, it executes a delegatecall to an unverified contract (0x96221423681A6d52E184D440a8eFCEbB105C7242) that runs with the Safe's full permissions. This call overwrites the Safe's core singleton implementation address (slot 0) with 0xbdd077f651Ebe7f7b3cE16fE5F2B025be2969516, giving that contract complete control over the Safe and its funds. |

## demo_auditor (ASK)

The description leaves out something the transaction does. Note: the gap between the words and the bytes is one a careful proposer would not normally leave. Check the answer independently before signing. In addition to paying 100 USDC, this transaction grants auditor (0x46F43A4Cb3c2cD27c36f07cfd691E8a22Dd60A4C) an unlimited allowance to spend the Safe's USDC. Did you intend to give auditor unlimited access to the Safe's USDC balance?

What to check:
- Verify whether auditor (0x46F43A4Cb3c2cD27c36f07cfd691E8a22Dd60A4C) requires an ongoing token allowance in addition to the 100 USDC direct transfer.
- Inspect the batched calls in MultiSendCallOnly to see why an unlimited USDC approve call was included.
- Confirm with the proposer if the unlimited USDC approval was added by mistake.

<details><summary>reasoning</summary>

The proposer's description promises only a payment of 100 USDC from the Safe to the auditor. The trace shows that in addition to transferring 100 USDC to the auditor, the transaction also grants the auditor an unlimited USDC spending allowance from the Safe. Granting an unlimited token approval alongside a direct transfer is an unexplained omission that exposes all of the Safe's USDC to the auditor.

</details>

## 09_routine_transfer_vague (ASK)

The description is too thin to check the transaction against. Note: the gap between the words and the bytes is one a careful proposer would not normally leave. Check the answer independently before signing. Did you intend for this routine transfer to send 1 ETH from the Safe to 0xE1D9a0eADCb8082d7989D7304061c017bE296C31?

What to check:
- Verify that 0xE1D9a0eADCb8082d7989D7304061c017bE296C31 is the intended recipient.
- Confirm that 1 ETH is the correct amount and asset to transfer.

<details><summary>reasoning</summary>

The proposer described the transaction simply as 'Routine transfer', which provides no verifiable details about the asset, amount, or recipient. The execution trace shows a transfer of 1 ETH from the Safe to 0xE1D9a0eADCb8082d7989D7304061c017bE296C31.

</details>

## 31_revoke_ravi_usdc (ASK)

The description says one thing and the transaction does another. Caution: the words and the bytes disagree in a way an honest proposer is unlikely to have written. Treat this proposal as suspect, and do not sign on the proposer's say-so alone. The description says this revokes Ravi's USDC allowance, but the transaction actually grants Ravi an unlimited USDC allowance. Did you intend to grant Ravi unlimited access to the Safe's USDC instead of setting the allowance to zero?

What to check:
- Verify the allowance amount parameter in the USDC approve call (currently set to unlimited instead of 0).
- Confirm with the proposer whether Ravi (0x2C81904f370e7f6490aEa328CA847AEFdc3853D3) should have their USDC allowance revoked or set to unlimited.

<details><summary>reasoning</summary>

The proposer's description promises to revoke Ravi's USDC allowance (setting it to zero). However, the transaction trace shows that the Safe actually sets Ravi's USDC allowance to unlimited. This is a direct contradiction between the promised amount (zero) and the actual amount (unlimited).

</details>

## 32_pay_dana_wrong_wallet (ASK)

The description says one thing and the transaction does another. Caution: the words and the bytes disagree in a way an honest proposer is unlikely to have written. Treat this proposal as suspect, and do not sign on the proposer's say-so alone. The description says this pays 2,500 USDC to Dana (0x4716b53aC6fd6AeFbb0E6a4687eAE260011bd315), but the transaction actually sends 2,500 USDC to the unrecognized address 0x97f8fD4720c6b29a0664cf3A8b3550bd1171c277. Did Dana change their payment address, or was the wrong recipient entered?

What to check:
- Verify directly with Dana via a trusted communication channel whether 0x97f8fD4720c6b29a0664cf3A8b3550bd1171c277 is their intended receiving address.
- Check the October invoice or payment request from Dana to see which wallet address is listed.
- Compare the transaction recipient against the Safe's address book entry for Dana (0x4716b53aC6fd6AeFbb0E6a4687eAE260011bd315).

<details><summary>reasoning</summary>

The proposer's description promises to pay 2,500 USDC from the Safe to Dana (whose address in the address book is 0x4716b53aC6fd6AeFbb0E6a4687eAE260011bd315). However, the trace shows a transfer of 2,500 USDC from the Safe to an unrecognized address, 0x97f8fD4720c6b29a0664cf3A8b3550bd1171c277. Because the words promise one recipient and the transaction bytes send the funds to a different recipient, this is a contradiction.

</details>

## 33_pay_ravi_but_approve (ASK)

The description says one thing and the transaction does another. Note: the gap between the words and the bytes is one a careful proposer would not normally leave. Check the answer independently before signing. This transaction approves Ravi (0x2C81904f370e7f6490aEa328CA847AEFdc3853D3) to spend up to 2,500 USDC from the Safe instead of transferring the 2,500 USDC directly. Did you intend to grant an allowance rather than send a direct payment?

What to check:
- Confirm with the proposer whether Ravi should receive a direct transfer of 2,500 USDC or an ERC-20 spending allowance.
- Verify that Ravi's address (0x2C81904f370e7f6490aEa328CA847AEFdc3853D3) is the intended recipient or spender.
- Check if a direct `transfer` call should be queued instead of `approve` so Ravi does not have to pull the funds manually.

<details><summary>reasoning</summary>

The proposer's description promises a direct payment ('Pay Ravi 2,500 USDC for October'), which corresponds to a token transfer of 2,500 USDC from the Safe to Ravi. However, the transaction trace shows no transfer; instead, it sets an ERC-20 allowance permitting Ravi to spend up to 2,500 USDC (2,500,000,000 base units) from the Safe. Per the definition, an approval where a payment was promised is a contradiction.

</details>

## 34_uniswap_output_diverted (ASK)

The description says one thing and the transaction does another. Caution: the words and the bytes disagree in a way an honest proposer is unlikely to have written. Treat this proposal as suspect, and do not sign on the proposer's say-so alone. Why does this Uniswap swap send the 1,000 USDC proceeds to 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3 instead of the Safe?

What to check:
- Verify who owns or controls the recipient address 0x2C81904f370e7f6490aEa328CA847AEFdc3853D3.
- Confirm whether the 1,000 USDC was intended to be received by the Safe (0x5afe5afE5afE5afE5afE5aFe5aFe5Afe5Afe5AfE) or sent directly to a third party.
- Check the `to` parameter in the Uniswap router call data.

<details><summary>reasoning</summary>

The description promises to buy 1,000 USDC on Uniswap for the Safe, spending at most 1 ETH. While the ETH expenditure matches (spending ~0.3546 ETH via Uniswap), the trace shows that the 1,000 USDC output from the Uniswap V2 pair (0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc) is sent to an external address (0x2C81904f370e7f6490aEa328CA847AEFdc3853D3) rather than returning to the Safe.

</details>

## 35_add_owner_then_lower_threshold (REJECT)

This transaction was refused because it contradicts the description regarding the Safe's approval threshold. While it adds Ravi (0x2C81904f370e7f6490aEa328CA847AEFdc3853D3) as a fourth owner as promised, it also lowers the required signature threshold from 2 to 1 instead of keeping it at 2. Executing this would allow any single owner to unilaterally execute transactions from the Safe.

What to check:
- Inspect the batched calls in MultiSendCallOnly v1.4.1 (0x9641d764fc13c8B624c04430C7356C1C7C8102e2) for an extra changeThreshold(1) call.
- Verify that a new transaction to add Ravi (0x2C81904f370e7f6490aEa328CA847AEFdc3853D3) only calls addOwnerWithThreshold with a threshold of 2.
- Confirm with the proposer why a threshold reduction to 1 was bundled into the transaction.

<details><summary>reasoning</summary>

The proposer's description promises to add Ravi (0x2C81904f370e7f6490aEa328CA847AEFdc3853D3) as an owner and keep the signature threshold at 2. While the transaction does add Ravi and initially sets the threshold to 2, it also executes an additional step that lowers the Safe's signature threshold from 2 to 1. This directly contradicts the explicit promise to keep the threshold at 2.

</details>

## demo_bybit (REJECT)

This transaction was refused because it does not transfer 500 ETH to the warm wallet as described. Instead, it executes a delegatecall to an unverified contract (0x96221423681A6d52E184D440a8eFCEbB105C7242) that runs with the Safe's full permissions. This call overwrites the Safe's core singleton implementation address (slot 0) with 0xbdd077f651Ebe7f7b3cE16fE5F2B025be2969516, giving that contract complete control over the Safe and its funds.

What to check:
- Verify the identity and security of the proposer account or device that submitted this transaction.
- Inspect the target address (0x96221423681A6d52E184D440a8eFCEbB105C7242) and operation type (delegatecall) in the raw transaction payload.
- Check the newly proposed singleton address (0xbdd077f651Ebe7f7b3cE16fE5F2B025be2969516) that would replace the Safe's implementation.
- Review other pending or recently queued transactions on the Safe for unauthorized delegatecalls or storage modifications.

<details><summary>reasoning</summary>

The proposer's description promises a simple transfer of 500 ETH to the warm wallet (0x5EdeB15618d4A94EBFC4DfEBBe49748982731B07). In reality, the trace shows no ETH transfer at all. Instead, the transaction executes a delegatecall to an unverified contract (0x96221423681A6d52E184D440a8eFCEbB105C7242), which overwrites the Safe's singleton implementation address in slot 0 from 0x41675C099F32341bf84BFc5382aF534df5C7461a to 0xbdd077f651Ebe7f7b3cE16fE5F2B025be2969516.

</details>
