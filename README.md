# Second Sig

An extra signer for Safe multisigs that humans can't give. It rehearses a proposed transaction on a fork of Ethereum, compares what the bytes actually do with what the description says, and signs an EIP-712 stamp only on a match. A guard contract on the Safe refuses every transaction that has no valid stamp for its exact hash, however many owners signed it.

Built in two and a half days at Encode London, October 2026, for the Gemini 4 Argon challenge and Agents That Ship. Demo video: *(link goes here before submission)*.

## The problem

A Safe owner approving a transaction sees a hex blob, maybe a decoded function name, and a description written by whoever proposed it. In practice owners trust the description and the wallet UI. In February 2025 Bybit's signers approved what their screen showed them, a routine transfer. The bytes they signed replaced the Safe's master code with the attackers' and about $1.4 billion left. Every signature was genuine. Nothing on chain checked that the transaction matched what the signers thought they were approving.

## What it does

1. **Rehearses** the exact bytes on a snapshot of a mainnet fork, through the real Safe contract with the owners' signatures, and records every call, storage write, balance change and event.
2. **Rejects attack shapes in code** before any model runs: a delegatecall to anything but the Safe batching contract, a write to the Safe's singleton, guard, fallback-handler or module slots, a call into unverified code, a gas-refund drain.
3. **Reads the words and the bytes separately.** One Gemini call sees only the description and says what it promises. Another sees only the rehearsal and says what happened. Neither sees the other's input, so the description cannot steer what the bytes are reported to do.
4. **Explains unlabelled storage from source.** Writes no known layout labels are treated as suspicious. Gemini 4 Argon reads the verified source of the touched contracts and claims what each write is; code recomputes the slot from the claim and accepts it only if it reproduces.
5. **Reconciles in code** and produces MATCH, ASK or REJECT from a fixed decision table. The model never decides.
6. **Asks a human when it is unsure.** On ASK, Argon drafts one question for the signers. An owner's answer amends the description and the judge re-runs on the same bytes.
7. **Signs a stamp on MATCH** with a key no model ever touches, and the guard on the Safe lets the transaction through. On anything else the Safe reverts.

## The three demos

All three run against a real Safe v1.4.1 on an anvil fork pinned at the Bybit attack block, with two of three owners' signatures already attached.

| Command | Described as | Actually does | Verdict | On chain |
| --- | --- | --- | --- | --- |
| `secondsig demo bybit` | Transfer 500 ETH to the warm wallet | delegatecall into the Bybit attackers' contract, overwriting the Safe's master-code slot | REJECT by the hard floor, before any model | guard reverts `SecondSig__NoStamp` with two valid signatures |
| `secondsig demo aave` | Deposit 10,000 USDC into Aave v3 | approve and `Pool.supply`, eight storage writes no layout labels | MATCH once Argon's source reading is corroborated by code | stamp signed, attested, executed; the Safe holds aUSDC |
| `secondsig demo auditor` | Pay our auditor 100 USDC | the transfer, plus an unlimited USDC approval to the auditor | ASK with one question | reverts; an owner's answer re-runs the judge and it executes |

Beyond the demos there is a 33-case eval set under `fixtures/cases/`: honest proposals, vague ones, descriptions that contradict the bytes, and prompt injections in the description, an address-book label, a contract label and a forged rehearsal tag.

## Setup

You need Python 3.12 with [uv](https://docs.astral.sh/uv/), [Foundry](https://getfoundry.sh/) (`anvil`, `forge`, `cast`), and three keys: a Gemini API key, a mainnet RPC that serves archive state at block 21,895,238, and an Etherscan API key. The Foundry libraries are git submodules.

```sh
git clone --recurse-submodules <repo url> second-sig
cd second-sig
uv sync
cp .env.example .env            # fill in GEMINI_API_KEY, MAINNET_RPC, ETHERSCAN_API_KEY
cast wallet new                 # a judge key for your fork; put it in .env as
                                # JUDGE_PRIVATE_KEY and JUDGE_ADDRESS
(cd contracts && forge build)
uv run pytest                   # offline tests; live and fork tests skip
```

Start the fork in one terminal and leave it running:

```sh
anvil --fork-url $MAINNET_RPC --fork-block-number 21895238 --steps-tracing --port 8545
```

In another, deploy the test Safe and the guard, then run the demos:

```sh
uv run python contracts/setup.py --guard   # creates the 2-of-3 Safe through Safe's factory, funds it,
                                           # deploys SecondSigGuard and installs it with setGuard
uv run secondsig demo bybit
uv run secondsig demo aave
uv run secondsig demo auditor
uv run secondsig answer fixtures/cases/demo/demo_auditor.json \
    "Yes, grant the auditor an unlimited USDC allowance for monthly invoicing." --owner 1 --chain
uv run secondsig reset                     # rewind the fork, rebuild Safe and guard
```

The demos replay recorded model forms by default and make no model call; add `--live` to call Gemini. An owner's answer always makes one live call, because the amended words have no recorded form. A MATCH that executes advances the Safe's nonce, so run `secondsig reset` between full runs.

Other entry points:

```sh
uv run secondsig judge fixtures/cases/match/01_send_eth_ops.json [--replay] [--chain]
uv run python -m judge.evidence.fork fixtures/cases/ask/09_routine_transfer_vague.json   # rehearse, write the bundle
uv run python -m judge.verdict fixtures/bundles/demo_bybit.bundle.json                   # decision table on a saved bundle
uv run python scripts/compare_benign.py [--live] [--include-reject]                      # every case, verdicts + reports
uv run pytest tests/test_stamp.py --fork -s                                              # stamp round trip through the guard
cd contracts && forge test -vv
```

## Models and agents used

Every call goes through the Interactions API via `google-genai`, with `response_format` set to a pydantic schema. No model has tools. Every call is logged with its interaction id, so any verdict can be rebuilt from the log without a model call.

| Where | Model | Thinking | Sees | Returns |
| --- | --- | --- | --- | --- |
| Forward pass | `gemini-3.8-flash` | low | the description and the address book | what the words promise |
| Backward pass | `gemini-3.8-flash` | low | the rehearsal, without the description | what the bytes did, with evidence citations |
| Source reader | `gemini-4-argon` | high | unlabelled storage writes and the verified source of the contracts that wrote them, about 100k tokens for Aave | per write: variable, base slot, key, offset, source lines. Accepted only when code recomputes the slot |
| Escalation | `gemini-4-argon` | medium | the saved comparison | the signer's question, or the statement of why it was refused. Advisory only |
| Naive baseline | `gemini-4-argon` | high | trace, source and description together | a verdict. Eval only; the row the layered judge is measured against |
| `scripts/investigate.py` | Antigravity agent with read-only tools | | a bundle and its residuals | a write-up. Developer aid, never on the stamp path |

## The agent: tools, steps, approvals

**Tools it uses.** An anvil fork (snapshot, impersonated owners, `debug_traceTransaction`, storage reads), Etherscan verified source and ABIs, the Gemini Interactions API, an EIP-712 signer, and the Safe and guard contracts.

**Steps, in fixed order.** Rehearse, hard floor, forward and backward passes in parallel, source check, citation check, canonical form, compare, decide, escalate, then on MATCH only: sign, attest, execute.

**Where a human approves.**

- Owners sign the Safe transaction as they always did. The judge adds a requirement and never removes one.
- On ASK the judge stops. Only an owner can answer, the answer is attributed and recorded, and it re-runs the judge rather than overriding it.
- If the judge is wrong or offline, every owner (more than the Safe's threshold) approves an override on the guard directly, and it executes after a delay.
- Removing the guard is itself a guarded transaction.

**Where it stops and why.** Any hard-rule hit is REJECT whatever any model says. A failed rehearsal, a missing or invalid model form, an unexplained storage write, an uncited claim, a model error or a rate limit all end in ASK, never MATCH.

**The record.** `logs/calls.jsonl` holds every model call: interaction id, prompt hash, model, thinking level, latency, parsed output, validation errors. `logs/proposals/` holds every proposal with its amendments and the forms they produced. `fixtures/outputs/` holds the recorded forms used for replay. `reports/compare/` holds a per-case report of what each pass said against the ground truth.

## The safety argument, in plain words

- **The model never decides.** The verdict is a pure function of the evidence and the checked forms.
- **Some patterns always get rejected,** whatever any model says.
- **The model never sees a key** and has no tool that writes, signs or sends.
- **Suspicion can go up on a model's say-so, never down.** Only a code layout or a source claim that code has recomputed can label a storage write.
- **The two passes never share an input.** The words can't steer the reading of the bytes.
- **Every claim cites evidence.** A citation that does not resolve is marked and can explain nothing.
- **Everything an attacker could author is untrusted text** and reaches a model only inside per-call random delimiters, never in a system instruction.
- **The stamp binds the transaction hash, the fork block and the judge version.** The guard checks all three, expires stamps after 100 blocks, and rejects malleable signatures.
- **The override is slow:** every owner, plus a delay.

## Repository layout

```
contracts/     SecondSigGuard.sol, Foundry tests (guard, stamp, override, bricking), setup.py for the fork
judge/         the judge: evidence/ (rehearsal, traces, decoding, slot labels, hard floor), jobs/ (forward,
               backward, escalate, leftovers), checker, canon, compare, corroborate, verdict, stamp, pipeline
cli/           secondsig commands and the three-panel terminal view
fixtures/      cases (generated by build.py), rehearsed bundles, recorded model outputs, Etherscan cache
tests/         pytest; --live calls Gemini, --fork needs anvil
scripts/       compare_benign.py (the replay report), investigate.py (the developer agent)
reports/       per-case comparison reports and findings
eval/          the naive-baseline write-up
```

`CLAUDE.md` holds the invariants and the map of the repo. `NOTES.md` holds the fork's operational state. `build-spec-v2.md`, `demo-and-pitch.md` and `ui-spec.md` describe the system as built; `product-overview.md` describes it as a product.

## Limits

- Safe v1.3.0 or later; older Safes cannot install guards. Bybit's was v1.1.1, so the demo replays the attack shape against our own v1.4.1 Safe.
- Safe v1.4.1 does not run guards on module transactions, which is why enabling a module is a hard-floor rule.
- A rehearsal cannot predict state that changes before execution. The stamp is short-lived for that reason.
- A description that contradicts the bytes without touching a critical slot comes out ASK today, not REJECT. Whether that should change is an open design question, recorded in `reports/compare/FINDINGS.md`.
- One judge key. Several independent judges with k-of-n stamps is the obvious next step.
- The model can be wrong on subtle cases. The floor is why that cannot cost the Safe its code or its owners.
