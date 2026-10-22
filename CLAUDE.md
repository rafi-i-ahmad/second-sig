# Second Sig

An extra signer for Safe multisigs. It rehearses a proposed transaction on a fork, compares what the bytes actually do with what the description says, and signs a stamp only on a match. A guard contract on the Safe refuses risky transactions without a valid stamp.

Hackathon build: two people, about 2.5 days, Encode London. The full spec is the "Second Sig: build spec" doc. This file holds what an agent working in the repo must not get wrong.

## Who owns what

- `judge/` (except `judge/evidence/fork.py`, `trace.py`, `decode.py`, `slots.py`), `cli/view.py`, `eval/`: Rafi (AI side).
- `contracts/`, `judge/evidence/fork.py`, `trace.py`, `decode.py`, `slots.py`, `sepolia/`: the chain lead.
- The two halves meet only at `judge/schemas.py` (`EvidenceBundle`, `Stamp`). Do not change either schema without both people agreeing. If a change seems necessary, stop and say so.

## Layout

```
contracts/            Foundry project
  src/SecondSigGuard.sol
  test/               Foundry tests (guard, stamp, override, bricking)
  script/             deploy and setGuard scripts
judge/
  schemas.py          pydantic models: EvidenceBundle, ExpectedEffects, Narration,
                      Classification, ProbeHypothesis, HumanQuestion, Verdict, Stamp
  evidence/           layer 1: fork.py, trace.py, decode.py, slots.py, rules.py
  labeller.py         layer 2: spotlighting, random delimiters
  model.py            Gemini Interactions API adapter; logs every call
  jobs/               layer 3: forward.py, backward.py, leftovers.py, probe.py, escalate.py
  checker.py          layer 4
  verdict.py          layer 5: decision table
  stamp.py            EIP-712 signing with the judge key
cli/
  secondsig.py        propose, judge, sign, execute, override, describe, demo, eval
  view.py             three-panel terminal view (rich)
sepolia/
  watcher.py          polls the Safe Transaction Service, judges pending proposals
  attacker.py         proposes the Bybit-shaped transaction to our own test Safe
fixtures/             bybit/, aave/, transfer/, tornado/, injection/
eval/run.py           the eval table
logs/                 calls.jsonl, verdicts.jsonl (used by --replay)
```

## Commands

```
uv sync
uv run pytest
cd contracts && forge build && forge test -vv

# fork for the mainnet scenarios (Bybit block); load a dump if offline
anvil --fork-url $MAINNET_RPC --fork-block-number 21895238 --steps-tracing
anvil --load-state fixtures/anvil-state.json

uv run secondsig demo bybit      # also: aave, probe
uv run secondsig judge <safeTxHash>
uv run secondsig eval --table
uv run secondsig demo bybit --replay   # rebuild verdicts from logs/, no model call
```

Secrets live in `.env` only: `GEMINI_API_KEY`, `MAINNET_RPC`, `SEPOLIA_RPC`, `ETHERSCAN_API_KEY`, `SAFE_API_KEY`, `JUDGE_PRIVATE_KEY`, test owner keys. Never print, log or commit any of them.

## Invariants: never break these

The safety argument rests on these. If a task seems to require breaking one, stop and ask.

1. The model never decides. The verdict is a pure function in `verdict.py` of the evidence bundle plus checked model forms.
2. Any hard-rule hit forces REJECT, whatever any model output says.
3. The model never sees or touches a key, and has no tool that writes, signs or sends. Tools available to model calls are read-only and run on throwaway fork snapshots.
4. The model proposes probes; code runs them and records the results. A probe can raise a slot's suspicion, never lower it. Only the compiler storage layout can lower it.
5. The forward pass never sees the trace. The backward pass never sees the description. Keep them in separate calls with separate inputs.
6. Every claim in a model form cites a trace entry (or source line). `checker.py` drops any claim whose citation does not resolve, and the item becomes ASK.
7. Everything an attacker could author is untrusted text: the description, on-chain strings, revert reasons, token and contract names, comments and identifiers in verified source. It reaches the model only through `labeller.py`, wrapped in per-call random delimiters. Never put it in a system instruction.
8. Attack and injection examples live in `fixtures/` and the eval set only. Never paste them into runtime prompts.
9. The stamp binds `safeTxHash`, `forkBlock` and `judgeVersion`. The guard checks all three. Do not let the guard accept anything the judge did not hash.
10. The override stays slow: more approvals than the Safe's threshold, plus a delay. `setGuard(address(0))` is a risky call and needs a stamp or an override.
11. Never fake a live call in the demo. If the model is unavailable, use `--replay` and say so.

## Stamp format (EIP-712)

```
domain: { name: "SecondSig", version: "1", chainId, verifyingContract: <guard address> }
Stamp:  { bytes32 safeTxHash, uint64 forkBlock, bytes32 judgeVersion }
```

`attest(stamp, sig)` is callable by anyone; the guard recovers the signer and compares it with the judge address. Stamps older than `MAX_STAMP_AGE` blocks are rejected.

## Safe gotchas

- Guards exist from Safe 1.3.0. Inherit the base guard from the safe-smart-account tag that matches the deployed Safe, so `setGuard`'s interface check passes.
- The Safe increments its nonce before calling `checkTransaction`. Recompute the hash with `getTransactionHash(..., nonce() - 1)`.
- Safe batches via delegatecall to MultiSendCallOnly. The rule is "delegatecall to anything not on the allowlist", not "any delegatecall".
- Risky in the guard: any delegatecall; any call to the Safe itself; any ERC-20 `approve`; non-allowlisted target above the value threshold; nonzero `gasPrice` with a refund receiver or gas token set.
- Bybit's real Safe was v1.1.1 (no guard support). The judge can run on the real transaction at block 21,895,238; the guard demo replays the attack shape against our own 1.3.0+ Safe.
- A broken guard can freeze a Safe. Every guard change gets the Foundry bricking tests (`test/Bricking.t.sol`) before it goes to Sepolia.

## Gemini notes (checked 17 October; confirm at the Friday workshop)

- Interactions API via `google-genai`. Models: `gemini-4-argon`, `gemini-3.8-flash` (ablation row only).
- `thinking_level` is low, medium or high. `temperature` is ignored on Argon: determinism comes from logging every interaction id, replaying from `logs/`, and three-sample majority votes on enum fields.
- Resend `tools`, `system_instruction` and `generation_config` on every turn, including function-result turns.
- Run any tool loop first, then make a separate call with `response_format` for the typed output, until we confirm the two can be combined.
- Every call goes through `judge/model.py`, which writes one line to `logs/calls.jsonl`: interaction id, prompt hash, model, thinking level, parsed output, validation errors, latency.

## Conventions

- `main` is always demoable. Work on branches; merge at gates.
- Python: type hints, pydantic for every model output, no bare dicts crossing module boundaries.
- Solidity: custom errors, named `SecondSig__...`; events for every attest, override approval and override execution.
- Prefer deleting scope over adding cleverness. The cut list in the spec says what goes first.
- When unsure whether something weakens an invariant, ask rather than guess.
