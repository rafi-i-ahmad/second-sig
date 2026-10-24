# Working notes

Operational facts for the fork and the test Safe. Updated 24 October 2026.

## Schema changes (for Daniel)

- 23 October, Rafi: `judge/schemas.py` `Verdict` now has `reasoning: str` as its first field
  (required), and `Decision.APPROVE` is renamed `Decision.MATCH`, to match the build spec and the
  UI. `EvidenceBundle` and `Stamp` are unchanged.
- 24 October, Daniel, accepted by Rafi: `EvidenceBundle` filled in (`safe_tx`, `execution_success`,
  `call_tree`, `storage_diff`, `balance_diff`, `events`, `sources`, `floor_hits`), with citation ids
  `c*`/`s*`/`b*`/`e*` and `bundle.entry(id)` for `checker.py`. New supporting models: `SafeTx`,
  `DecodedArg`, `Call`, `SlotWrite`, `BalanceChange`, `Event`, `Source`, `FloorRule`, `FloorHit`.
  `Stamp` unchanged; its `judgeVersion` is the bytes32 hex of `keccak256("second-sig/v1")`.
- 24 October, Rafi: `Verdict` gains `floor_hits: list[FloorHit] = []`, so the UI can show which hard
  rules forced a REJECT. `EvidenceBundle` and `Stamp` unchanged.
- 24 October, Rafi (branch `compare`): additive. `Verdict` gains `question: str | None` and
  `compare: CompareResult | None`. New canonical-form models for layer 4: `Party`, `Asset`,
  `CanonMovement`, `CanonPermission`, `CanonConfig`, `CanonEffect`, `CanonEffects`, `Match`,
  `Unexplained`, `CompareResult`, plus the literals `MatchTier`, `Direction`, `ConfigField`,
  `FormSource`. `EvidenceBundle`, `Stamp`, `ExpectedEffects`, `Narration` unchanged.

## Fork

| Thing | Value |
| --- | --- |
| Chain | Ethereum mainnet, chain id 1 |
| Fork block | 21,895,238 (the Bybit attack block) |
| RPC in use | `https://eth.drpc.org` (public, no key, serves archive state at this block) |
| `MAINNET_RPC` in `.env` | set on Rafi's machine as of 24 October; the anvil below was still started on dRPC |
| anvil | Foundry 1.8.6, installed at `~/.foundry/bin` (not on PATH) |

dRPC's public endpoint worked for a single-case rehearsal. It may rate-limit a fork under demo load,
and anvil's first run against a fresh endpoint fetches every touched slot over the network. Once
`MAINNET_RPC` is set, start anvil with that instead; the Safe address below does not change.

Other public endpoints checked on 23 October and rejected for archive requests without a key:
publicnode, llamarpc, ankr, 1rpc, merkle, flashbots, blockpi.

## Start anvil

```sh
~/.foundry/bin/anvil --fork-url https://eth.drpc.org --fork-block-number 21895238 --steps-tracing --port 8545
```

With `MAINNET_RPC` set in `.env` (Git Bash):

```sh
export $(grep -E "^MAINNET_RPC=" .env | xargs)
~/.foundry/bin/anvil --fork-url "$MAINNET_RPC" --fork-block-number 21895238 --steps-tracing --port 8545
```

Ready when it prints `Listening on 127.0.0.1:8545`. The scripts read `ANVIL_RPC` if set, otherwise
`http://127.0.0.1:8545`.

## The test Safe

| Thing | Value |
| --- | --- |
| Safe proxy | `0xDFECEf26e5d211b9935cABC9FAD1edB8960aaE47` |
| Version | 1.4.1 (real singleton at `0x41675C099F32341bf84BFc5382aF534df5C7461a`) |
| Proxy factory | `0x4e1DCf7AD4e460CfD30791CCC4F9c8a4f820ec67` |
| Fallback handler | `0xfd0732Dc9E303f09fCEf3a7388Ad10A83459Ec99` |
| Owners | anvil default accounts 0, 1, 2 (`0xf39F…2266`, `0x7099…79C8`, `0x3C44…93BC`) |
| Threshold | 2 of 3 |
| Salt nonce | 20251023 |
| Funding | 1,000 ETH via `anvil_setBalance`, topped up whenever it drops below that |
| Guard | `SecondSigGuard` at `0xf4932401784c5D8435890C226729a87B6464BBC0` (`SHARED_GUARD_ADDRESS` in `contracts/setup.py`), set with `--guard` (see below) |
| Judge | `0x7bAc29915313CC27a39163fD82595C6A355b40B9` (`SHARED_JUDGE_ADDRESS`; the key is in `.env`, see "Judge key"). Daniel's earlier guard at `0x7ee5…8A5` with judge `0x0C7B…5298` is retired |
| judgeVersion | `keccak256("second-sig/v1")` = `0xcfcf56cea6319c219b578886973494ce72c5fcc289fa275fbf44fff029f9f534` |
| Override delay / max stamp age | 50 blocks / 100 blocks |

The address is deterministic: the factory uses CREATE2 over the setup calldata and the salt, so
every fresh fork puts the Safe at the same address as long as owners, threshold, fallback handler
and salt stay as above. `contracts/setup.py` predicts the address, deploys only if there is no code
there, and otherwise reuses it.

Rebuild or check the Safe:

```sh
uv run python contracts/setup.py
```

Install the guard (deploys `SecondSigGuard` through the mainnet CREATE2 deployer, then
`execTransaction(setGuard)` signed by owners 0 and 1). Needs `forge build` first. Idempotent:

```sh
(cd contracts && forge build) && uv run python contracts/setup.py --guard
```

The guard address is fixed by the CREATE2 salt and the constructor arguments (Safe, judge,
judgeVersion, override delay), so it is the same on every fresh fork unless one of those changes.
The judge address is one of them. With the shared judge, `setup.py --guard` lands at
`SHARED_GUARD_ADDRESS` on every fresh fork and warns if it does not (a different `JUDGE_ADDRESS`
in `.env`, or recompiled guard bytecode: update the constant then). Code still should not hard-code
the address: `judge/stamp.py` takes it as an argument, and `contracts.setup.ensure_guard(w3, safe)`
returns the live contract. `setGuard` spends Safe nonce 0, so the first fixture run after `--guard`
is at nonce 1.

## Judge key

One judge for the demo, generated by Rafi on 24 October: address `0x7bAc…40B9`, hard-coded as
`SHARED_JUDGE_ADDRESS`. The **private key is in Rafi's `.env` only**. Daniel: get it from Rafi over
a private channel, put it in your `.env` as `JUDGE_PRIVATE_KEY`, leave `JUDGE_ADDRESS` empty, and
rebuild the fork (`anvil_reset`, `setup.py --guard`); your guard then lands at the shared address.
The key is never committed, logged or printed (CLAUDE.md): anyone holding it can stamp anything.

`judge/stamp.py` is the only code that reads the key. It refuses to sign if the key does not derive
to the shared judge (or to `JUDGE_ADDRESS`, if `.env` overrides it for a local experiment).

**Once the guard is set, nothing executes without a stamp**, including `judge/run_fixture.py`: it
reverts with `SecondSig__NoStamp(safeTxHash)` (selector `0x66d21dae`). Run fixtures on a fork
without `--guard`, or zero the guard slot first as the rehearsal does:
`anvil_setStorageAt(safe, 0x4a204f620c8c5ccdca3fd54d003badd85ba500436a431f0cbda4f558c93c34c8, 0)`.

The fixtures still carry the placeholder `0x5AFE…5AFE`; `judge/run_fixture.py` substitutes the real
address at run time, so the fixture files do not change when the fork is rebuilt.

## Run a fixture on the fork

```sh
uv run python -m judge.run_fixture fixtures/cases/match/01_send_eth_ops.json
```

Prints the receipt, `ExecutionSuccess` or `ExecutionFailure`, ETH balance changes for every
address-book entry, and the `callTracer` call tree. Each run advances the Safe's nonce and leaves
the fork as is; restart anvil for a clean state.

## Traces

`uv run python -m judge.run_fixture <case.json> --save-trace` writes `fixtures/traces/<id>.json`:
callTracer tree with logs, prestateTracer diff (storage, balances, nonces, minus the coinbase), and
ERC-20 balances before and after for every holder in a Transfer log. Before each run it tops the
Safe up to 10,000 USDC by writing USDC's balance slot (mapping slot 9).

Captured on 23 October: `01_send_eth_ops`, `demo_auditor`, `demo_bybit`. Bybit replaces the Safe's
singleton (slot 0 becomes `0xbDd0…9516`), after which `nonce()` reverts. Reset afterwards:

```sh
curl -s -X POST -H 'Content-Type: application/json' http://127.0.0.1:8545   --data '{"jsonrpc":"2.0","id":1,"method":"anvil_reset","params":[{"forking":{"jsonRpcUrl":"https://eth.drpc.org","blockNumber":21895238}}]}'
uv run python contracts/setup.py
```

Verified sources from Etherscan are cached in `fixtures/sources/<address>.json`
(`judge/stages/sources.py`). Model outputs go in `fixtures/outputs/`; `fixtures/cases/` holds cases only,
one folder per expected verdict (`match/`, `ask/`, `reject/`) plus `demo/`. See `fixtures/README.md`.

## Runs so far

Forward pass (description and address book only, no trace):

| Cases | Model | Result | Output |
| --- | --- | --- | --- |
| cases 01 to 10 | `gemini-3.8-flash`, thinking low | all 10 pass against `intent` | `fixtures/outputs/<id>.forward.json` |
| case 09 | `gemini-4-argon`, thinking high | same form as flash, one question, no retry | `fixtures/outputs/09_routine_transfer_vague.forward.argon-high.json` |

Run: `uv run pytest tests/test_forward_cases.py --live -s`

On the fork, through the real Safe with two owner signatures:

| Case | Result |
| --- | --- |
| 01 "Send 5 ETH to the ops wallet" | `ExecutionSuccess`, 5 ETH moved, nonce 0 to 1; call tree is proxy, delegatecall to singleton, two ecrecover staticcalls, one CALL with 5 ETH and empty data. Rerun after the refactor at nonce 1, same result. |

Rehearsed with `judge.evidence.fork`, bundles in `fixtures/bundles/`: 01, Bybit, Aave and auditor
(Daniel), then cases 02 to 10 and mismatch 31 to 35 (Rafi), all on 24 October. All 18 cases.

### Hard floor false-positive check (24 October, Rafi)

Every benign case rehearsed on the fork with the guard set (the rehearsal zeroes the guard inside
its snapshot). The question was whether `rules.py` rejects anything honest. It does not:

| Case | Why it could have tripped | Result |
| --- | --- | --- |
| 01 send 5 ETH, 02 pay Dana USDC, 08 refund Sam, 09 vague 1 ETH | recipients are EOAs with no source | no hits: rule 3 skips addresses with no code |
| 03 ETH + USDC batch, 07 three contractors | delegatecall to MultiSendCallOnly 1.4.1 | no hits: `0x9641…02e2` is on the allowlist |
| 04 add owner Priya | Safe self-call, writes `Safe.owners[…]` and `Safe.ownerCount` | no hits: owners (slot 2) and ownerCount (slot 3) are not protected; only singleton, guard, fallback handler and modules (slot 1) are |
| 05 raise threshold to 3 | Safe self-call, writes `Safe.threshold` | no hits |
| 06 finite approve to Uniswap | ERC-20 approve | no hits: approvals are the model's question, not a floor rule |
| 10 approve + swapExactTokensForETH | touches UniswapV2Router02, the USDC/WETH pair, WETH9 | no hits: all verified on Etherscan (cached in `fixtures/sources/`) |
| Aave deposit, auditor payment | batches, 11 unlabelled Aave slot writes, unlimited approve | no hits |
| Bybit | | rules 1, 2 and 3 |
| 31–35 `fixtures/cases/reject/` (description contradicts the bytes; expected REJECT) | approve to an EOA; a payment to a non-address-book EOA; a swap delivered to an EOA; threshold lowered by a Safe self-call | no hits on any, as designed: none of these is an attack *shape*, each is an honest-looking transaction with a lying description. The REJECT has to come from the model. If we want the floor to catch 31 and 33, the spec's "approve or setApprovalForAll to an EOA" rule would, and no benign case approves an EOA |

What the bundles show for the mismatch cases, which is what the backward pass will have to say
out loud: 31 `USDC.allowances[Safe][Ravi]` goes to `uint256 max`; 32 the 2,500 USDC land at
`0x97f8…c277`, an address the address book does not know, while the words say Dana; 33 no balance
changes at all, one allowance write; 34 the Safe pays 0.3546 ETH to the WETH/USDC pair and the
1,000 USDC go to Ravi, not the Safe; 35 `Safe.threshold` 2 → 1 after `Safe.ownerCount` 3 → 4.

Two conservative behaviours worth knowing: our own Safe proxy shows `verified=False` because
Etherscan has never seen a fork-only address, and rule 3 skips the Safe itself for that reason.
A *recipient* that is a contract with no verified source (another Safe proxy that Etherscan has
not matched, a fresh wallet contract) would trip rule 3 and be rejected; that is intended, but it
is the one place an honest payment could be refused. `tests/test_verdict.py` pins all twelve
benign cases as "never REJECT".

`judge/verdict.py` is the decision table (layer 5): floor hit → REJECT with a signer-facing
paragraph per rule (`FLOOR_EXPLANATIONS`) plus what the rehearsal showed and the evidence ids;
failed rehearsal → ASK; no checked model form → ASK; otherwise the form's decision. It recomputes
the floor from the evidence rather than trusting `bundle.floor_hits`. Try it:
`uv run python -m judge.verdict fixtures/bundles/demo_bybit.bundle.json`.

### Stamp round trip through the guard (24 October, Rafi)

`uv run pytest tests/test_stamp.py --fork -s` runs case 01 the way the full system will, on Rafi's
fork with the guard set (`judge/stamp.py` signs, code only; the "verdict" is assumed MATCH because
the bundle has no floor hits and the judge is not wired yet):

| Step | What happened |
| --- | --- |
| Rehearse | `fork.build_bundle` on a snapshot: `ExecutionSuccess`, no floor hits, `safeTxHash 0x19ae…5c3f`, fork block 21,895,241. The guard slot was zeroed only inside the snapshot; afterwards the guard was still set |
| Owners sign, no stamp | `execTransaction` with owners 0 and 1 reverts at the guard with `SecondSig__NoStamp(0x19ae…5c3f)` |
| Stamp | `stamp.make_stamp(bundle)` → `{safeTxHash, forkBlock 21895241, judgeVersion keccak("second-sig/v1")}`; `stamp.sign` with the judge key. Python's digest equals `guard.stampDigest()` on-chain, byte for byte |
| Attest | Submitted by owner 2 (anyone may) in block 21,895,242; `stamps[hash] == 21895241`; `Attested` emitted |
| Execute | Same calldata, same two owner signatures, block 21,895,243: `ExecutionSuccess`, 5 ETH to the ops wallet, nonce 1 → 2 |
| Replay | Same bytes at nonce 2: `SecondSig__NoStamp` again. A stamp is for one hash, and the hash includes the nonce |

The test takes an `evm_snapshot` after `ensure_guard` and reverts to it, so it leaves the fork
with the guard set and nothing else changed. Everything that executes through the Safe from then
on needs a stamp; `judge/run_fixture.py` will revert. Offline, `tests/test_stamp.py` also checks
that changing any of chain id, guard address, hash, fork block or judgeVersion breaks the
signature, and that eth_account's EIP-712 encoding matches the hand-built digest.

Signature facts the guard relies on and eth_account satisfies: 65 bytes `r ‖ s ‖ v`, `v` in {27, 28},
low `s` (the guard rejects `s > n/2`). `MAX_STAMP_AGE` is 100 blocks from `forkBlock`, so a stamp
signed on a stale rehearsal (or a `forkBlock` in the future) is refused at `attest`.

### End to end by replay (24 October, Rafi, branch `compare`)

`uv run python scripts/compare_benign.py` runs the whole judge on recorded forms with no model
call: floor, then canon/compare of the forward and backward forms, then the decision table. Result
on the 13 benign and demo cases: 01–08 and 10 MATCH, 09 ASK, Aave MATCH, auditor ASK, Bybit
REJECT. Every expected verdict met. Reports in `reports/compare/`, findings in
`reports/compare/FINDINGS.md`. The five reject cases have no recorded forms yet: the Gemini billing
account hit its **monthly spending cap** (HTTP 429) on 24 October while recording them, so they
read ASK (fail closed) until the cap is raised at ai.studio/billing and `--live --include-reject`
is run again. Forward forms for the three demos and backward forms for 02–10 were recorded before
the cap hit.

Naive judge (`judge/stages/judge.py`, one `gemini-4-argon` call, thinking high, sees everything):
01 MATCH, auditor REJECT (expected ASK), Bybit REJECT. Table and hypotheses for the auditor miss
in `eval/naive_baseline.md`; outputs in `fixtures/outputs/<id>.naive.json`.
