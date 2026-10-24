# Second Sig: build spec, as built

24 October 2026 · Rafi and Daniel

This replaces the 22 October plan. It describes the repo as it is on the evening of 24 October, not what we hoped to build. Where this file and the code disagree, the code and `CLAUDE.md` win; `NOTES.md` holds the live state of the fork and the list of what is left. The file keeps its old name so links in `CLAUDE.md` and the memory notes still work.

**What changed since v2, in one paragraph.** There is no web UI and no HTTP API; the product is a CLI with a three-panel terminal view. There is no "full-context Argon judge" that returns a verdict: the model never decides. Two blind Flash passes fill typed forms, code reconciles them and a fixed decision table produces the verdict. Argon is used in two places only, both advisory or code-checked: it writes the signer's question or the rejection statement, and it reads verified contract source to explain storage writes that no code layout labels, accepted only when code recomputes the slot from its claim. The one-call Argon judge still exists as the eval baseline the layered judge is measured against, and nowhere else. The override on the guard gained a delay. The eval set grew from three demos to 33 cases.

## What we're building

Second Sig is a signature the humans can't give. A judge rehearses the exact bytes of a Safe proposal on a fork of Ethereum, compares what they do with what the proposer said, and signs an EIP-712 stamp only on a match. A guard on the Safe refuses any transaction without a stamp for its exact hash. Owners still sign as normal; their signatures alone no longer execute anything.

**Everything on the fork is real.** The Safe is a real v1.4.1 proxy created through the real `SafeProxyFactory` on a fork of mainnet pinned at block 21,895,238, the Bybit attack block. The guard is installed with a real `execTransaction(setGuard)`. Every execution goes through the real `Safe.sol`, which calls our guard. The contracts the cases touch sit at their mainnet addresses: Aave v3, USDC, WETH9, Uniswap V2, MultiSendCallOnly, and the contract the Bybit attackers used. The only contract we wrote is `SecondSigGuard.sol`.

**What we claim.** The guard makes the check mandatory. A hard floor in code rejects the Bybit class before any model runs. The two blind passes plus code reconciliation let honest but complex work through and ask about the rest, and every model claim has to cite evidence code can check. **What we don't claim:** that it catches everything, or that it replaces signers.

**Shape of the build.** Two people, two and a half days, Encode London, entered in the Gemini 4 Argon challenge and Agents That Ship. One laptop, one anvil fork, one CLI, three demo scenarios, a 33-case eval set.

## The scenarios and the eval set

The three demos run against the same 2-of-3 Safe on the fork with two owners' signatures already attached, so the point lands every time: the humans signed, and the chain still did what the judge said.

| Scenario | What the signers are told | What the bytes do | Verdict | What it shows |
| --- | --- | --- | --- | --- |
| `demo_bybit` | "Transfer 500 ETH to the warm wallet" | `delegatecall` to the Bybit attackers' contract, `transfer(0xbDd0…9516, 0)`, which overwrites the Safe's slot 0 | REJECT by the floor (rules 1, 2, 3) before any model. Guard reverts `SecondSig__NoStamp` with two valid signatures | The $1.4B attack shape against a real Safe |
| `demo_aave` | "Deposit 10,000 USDC into Aave v3" | MultiSendCallOnly batch: `USDC.approve(Pool, 10,000e6)`, `Pool.supply(USDC, 10,000e6, safe, 0)` | MATCH once the source reader has explained Aave's eight unlabelled writes; ASK until then. Stamp, attest, execute; Safe holds aUSDC | Honest complexity passes, and only because source was read and code checked it |
| `demo_auditor` | "Pay our auditor 100 USDC" | Batch: `USDC.transfer(auditor, 100e6)`, `USDC.approve(auditor, uint256 max)` | ASK with one Argon-written question. No stamp, execution reverts. An owner's answer amends the words and the judge re-runs on the same bytes | True but incomplete; the human stays in the loop |

The eval set is in `fixtures/cases/`, one folder per expected verdict. `fixtures/README.md` describes every file.

| Folder | Cases | Point |
| --- | --- | --- |
| `match/` | 01–08, 10 | Honest and precise: transfers, batches, owner and threshold changes, a finite approval, a Uniswap swap |
| `ask/` | 09, 38, 39, 42, 44–51 | Too vague, or one honest gap: an extra dust recipient, conflicting units, an unlimited allowance behind "up to", a WETH payment funded by wrapping, an unbooked wallet, a threshold side effect, clarifications that move the goalposts. 39, 49 and 51 carry scripted clarifications for the ASK loop |
| `reject/` | 31–35, 37, 40, 41, 43 | The words contradict the bytes, and four prompt injections (in the description, an address-book label, a contract label, a forged rehearsal tag). No floor rule fires on any; the comparison has to see the gap |
| `demo/` | the three above | Forward-pass tests and few-shot examples never read this folder |

Every case has a rehearsed `EvidenceBundle` in `fixtures/bundles/`. Recorded model forms in `fixtures/outputs/` exist for 01–10, 31–35 and the demos; 37–51 are waiting on the API. The Safe address in every case file is the placeholder `0x5AFE…5AFE`, substituted at run time.

## Architecture

```
  proposal (description, address book, safe_tx)
        │
  0  rehearse        judge/evidence/fork.py        anvil snapshot, real execTransaction, traces   ─▶ EvidenceBundle
        │
  1  hard floor      judge/evidence/rules.py       four rules, recomputed from evidence           ─▶ REJECT, or go on
        │
  2  forward ‖ backward                             two Flash calls, separate inputs
       words only    judge/jobs/forward.py          description + address book                     ─▶ ExpectedEffects
       bytes only    judge/jobs/backward.py         bundle minus description                       ─▶ Narration
        │
  3  source check    judge/layouts.py, evidence/slots.py     code labels for known contracts
                     judge/jobs/leftovers.py        one Argon call over verified source             ─▶ Classification
                     judge/corroborate.py           code recomputes each claimed slot; else ignored
        │
  4  reconcile       judge/checker.py               every citation must resolve (fail closed)
                     judge/canon.py                 identity is the address; labels are display
                     judge/compare.py               tiers, residuals                                ─▶ CompareResult
        │
  5  decide          judge/verdict.py               fixed table, pure function                      ─▶ Verdict
        │
     escalate        judge/jobs/escalate.py         Argon drafts the question or the statement      ─▶ HumanQuestion (advisory)
        │
     stamp           judge/stamp.py                 EIP-712 with the judge key, MATCH only
     attest, execute judge/pipeline.py              on the fork; the real Safe asks the guard
```

Only step 5 decides, and only `stamp.py` holds a key. Models fill forms through `response_format`; every call goes through `judge/model.py` and is logged to `logs/calls.jsonl` with its interaction id, so any verdict can be rebuilt with `--replay` and no model call.

## The pipeline, step by step

**0. Rehearse (code, Daniel).** `evm_snapshot`; zero the guard slot with `anvil_setStorageAt` so our own guard does not block the rehearsal; top the Safe up with USDC; run the real `execTransaction` with two owners' signatures; `debug_traceTransaction` with `callTracer` and `prestateTracer` in diff mode; decode calls and events with Etherscan ABIs (`judge/stages/sources.py`, proxies followed, cached in `fixtures/sources/`); label the slots code knows; `evm_revert`. Output: `EvidenceBundle` with citation ids `c*` (calls), `s*` (storage writes), `b*` (balance changes), `e*` (events), and `bundle.entry(id)` for the checker.

**1. Hard floor (code, Daniel).** Rules with no honest counterexample. Any hit is REJECT whatever any model says, and the verdict recomputes the floor from the evidence rather than trusting the bundle's own `floor_hits` list.

1. `delegatecall` to anything other than MultiSendCallOnly (the Safe proxy's own forward to its singleton is exempt)
2. A write to the Safe's singleton slot, guard slot, fallback-handler slot or modules mapping
3. A call or delegatecall into a contract with no verified source
4. `gasPrice != 0` with a gas token or refund receiver set

Bybit trips 1, 2 and 3. Every benign case in the set is pinned by `tests/test_verdict.py` as "never REJECT by the floor". Unlimited approvals, owner changes and threshold changes are deliberately not floor rules: they are sometimes intended, so they are the comparison's business.

**2a. Forward pass (`gemini-3.8-flash`, thinking low, blind to the trace).** Input: the description and any owner amendments, each wrapped by `labeller.spotlight()` in per-call random delimiters, plus the address book and the Safe address. Output: `ExpectedEffects`: movements, permission changes, Safe config changes, `nothing_else`, assumptions, questions for the human, confidence. Qualifiers such as "up to", "at least" and "about" are kept in `amount_human`, and `canon.bounds()` turns them into a ceiling, a floor or a loose figure. A form that licenses nothing must ask at least one question.

**2b. Backward pass (`gemini-3.8-flash`, thinking low, blind to the description).** Input: the bundle with the `description` field removed: the decoded call tree, the labelled storage diff, balance changes and events, every untrusted string spotlighted. Output: `Narration`: one sentence per effect with a severity (`info`, `notable`, `critical`) and citations, plus movements, permission changes and config changes that mirror the forward form item by item. It never sees the proposer's words, so the words cannot steer what the bytes are reported to do. The two passes run on separate inputs and their forms are recorded separately.

**3. Source check (code first, then one Argon call, then code).** Storage writes that no code layout labels are *unexplained* and count as notable, however the backward pass described them. Code labels come first: Safe and USDC layouts in `evidence/slots.py`, Uniswap V2 pair and WETH9 in `layouts.py`, keyed by address, never by contract name. For whatever is left, `jobs/leftovers.py` makes one `gemini-4-argon` call at thinking high, no tools, over the verified source of the implementation behind each written contract, trimmed to the files whose functions appear in the trace. It never sees the description. It returns `Classification`: per write, the variable, base slot, key, offset, cited source lines and a reading (`routine_bookkeeping`, `asset_or_permission`, `control`, `unknown`). `corroborate.py` keeps a claim only if the cited lines exist and name the variable and `keccak(key, base_slot) + offset` reproduces the slot. A corroborated bookkeeping claim labels the write. Any other reading raises the write to notable. An uncorroborated claim changes nothing. Aave's eight writes all reproduce; the trimmed call is about 98k tokens, down from 182k.

**4. Reconcile (code).** `checker.py`: every backward citation must resolve through `bundle.entry()`, every forward phrase must appear in the description; a bad citation is marked, never silently dropped, and the item it supports can then never explain anything. `canon.py`: both forms and the fixture ground truth become `CanonEffects`, where identity is the address: parties resolve through the address book, assets through the address book or cited evidence; chain symbols and contract names are display only. `compare.py` matches observed items against expected ones and records the weakest tier each match needed:

| Tier | Means |
| --- | --- |
| `exact` | same asset, direction, parties, amount |
| `amount_bounded` | the words fixed a ceiling, floor or loose figure, and the observed amount is inside it |
| `amount_unconstrained` | the words fixed no amount |
| `counterparty_via_callee` | the money landed somewhere inside the Safe's call into the named counterparty (USDC lands in the aToken because the Pool put it there) |
| `party_unresolved`, `asset_unresolved` | the words named a party or asset the address book does not know; everything else agrees |
| `inbound_from_callee` | the Safe received an asset the words did not name, from inside a licensed call (a receipt token). Receiving never drains the Safe |
| `internal_to_callee` | a movement between contracts inside a call the Safe made (pair to router legs). Logged, never a finding |

Only notable and critical observed items take part in the verdict. Residuals are `observed_unexplained` (with severity) and `expected_unobserved`.

**5. Decide (`verdict.py`, pure function).** In this order, and nothing later softens an earlier row:

1. any floor hit: REJECT
2. the rehearsal failed or reverted: ASK
3. a missing or invalid form: ASK
4. an unexplained critical observed effect: REJECT; an unexplained notable: ASK; an expected effect the trace does not show: ASK; `nothing_else` false: ASK with the forward pass's question; otherwise MATCH

The `Verdict` carries the `CompareResult`, so the view can show the per-effect table. 31–34 (contradictions without a critical write) come out ASK today; whether a contradiction should be REJECT where an omission is ASK is the open design question recorded in `reports/compare/FINDINGS.md`, and the rule is deliberately unapplied.

**Escalate (`gemini-4-argon`, thinking medium, advisory).** From the saved comparison it drafts the signer's question (ASK) or a two-sentence statement of why the transaction was refused (REJECT), classifies the gap as omission, contradiction or vague, and lists what to check first. Nothing in it feeds back into the decision. Its "would an honest proposer write this" field currently colours a caution line; the plan is to demote it to a note.

**Stamp, attest, execute (code).** On MATCH, `stamp.py` signs `{safeTxHash, forkBlock, judgeVersion}` with the judge key, the only module that reads it, and refuses if the key does not derive to the shared judge address. Owner 2 submits `attest`; owners 0 and 1's `execTransaction` runs through the guard. On ASK or REJECT the demo sends the same `execTransaction` anyway and shows the `SecondSig__NoStamp` revert.

**The ASK answer loop (`pipeline.answer`).** An owner's answer becomes an attributed amendment to the description. It is untrusted text and goes through the spotlighter like the original. The forward pass re-runs once on the amended words; the rehearsal and the backward pass are reused because the bytes did not change; the floor re-runs, so a floor hit can never be amended away; the table decides again. Proposal records with every amendment and the forms it produced live in `logs/proposals/`. Today the loop is unbounded; the planned bound (gap ids, an amendment counts only if it closes an asked gap, two rounds then REJECT) is in `NOTES.md` under "What's left".

**Failure modes.** A 429 is retried four times with a growing pause; any other API error, or a 429 that outlasts the retries, raises `ModelUnavailable`. Every failure ends in ASK, never MATCH. A live form is saved to `fixtures/outputs/` the first time it is produced, so the next run replays it with no model call.

## Models used and where

| Call | Model | Thinking | Sees | Returns | On the stamp path |
| --- | --- | --- | --- | --- | --- |
| Forward pass | `gemini-3.8-flash` | low | description + address book | `ExpectedEffects` | yes, as a checked form |
| Backward pass | `gemini-3.8-flash` | low | bundle without the description | `Narration` | yes, as a checked form |
| Source reader | `gemini-4-argon` | high | unlabelled writes + verified source, no description | `Classification` | only after code corroboration |
| Escalation | `gemini-4-argon` | medium | the saved comparison | `HumanQuestion` | no, advisory text |
| Naive baseline | `gemini-4-argon` | high | trace, source and description together | `Verdict` | never; eval only |
| `scripts/investigate.py` | Antigravity agent, read-only tools | | a bundle and its residuals | a write-up in `logs/investigations/` | never; developer aid |

All calls use the Interactions API through `google-genai` with `response_format` set to the pydantic schema. The adapter offers the models no tools. Every call is logged with its interaction id, prompt hash, latency and validation errors; the prompt text and the key are never logged. Determinism on stage comes from recorded forms and `--replay`, not from the sampler.

## The guard and the stamp, as built

`contracts/src/SecondSigGuard.sol` inherits `BaseGuard` from the v1.4.1 tag. Constructor: Safe, judge address, `judgeVersion`, override delay (50 blocks on the fork; zero is refused). Deployed through the mainnet CREATE2 deployer by `contracts/setup.py --guard`, so with the shared judge key it lands at the same address on every fresh fork.

- `attest(Stamp, sig)`: anyone may call. Checks `judgeVersion`, refuses a stale or future `forkBlock` (`MAX_STAMP_AGE` 100 blocks), recovers the EIP-712 signer and requires it to be the judge, rejects malleable high-`s` signatures, stores `stamps[safeTxHash] = forkBlock`, emits `Attested`.
- `checkTransaction(...)`: only the Safe may call. Recomputes the hash with `getTransactionHash(..., nonce() - 1)` because the Safe has already incremented its nonce. If an override is ready and its delay has passed, emits `OverrideExecuted` and passes; otherwise requires a fresh stamp or reverts `SecondSig__NoStamp(hash)` / `SecondSig__StaleStamp`.
- `approveOverride(hash)`: each current owner calls directly. When every owner has, `overrideReadyAt = block.number + OVERRIDE_DELAY`. Wider than the Safe's threshold and slow on purpose. Exists so a dead judge cannot brick the Safe.
- `checkAfterExecution`: empty.
- Custom errors `SecondSig__...`; events for every attest, override approval, override ready and override execution.

The stamp: domain `{name: "SecondSig", version: "1", chainId, verifyingContract: guard}`, type `Stamp(bytes32 safeTxHash, uint64 forkBlock, bytes32 judgeVersion)`, `judgeVersion = keccak256("second-sig/v1")`. Python signs with `eth_account`; the digest matches `guard.stampDigest()` byte for byte, proven on the fork by `tests/test_stamp.py --fork`. Foundry tests: `Guard`, `Stamp`, `Override`, `Bricking` (every guard change runs them before it goes anywhere near Sepolia). Removing the guard is itself a guarded transaction.

**Safe facts that shaped it.** Guards exist from Safe 1.3.0; Bybit's Safe was v1.1.1, so the judge can run on the real attack transaction at the pinned block while the guard demo replays the shape against our v1.4.1 Safe. v1.4.1 does not run guards on module transactions, which is why enabling a module is a floor rule.

## The interfaces

All in `judge/schemas.py`. `EvidenceBundle` and `Stamp` are the two halves' contract and change only by agreement, recorded under "Schema changes" in `NOTES.md`.

```
EvidenceBundle   safe_tx, safe_tx_hash, fork_block, description, execution_success, call_tree[Call],
                 storage_diff[SlotWrite], balance_diff[BalanceChange], events[Event], sources{addr: Source},
                 floor_hits[FloorHit]; entry(id) resolves c*/s*/b*/e* citations
ExpectedEffects  reasoning, movements, permission_changes, safe_config_changes, nothing_else, assumptions,
                 questions_for_human, confidence                                   (forward pass)
Narration        reasoning, effects[sentence, severity, cites], movements, permission_changes,
                 safe_config_changes, confidence                                   (backward pass)
Classification   reasoning, items[SlotClaim: contract, variable, base_slot, key, offset, source_cites, reading]
HumanQuestion    reasoning, gap_kind, would_an_honest_proposer_write_this, question | statement,
                 what_to_check, confidence                                         (escalation, advisory)
CanonEffects     Party, Asset, CanonMovement, CanonPermission, CanonConfig; identity is the address
CompareResult    matched[tier], observed_unexplained[severity], expected_unobserved, info_effects,
                 uncited, unsupported, nothing_else, questions, explained_slots
Verdict          reasoning, decision (MATCH | ASK | REJECT), reasons, floor_hits, question, compare
Stamp            safeTxHash, forkBlock, judgeVersion                              (matches the Solidity struct)
```

`ProbeHypothesis` is empty by design: the probe job is designed, not built, because on the current cases a probe agent has zero verdict delta and under invariant 4 it could only ever raise suspicion.

## Fixtures, replay and the eval

- `fixtures/build.py` generates every case file; edit the Python, not the JSON. Cases 37–51 were drafted in `PROMPT.md`.
- `judge.evidence.fork <case>` rehearses a case and writes `fixtures/bundles/<id>.bundle.json` plus the raw traces.
- `judge/truth.py` derives ground truth from the calldata so each pass is graded on its own, not only the final verdict.
- `scripts/compare_benign.py [--live] [--include-reject]` runs the whole judge on recorded forms and writes `reports/compare/<id>.md`, `summary.json` and `FINDINGS.md`, which says which pass is wrong where.
- `judge/stages/judge.py` is the naive baseline: one Argon call that sees everything. Results and the auditor miss in `eval/naive_baseline.md`. `eval/run.py` (the table with the Argon-on-backward ablation row) is not written yet.
- `tests/`: 321 tests; offline ones run with `uv run pytest`, `--live` needs `GEMINI_API_KEY`, `--fork` needs anvil.

Measured on the one fully live run (case 46, 24 October): about 65 s wall, 58 s of it model latency, three model calls; the verdict and the question were the ones the case was written for. The write-up is `reports/live-loop-case-46.md`.

## Commands

The full list is in `CLAUDE.md`. The ones the demo uses:

```
~/.foundry/bin/anvil --fork-url $MAINNET_RPC --fork-block-number 21895238 --steps-tracing --port 8545
uv run python contracts/setup.py --guard          # Safe + guard on a fresh fork
uv run secondsig demo bybit|aave|auditor [--live] # replay forms by default, then stamp/attest/execute on anvil
uv run secondsig judge <case.json> [--replay] [--chain]
uv run secondsig answer <case.json> "owner's words" --owner 1 [--chain]
uv run secondsig reset                            # anvil_reset + Safe + guard; clears logs/proposals/
```

## Roles

| Area | Daniel (chain) | Rafi (AI) |
| --- | --- | --- |
| Fork, Safe, guard | `contracts/`, `setup.py`, Foundry tests, bricking tests | stamp signing in Python |
| Evidence | `judge/evidence/`: fork, trace, decode, slots, rules | `layouts.py` for Uniswap and WETH |
| Fixtures | `fixtures/bundles/`, `fixtures/examples/` | `fixtures/build.py`, cases, `fixtures/outputs/` |
| Judge | | `judge/` layers 2–5, jobs, pipeline, `cli/`, `eval/` |
| Tools | `scripts/investigate.py` | `scripts/compare_benign.py`, `ask_questions.py` |
| Pitch | guard and chain questions; records the on-chain beats | script, video cut, model questions |

Cross-imports to keep stable: `judge/evidence/fork.py` calls `judge.stages.sources.load()` and `judge.run_fixture.ensure_usdc()`.

## Status on 24 October and what is left

Done and proven on the fork: rehearsal, floor, both passes, checker, canon, compare, the source reader unit, the decision table, escalation, stamp, attest, execute, the ASK answer loop, the three demos by replay, the replay report, the naive baseline on three cases.

Left, in order (detail in `NOTES.md`, "What's left"):

1. Record what the API owes: the Aave leftovers file, forms for 37–51, re-recorded forward forms for 01–35 and the demos under the 24 October prompt.
2. The bounded ASK loop.
3. Small prompt and table edits: owner and threshold writes stay critical in the backward prompt; the honesty field becomes a note; temperature pinned at 0 for the record.
4. `eval/run.py` with the Argon-on-backward ablation row.
5. README with setup instructions and the models-used section; pitch and video.
6. Two more benign protocol cases (Compound v3 supply, Uniswap V3 exactInputSingle), if time allows.

Deliberately not built: the web UI and HTTP API, the probe job, `sepolia/watcher.py` and `attacker.py`, the `propose`, `sign`, `override` and `describe` CLI commands, majority voting on enum fields, `anvil --load-state`.

**Cut list, first to go at the top.** The two extra protocol cases; the ablation row; the bounded ASK loop (the unbounded one works and is honest about it in Q&A); live model calls on stage (replay everything and say so).

**Never cut.** The real Safe on the fork with the guard set through `execTransaction`. Bybit: floor REJECT, then the on-chain revert with two valid signatures. Aave: MATCH, stamp, execution. The auditor: ASK, revert, an owner answers, the judge re-runs on the same bytes.
