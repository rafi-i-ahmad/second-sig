# Naive judge baseline

One `gemini-4-argon` call, thinking high, that sees everything at once: the decoded
transaction and call tree, balance and storage changes, the verified source of every contract
in the call tree, and the proposer's description, last and spotlit. Code:
`judge/stages/judge.py`. It is the row the layered judge is measured against, and it never
feeds the stamp path.

## First run, 23 October 2026

| Case | Expected | Got | Tokens | Latency | Reasoning (first 100 chars) |
| --- | --- | --- | --- | --- | --- |
| 01 send 5 ETH | MATCH | **MATCH** | 24,068 | 25.2 s | The proposer's description states 'Send 5 ETH to the ops wallet'. In the call tree, the Safe (`0xDFE |
| auditor | ASK | **REJECT** | 78,844 | 46.5 s | The proposer's description states only "Pay our auditor 100 USDC". In `[c0]` and `[c0.0]`, the Safe |
| Bybit | REJECT | **REJECT** | 24,499 | 50.8 s | The proposer's description states that this transaction will "Transfer 500 ETH to the warm wallet" ( |

Two of three cases came back as expected. Every output validated on the first attempt. Full
verdicts and interaction ids are in `fixtures/outputs/<id>.naive.json`. The traces it judged are in
`fixtures/traces/` and the cached sources in `fixtures/sources/`.

- **Bybit:** it found all three problems: no ETH reaches the warm wallet, an unverified
  delegatecall at `[c0.0.2]`, and slot 0 overwritten, which it identified as the singleton
  (`Singleton.sol:12`) and called a hijack of the Safe.
- **Auditor:** the reading is right. It licensed the 100 USDC transfer, then found the
  `approve` at `[c0.0.2.1]` setting `allowed[Safe][auditor]` to `type(uint256).max` in slot
  `0xc0ad…13bb` (`FiatTokenV1.sol:238`, `:245`). It judged that the auditor could drain the
  remaining 9,900 USDC and chose REJECT, where the fixture expects ASK.

Known issue in this run: Etherscan marks `FiatTokenV2_2` (`0x4350…02dd`) as a proxy whose
"implementation" is its linked library `SignatureChecker` (`0x800c…b172`), so the auditor
prompt also carried that library's source, which never runs in the trace. Fix:
`sources.load_with_impl` should follow `Implementation` only when the trace shows a DELEGATECALL
to it. Left unfixed so this run's prompts stay reproducible.

## Why it rejects where we expected it to ask: hypotheses

One sample on one case, so these are guesses to test, not findings.

1. **The task wording licenses REJECT.** The prompt calls "any permission that outlives the
   transaction" a discrepancy, and sends a discrepancy to REJECT when the harm is
   "irreversible or control-changing". An unlimited allowance gives the spender lasting
   control over the Safe's USDC, which fits "control-changing" read literally. The model
   followed the rubric; the rubric does not say where ASK ends.
2. **ASK has no positive test.** REJECT and MATCH each have a stated condition; ASK is
   whatever falls between them ("a discrepancy a human should confirm"). Every discrepancy is
   one a human could confirm, so nothing tells the model when a case belongs in ASK rather
   than REJECT. Given a serious discrepancy, the stricter branch with an explicit trigger wins.
3. **The framing is one-sided.** "You are the final signer" and "the owners have already
   signed based on the description" cast the model as the last line of defence. The prompt
   names the cost of a wrong MATCH and never the cost of a wrong REJECT: a blocked payment,
   a confused treasurer, a human who learns to override.
4. **Reversibility is not explained.** An allowance can be revoked before it is used, and the
   spender is a named counterparty in the owners' own address book. The prompt does not say
   that address-book entries are known parties, or that revocable-but-dangerous sits closer to
   ASK than to REJECT. The model reasoned from the worst case (the spender drains it
   immediately), which makes the harm irreversible.
5. **High thinking pushes towards the worst case.** Long reasoning on a security task tends to
   follow attack paths to their end. A single sample with no majority vote (the CLAUDE.md
   Gemini notes call for three samples on enum fields) can land on the strict side by chance.
6. **The expected label is a policy choice.** The guard treats any ERC-20 `approve` as risky,
   and a reasonable signer could reject an unlimited approval hidden in a payment. ASK
   encodes "a human decides". The naive judge has no way to tell that this is our policy
   rather than a fact about the transaction. That is part of what the layered judge's
   decision table (`verdict.py`) is for.

## What would test them

- Three samples per case, to see whether the REJECT is stable (hypothesis 5).
- The same case with the REJECT condition narrowed to "transfers control of the Safe itself or
  moves funds the description does not mention", and a positive test for ASK such as "a
  permission or effect a known party could plausibly have intended" (hypotheses 1, 2, 4).
- A variant where the approval goes to an address outside the address book, which should stay
  REJECT under any wording; if it drops to ASK, the change went too far.

Do not tune the baseline prompt to the answer key. If the wording changes, record it here as a
new run with its own table.
