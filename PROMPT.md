Read CLAUDE.md and judge/schemas.py. I’m building test cases for the forward pass, which reads only a human description of a Safe proposal and must predict what the transaction will do. I’m not a crypto expert, so explain each step in one plain sentence as you go.

Write fixtures/build.py. It defines cases in plain Python and writes one JSON file per case to fixtures/cases/. Each case has: id, description (the human sentence a treasurer would write), safe_tx (to, value, data, operation), address_book (name to address for every address the description refers to), and intent (the ground truth I’ll check the forward pass against: a list of movements {asset, amount_human, from_name, to_name}, permission_changes, safe_config_changes, nothing_else). Build data by encoding the function call with eth_abi or cast calldata; for batched cases, pack the inner calls in MultiSendCallOnly’s format (one byte operation, 20-byte address, 32-byte value, 32-byte data length, data, concatenated) and wrap in multiSend(bytes). Use the Safe placeholder 0xSAFE… to be replaced once the fork exists; use real mainnet addresses for USDC, the Aave v3 Pool and MultiSendCallOnly v1.4.1, each with an Etherscan link in a comment, and invented addresses for people.

Ten cases, none of them the demo scenarios (no Bybit replay, no Aave deposit, no auditor payment):

“Send 5 ETH to the ops wallet”
“Pay Dana 2,500 USDC for October”
“Move 20 ETH and 10,000 USDC to the hot wallet”, one batch
“Add Priya as a signer”, addOwnerWithThreshold(priya, 2)
“Raise the signing threshold to 3 of 4”, changeThreshold(3)
“Approve the Uniswap router to spend 1,000 USDC for next week’s swap”, a finite approval
“Pay three contractors their invoices”, three USDC transfers in one batch
“Refund Sam the 0.5 ETH he overpaid”
“Routine transfer”, a 1 ETH transfer: deliberately vague, ground truth is a question
“Swap 5,000 USDC for ETH on Uniswap”, approve plus a swapExactTokensForETH call in one batch

Also build the three demo scenarios as separate files in fixtures/demo/, not fixtures/cases/, so the forward-pass tests and any few-shot examples never read them: bybit (delegatecall, operation = 1, to = 0x96221423681A6d52E184D440a8eFCEbB105C7242, data = transfer(0xbDd077f651EBe7f7b3cE16fe5F2b025BE2969516, 0), description “Transfer 500 ETH to the warm wallet”), aave (batch of USDC.approve(Pool, 10,000e6) then Pool.supply(USDC, 10,000e6, SAFE, 0), description “Deposit 10,000 USDC into Aave v3”), and auditor (batch of USDC.transfer(auditor, 100e6) then USDC.approve(auditor, type(uint256).max), description “Pay our auditor 100 USDC”). Give each the same JSON shape plus an expected_verdict field: REJECT, MATCH, ASK.

Then write tests/test_forward_cases.py that runs judge/stages/forward.py on every case and compares the output to intent: same set of movements (asset, amount, from, to), same permission and config changes, nothing_else agreeing, and for case 9 at least one questions_for_human. (Check with me before this) Print a one-line pass/fail per case with latency, and save each model output next to its case as <id>.forward.json so I can read them. Use gemini-3.8-flash, thinking="low". Mark the test live.

Don’t run anything that calls Gemini until I’ve seen the cases. Show me fixtures/cases/ first.