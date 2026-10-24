# Working notes

Operational facts for the fork and the test Safe. Updated 23 October 2026.

## Schema changes (for Daniel)

- 23 October, Rafi: `judge/schemas.py` `Verdict` now has `reasoning: str` as its first field
  (required), and `Decision.APPROVE` is renamed `Decision.MATCH`, to match the build spec and the
  UI. `EvidenceBundle` and `Stamp` are unchanged.

## Fork

| Thing | Value |
| --- | --- |
| Chain | Ethereum mainnet, chain id 1 |
| Fork block | 21,895,238 (the Bybit attack block) |
| RPC in use | `https://eth.drpc.org` (public, no key, serves archive state at this block) |
| `MAINNET_RPC` in `.env` | empty as of 23 October; set it to an Alchemy or Infura URL before the demo |
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
| Guard | `SecondSigGuard` at `0x7ee55531aacf54195D872EbBD1e19a1c725DD8A5`, set with `--guard` (see below) |
| Judge | `0x0C7B56D75DCA0c4D7258fBEe0d0E9fa8E74B5298` (`JUDGE_ADDRESS` in `.env`; key in `JUDGE_PRIVATE_KEY`) |
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
It sits in the stamp's EIP-712 domain, so `judge/stamp.py` must use this address and judgeVersion.

**Once the guard is set, nothing executes without a stamp**, including `judge/run_fixture.py`: it
reverts with `SecondSig__NoStamp(safeTxHash)` (selector `0x66d21dae`). Run fixtures on a fork
without `--guard`, or zero the guard slot first as the rehearsal does:
`anvil_setStorageAt(safe, 0x4a204f620c8c5ccdca3fd54d003badd85ba500436a431f0cbda4f558c93c34c8, 0)`.

The fixtures still carry the placeholder `0x5AFE…5AFE`; `judge/run_fixture.py` substitutes the real
address at run time, so the fixture files do not change when the fork is rebuilt.

## Run a fixture on the fork

```sh
uv run python -m judge.run_fixture fixtures/cases/01_send_eth_ops.json
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
(`judge/stages/sources.py`). Model outputs go in `fixtures/outputs/`; `fixtures/cases/` holds cases only.

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

Not yet run on the fork: cases 02 to 10, the three demo scenarios. Nothing has been run through the
guard, which is not deployed.

Naive judge (`judge/stages/judge.py`, one `gemini-4-argon` call, thinking high, sees everything):
01 MATCH, auditor REJECT (expected ASK), Bybit REJECT. Table and hypotheses for the auditor miss
in `eval/naive_baseline.md`; outputs in `fixtures/outputs/<id>.naive.json`.
