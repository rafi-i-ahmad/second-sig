# Second Sig

NOTE! Do NOT get too hung up on the spec it is okay to deviate from it somewhat.

An extra signer for Safe multisigs. It rehearses a proposed transaction on a fork, compares what the bytes actually do with what the description says, and signs a stamp only on a match. A guard contract on the Safe refuses every transaction that has no valid stamp for its exact hash, unless every owner has approved an override and the delay has passed.

Hackathon build: two people, about 2.5 days, Encode London. `Second Sig build spec v2.md` (plus the UI and demo docs next to it) is a rough guide, not the source of truth: where it disagrees with this file, this file wins. This file holds what an agent working in the repo must not get wrong. `NOTES.md` holds the live operational state (fork, test Safe, what has run, schema changes); read it before touching the fork.

## Who owns what

- `judge/` (except `judge/evidence/`), `cli/`, `eval/`, `fixtures/build.py` and the case files it writes, `fixtures/outputs/`: Rafi (AI side).
- `contracts/` (including `setup.py`), `judge/evidence/` (`fork.py`, `trace.py`, `decode.py`, `slots.py`, `rules.py`), `fixtures/bundles/`, `fixtures/examples/`, `sepolia/`: the chain lead. Daniel (Crypto side).
- Cross-imports to keep stable: `judge/evidence/fork.py` calls `judge.stages.sources.load()` and `judge.run_fixture.ensure_usdc()`. Don't rename or change either without telling Daniel.
- The two halves meet only at `judge/schemas.py` (`EvidenceBundle`, `Stamp`). Do not change either schema without both people agreeing. If a change seems necessary, stop and say so. Record every agreed schema change under "Schema changes" in `NOTES.md`.

## Layout

`(stub)` means the file holds only a docstring or `NotImplementedError` so far. Update the mark when you fill one in.

```
contracts/            Foundry project (solc ^0.8.24; lib/forge-std, lib/safe-smart-account)
  src/SecondSigGuard.sol        stamp on every tx; attest(), approveOverride(); MAX_STAMP_AGE 100
  test/               Base (shared setup), Guard, Stamp, Override, Bricking .t.sol. GuardForkTest
                      skips unless MAINNET_RPC is set
  script/             Deploy.s.sol, SetGuard.s.sol  (stubs; setup.py --guard does the job)
  setup.py            deploys or finds the test Safe v1.4.1 on the fork, funds it; --guard deploys
                      SecondSigGuard via CREATE2 and setGuard()s it. Also a library
                      (ensure_safe, ensure_guard, OWNERS, sign_safe_tx, rpc, FORK_BLOCK, JUDGE_VERSION)
judge/
  schemas.py          pydantic models. Filled: EvidenceBundle (+ SafeTx, Call, SlotWrite,
                      BalanceChange, Event, Source, FloorHit), ExpectedEffects (+ Movement,
                      PermissionChange, SafeConfigChange), Narration (+ ObservedEffect,
                      ObservedMovement, ObservedPermissionChange, ObservedSafeConfigChange),
                      Decision, Verdict, Stamp. Classification, ProbeHypothesis, HumanQuestion: empty
  evidence/           layer 1: fork.py rehearses on a snapshot and builds the EvidenceBundle;
                      trace.py, decode.py, slots.py feed it; rules.py is the hard floor
  labeller.py         layer 2: spotlight() wraps untrusted text in per-call random tags
  model.py            Gemini Interactions adapter: complete(), stream(), count_tokens(); logs every call
  jobs/               layer 3: forward.py, backward.py (work); leftovers, probe, escalate (stubs)
  checker.py          layer 4  (stub)
  verdict.py          layer 5: decide(bundle, model_form) -> Verdict. Floor hit -> REJECT (recomputes the
                      floor, never trusts bundle.floor_hits); failed rehearsal or no form -> ASK; else the
                      form's decision. FLOOR_EXPLANATIONS holds the signer-facing paragraph per rule
  stamp.py            EIP-712 signing with the judge key: make_stamp(bundle), sign(), digest(),
                      attest(). The only module that reads JUDGE_PRIVATE_KEY
  stages/
    sources.py        Etherscan verified source + ABI, cached in fixtures/sources/, proxies followed
    judge.py          the naive one-call baseline (see below the invariants). Eval only
  run_fixture.py      runs a fixture through the test Safe on the fork; --save-trace writes the trace
cli/
  secondsig.py        propose, judge, sign, execute, override, describe, demo, eval  (all stubs)
  view.py             three-panel terminal view (rich)  (stub)
sepolia/              watcher.py, attacker.py  (stubs)
fixtures/
  build.py            generates every case JSON; edit the Python, not the JSON
  README.md           what every folder here is for; read it before adding a fixture
  cases/              every proposal, one folder per expected verdict, every file has expected_verdict
    match/            honest and precise (01-08, 10)
    ask/              too vague to act on (09)
    reject/           description contradicts the bytes (31-35); floor-clean, so the model's job
    demo/             demo_bybit (REJECT), demo_aave (MATCH), demo_auditor (ASK). Forward-pass tests and
                      few-shot examples never read this folder (invariant 8)
  outputs/            model outputs: <id>.forward.json, <id>.backward.json, <id>.naive.json
  sources/            Etherscan cache, one file per address
  traces/             older raw traces from run_fixture --save-trace; only the naive baseline still reads them
  bundles/            <id>.bundle.json (EvidenceBundle) + <id>.rehearsal.json (raw traces), from fork.py.
                      All 18 cases (01-10, the three demos, mismatch 31-35) as of 24 October
  examples/           bybit.bundle.json, the hand-checked example the schema tests validate
eval/
  run.py              the eval table  (stub)
  naive_baseline.md   naive-judge results and the auditor-miss analysis
tests/                pytest: schemas, model adapter, evidence, floor rules, stamp, forward cases
                      (live), backward (input checks offline; bundles live). Markers: `live` needs --live + GEMINI_API_KEY; `fork` needs --fork + anvil
scripts/              smoke_gemini.py, forward_transfer.py: one-off checks
logs/                 calls.jsonl, verdicts.jsonl (gitignored; used by --replay)
```

## Commands

Working now:

```
uv sync
uv run pytest                                   # offline tests; live ones skip
uv run pytest tests/test_forward_cases.py --live -s   # calls Gemini; needs GEMINI_API_KEY
uv run pytest tests/test_backward.py --live -s        # backward pass on fixtures/bundles/
uv run pytest tests/test_stamp.py --fork -s            # stamp, attest, execute case 01 through the guard on anvil
uv run python fixtures/build.py                 # regenerate fixture JSON
cd contracts && ~/.foundry/bin/forge build && ~/.foundry/bin/forge test -vv

# fork (anvil is at ~/.foundry/bin, not on PATH; see NOTES.md for the RPC in use)
~/.foundry/bin/anvil --fork-url $MAINNET_RPC --fork-block-number 21895238 --steps-tracing --port 8545
uv run python contracts/setup.py [--guard]      # deploy or find the test Safe; --guard also sets the guard
uv run python -m judge.evidence.fork <case.json> [--out fixtures/bundles]   # rehearse, write the bundle
uv run python -m judge.verdict fixtures/bundles/<id>.bundle.json           # decision table on a saved bundle
uv run python -m judge.run_fixture fixtures/cases/01_send_eth_ops.json [--save-trace]
uv run python -m judge.stages.judge <case.json>... [--dump-prompt out.txt --no-call]
```

Not working yet (stubs): every `uv run secondsig ...` command (`demo`, `judge`, `eval --table`, `--replay`) raises `NotImplementedError`. `anvil --load-state fixtures/anvil-state.json` needs a dump that doesn't exist yet.

Fixtures carry the Safe placeholder `0x5AFE…5AFE`. `run_fixture.py` and `fork.py` substitute the real address at run time. A Bybit-shaped run overwrites the Safe's slot 0, so reset the fork afterwards (`NOTES.md`). Once the guard is set, `run_fixture.py` reverts with `SecondSig__NoStamp`. `fork.py` doesn't, because it zeroes the guard slot inside its snapshot.

Read and write text files with `encoding="utf-8"`. The default encoding on Windows is not UTF-8, and the fixtures contain non-ASCII characters such as `…`.

Secrets live in `.env` only: `GEMINI_API_KEY`, `MAINNET_RPC`, `SEPOLIA_RPC`, `ETHERSCAN_API_KEY`, `SAFE_API_KEY`, `JUDGE_PRIVATE_KEY` (with its public `JUDGE_ADDRESS`), test owner keys. Never print, log or commit any of them.

## Invariants: never break these

The safety argument rests on these. If a task seems to require breaking one, stop and ask.

1. The model never decides. The verdict is a pure function in `verdict.py` of the evidence bundle plus checked model forms.
2. Any hard-rule hit forces REJECT, whatever any model output says.
3. The model never sees or touches a key, and has no tool that writes, signs or sends. Tools available to model calls are read-only and run on throwaway fork snapshots.
4. The model proposes probes; code runs them and records the results. A probe can raise a slot's suspicion, never lower it. Only the compiler storage layout can lower it.
5. The forward pass never sees the trace. The backward pass never sees the description. Keep them in separate calls with separate inputs. `EvidenceBundle` carries `description`, so never hand the whole bundle to the backward pass: build its input from the bundle without that field.
6. Every claim in a model form cites a trace entry (or source line). `checker.py` drops any claim whose citation does not resolve, and the item becomes ASK.
7. Everything an attacker could author is untrusted text: the description, on-chain strings, revert reasons, token and contract names, comments and identifiers in verified source. It reaches the model only through `labeller.py`, wrapped in per-call random delimiters. Never put it in a system instruction.
8. Attack and injection examples live in `fixtures/` and the eval set only. Never paste them into runtime prompts.
9. The stamp binds `safeTxHash`, `forkBlock` and `judgeVersion`. The guard checks all three. Do not let the guard accept anything the judge did not hash.
10. The override stays slow: more approvals than the Safe's threshold, plus a delay. `setGuard(address(0))` is a risky call and needs a stamp or an override.
11. Never fake a live call in the demo. If the model is unavailable, use `--replay` and say so.

**The one sanctioned exception: the naive baseline.** `judge/stages/judge.py` is a single Argon call that sees the trace, the sources and the description together, and returns a `Verdict` directly. It breaks invariants 1 and 5 on purpose, because it is the row the layered judge is measured against in the eval. It still obeys 3, 7 and 8. Nothing on the stamp path (`verdict.py`, `stamp.py`, the CLI's `sign` or `execute`) may import or call it.

## Stamp format (EIP-712)

```
domain: { name: "SecondSig", version: "1", chainId, verifyingContract: <guard address> }
Stamp:  { bytes32 safeTxHash, uint64 forkBlock, bytes32 judgeVersion }
```

`attest(stamp, sig)` is callable by anyone; the guard recovers the signer and compares it with the judge address. Stamps older than `MAX_STAMP_AGE` blocks are rejected, and so are low-s-violating (malleable) signatures. `judgeVersion` is the bytes32 `keccak256("second-sig/v1")` (`contracts/setup.py` `JUDGE_VERSION`). `verifyingContract` is the guard's address. One judge key is shared for the demo; its public address and the resulting guard address are `SHARED_JUDGE_ADDRESS` and `SHARED_GUARD_ADDRESS` in `contracts/setup.py`. The private key is passed between us privately and lives in `.env` only (`NOTES.md`, "Judge key"). In code, get the guard from `ensure_guard(w3, safe)` and pass its address to `judge/stamp.py` rather than repeating the constant. The stamp round trip is proven on the fork by `tests/test_stamp.py --fork`.

## Safe gotchas

- Guards exist from Safe 1.3.0. Our test Safe on the fork is v1.4.1 (address and owners in `NOTES.md`). Inherit the base guard from the safe-smart-account tag that matches it, so `setGuard`'s interface check passes.
- The Safe increments its nonce before calling `checkTransaction`. Recompute the hash with `getTransactionHash(..., nonce() - 1)`.
- Safe batches via delegatecall to MultiSendCallOnly. The rule is "delegatecall to anything not on the allowlist", not "any delegatecall".
- The guard has no "risky" list: every transaction needs a stamp, `setGuard(address(0))` and owner changes included. The pattern checks live in the hard floor (`judge/evidence/rules.py`): delegatecall to anything but MultiSendCallOnly; a write to the Safe's singleton, guard, fallback-handler slot or modules mapping; a call into unverified code; nonzero `gasPrice` with a refund receiver or gas token set.
- Safe v1.4.1 does not run guards on module transactions. The floor blocks enabling a module (modules-mapping write), which is what keeps this closed.
- Bybit's real Safe was v1.1.1 (no guard support). The judge can run on the real transaction at block 21,895,238; the guard demo replays the attack shape against our own v1.4.1 Safe.
- A broken guard can freeze a Safe. Every guard change gets the Foundry bricking tests (`test/Bricking.t.sol`) before it goes to Sepolia.

## Gemini notes (SDK facts confirmed against google-genai 2.33.0; details in the `judge/model.py` docstring)

- Interactions API via `google-genai`. Models in use: `gemini-3.8-flash` at thinking low for the forward pass (`jobs/forward.py` default); `gemini-4-argon` at thinking high for the naive baseline and for spot checks.
- `thinking_level`: the adapter accepts low, medium or high. `temperature` is deprecated on this API: determinism comes from logging every interaction id, replaying from `logs/`, and three-sample majority votes on enum fields (not built yet).
- Typed output: `response_format` carries the pydantic JSON schema, and `response_mime_type` must also be set. The adapter retries once on a validation error, then raises `ModelFormError`. Timeouts and API errors raise `ModelUnavailable`. Callers turn either into ASK, never MATCH.
- Resend `tools`, `system_instruction` and `generation_config` on every turn, including function-result turns.
- Run any tool loop first, then make a separate call with `response_format` for the typed output, until we confirm the two can be combined.
- Every call goes through `judge/model.py`, which writes one line to `logs/calls.jsonl`: interaction id, prompt hash, model, thinking level, parsed output, validation errors, latency. The raw prompt and the key are never logged. The adapter offers the model no tools yet.

## Conventions

- `main` is always demoable. Work on branches; merge at gates.
- Python: type hints, pydantic for every model output, no bare dicts crossing module boundaries.
- Solidity: custom errors, named `SecondSig__...`; events for every attest, override approval and override execution.
- Prefer deleting scope over adding cleverness. The cut list in the spec says what goes first.
- Live-API tests are marked `@pytest.mark.live` and run only with `--live`. Save model outputs under `fixtures/outputs/`, never in `fixtures/cases/`.
- When unsure whether something weakens an invariant, ask rather than guess.
