# Live loop, case 46: what happened and what to improve

24 October 2026, ~14:04, personal Gemini key (the hackathon key was refusing Argon all afternoon).
Command: `uv run secondsig judge fixtures/cases/ask/46_up_to_ceiling_unlimited_allowance.json --chain`.
No recorded forms were used; every model call below was live.

## The case

**Words:** "Use up to 1,000 USDC on Uniswap to buy at least 0.000001 WETH for the Safe."
**Bytes:** `USDC.approve(router, uint256 max)` then `swapExactTokensForTokens(1,000 USDC, min 0.000001 WETH, [USDC, WETH], Safe)`.
**Expected:** ASK. The swap matches the words; the unlimited standing allowance does not.

## What ran

| Step | Who | Time | Result |
| --- | --- | --- | --- |
| Rehearse | anvil fork, snapshot, revert | ~3 s | `ExecutionSuccess`; 9 storage writes, 4 balance changes, 6 events |
| Hard floor | code | 0 | no hits (correct: a swap is not an attack shape) |
| Forward | `gemini-3.8-flash`, low | 20 s | 1,000 USDC Safe → Uniswap; 0.000001 WETH Uniswap → Safe; allowance 1,000 USDC to Uniswap |
| Backward | `gemini-3.8-flash`, low | 24 s (13 s wasted on one schema retry) | 1,000 USDC Safe → pair; 0.3524 WETH pair → Safe; **unlimited** allowance to Uniswap; pair reserve writes as `info`; nonce as `info` |
| Code layouts | `judge/layouts.py` | 0 | pair slots 8–10 and the WETH balance labelled; the "reserves and oracle" info effect is explained without any source call |
| Source reader | — | — | not needed: nothing left unlabelled |
| Compare | code | 0 | USDC leg matched `counterparty_via_callee`; WETH leg matched `inbound_from_callee`; allowance **unlimited vs 1,000 unexplained** (notable); two expected items unobserved (see below) |
| Verdict | code | 0 | **ASK** |
| Escalate | `gemini-4-argon`, medium | 14 s | "This transaction grants Uniswap an unlimited USDC allowance instead of limiting the approval to the 1,000 USDC being swapped. Did you intend to leave an unlimited USDC approval active on Uniswap?" |
| Chain | fork | ~2 s | no stamp; `execTransaction` with owners 0 and 1 reverted: `SecondSig__NoStamp` |

Total wall time about 65 s, of which 58 s was model latency. Three model calls, 3 interaction ids
logged. The verdict and the question are the ones the case was written for.

## What worked

- Both passes read the transaction correctly and independently; the backward pass found the
  unlimited allowance and named the router by its address-book name.
- The two tolerances did their job: USDC landing in the pair (not the router the words name)
  and WETH arriving from the pair were both explained *because* they happened inside the Safe's
  call into the router, derived from the call tree, not from any model's say-so.
- The code layouts explained the pair's reserve and oracle writes, so no Argon source call was
  needed; the earlier tightening (unlabelled writes are questions) cost nothing here.
- The escalation question is specific, names the counterparty and the amounts, and asks about
  the gap rather than the parts that match.
- The guard refused two valid owner signatures because no stamp existed. The chain did what the
  judge said.

## Improvements this run points at

Ordered by how much they matter, with where the fix goes.

1. **"At least" is a floor, not an exact amount** (`judge/canon.py`, `compare.py`). The forward pass
   wrote "0.000001 WETH" for "at least 0.000001 WETH"; canon read it as exact; the real 0.3524 WETH
   did not match it and was instead explained by `inbound_from_callee`, leaving the promise listed
   as "not seen". Mirror of today's "at most" ceiling: `amount_min_base`, match if observed ≥ min.
   On this case the verdict was unaffected (the allowance alone is ASK); on a clean "buy at least X"
   swap it would be a false ASK. *Half an hour.*

2. **Qualifiers must survive the forward pass** (`judge/jobs/forward.py` SYSTEM). The forward form
   dropped "up to" from "up to 1,000 USDC" (the words were a ceiling; the form said 1,000). Canon's
   bound detection reads the form's `amount_human`, so the qualifier has to be kept there. Add one
   sentence: "Copy qualifiers into amount_human: 'up to 1,000 USDC', 'at least 0.5 ETH', 'about 2
   ETH'." *Five minutes; re-record forms.*

3. **Backward schema retry on `permission_changes[].kind`** (`judge/schemas.py` or `backward.py`
   SYSTEM). Flash's first attempt put something other than `erc20_approval` in `kind` and was
   retried (13 s). The same error appeared this morning. Either tell the model the only allowed
   value in the system prompt, or take `kind` out of the model-facing schema and set it in code.
   *Ten minutes; saves a retry per run.*

4. **A matched leg should consume its promise even when the bound mismatches.** Related to (1):
   the WETH leg was explained (inbound tolerance) while the forward's WETH promise stayed in
   `expected_unobserved`. With (1) fixed this resolves itself; if any bound-shaped mismatch remains,
   compare should prefer "matched with a bound note" over "unobserved + separately explained".

5. **Escalation call was not listed under "model calls"** (`judge/pipeline.py`). The result had
   copied the list before the append. Fixed in this commit.

6. **Raw addresses in the view** (`cli/view.py`, `canon.render_party`). The pair appears as
   `0xB4e16d01…` five times. Identity must stay the address, but display may use the verified
   contract name: `0xB4e1…C9Dc (UniswapV2Pair)`. Display only; never for matching. *Fifteen minutes.*

7. **Latency.** 58 s of model time is fine for the demo if the UI shows the three cards filling in
   as calls return; a blank screen for a minute is not. Stream or at least spinner per pass. The
   demo should still default to `--replay`.

8. **A design question, not a bug.** An unlimited approval to a canonical router is common
   practice in DeFi and the words said "up to 1,000 USDC". Today that is ASK, and the question is
   good. If the team wants it to pass, the rule would be "unlimited allowance to a contract on an
   allowlist of canonical routers, when the words license a swap", recorded as a tolerance tier.
   My view: keep ASK. The signer should see a standing unlimited approval once.

## Still to record

With the key working: the recorded classification for Aave (`demo_aave.leftovers.json`, the
~98k-token Argon source call), then forms for cases 37–51 (`scripts/compare_benign.py --live
--include-reject`) and the eval table. The hackathon key's Argon 429s (~91 s each, even on a one-word
call) are a billing-account problem on Google's side, not a rate limit we can engineer around.
