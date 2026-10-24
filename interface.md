# Second Sig: what changed in the verification loop (24 October 2026)

Merged into `main` as `94913cc`; pull `main`. Base `5b8bb89`; `git diff 5b8bb89 -- judge cli scripts` shows every code change.

**None of your files changed:** `contracts/`, `judge/evidence/`, `fixtures/bundles/`, `fixtures/examples/`, `sepolia/`. The cross-imports `judge.stages.sources.load()` and `judge.run_fixture.ensure_usdc()` are unchanged; the CLI now calls `ensure_usdc` too.

## Unchanged: safe to build on

- `pipeline.judge(proposal, bundle, replay=, emit=)`, `pipeline.answer(...)`, every `JudgeResult` field, and `sign_stamp`, `attest` and `execute`.
- `web/server.py` is untouched: same routes, same SSE events.
- `EvidenceBundle`, `Stamp`, the EIP-712 format, the guard, the judge and guard addresses, and `MAX_STAMP_AGE`.
- Decisions are still `MATCH`, `ASK` and `REJECT`, and a floor hit is `REJECT` before any model runs.

## Verdicts: what the UI will now see

- **Drive the UI from `verdict.decision`, never from "everything matched".** An `ASK` can now arrive with every item matched. If the forward pass asked a question, the table asks even when `nothing_else` is true. The question is in `verdict.question`, and `verdict.reasons` is `["the description raises a question"]`.
- **Contradictions are `ASK`, not `REJECT`** (team decision). These are words that state one payment or allowance over bytes that do another. `REJECT` means a floor hit or an unexplained critical effect.
- **An owner or threshold change the words don't license is critical, so it is `REJECT`** (cases 35, 38 and 50).
- **A new code check adds unexplained items when the backward pass leaves something out.** They appear in `verdict.compare.observed_unexplained` like any other item:

| `kind` | `severity` | `cites` | `reason` |
| --- | --- | --- | --- |
| `movement` | notable | one balance entry, `b<n>` | `the narration leaves part of this balance change out` |
| `permission` | notable | one Approval event, `e<n>` | `the narration leaves out an allowance the Safe granted` |
| `config` | critical | one event from the Safe, `e<n>` | `the narration leaves out a change to the Safe's owners or threshold` |

- **The tiers `party_unresolved`, `asset_unresolved` and `amount_unconstrained` now appear only on what the Safe receives.** A payment out of the Safe, or an allowance, needs a known token, a known counterparty and an amount. Without them it shows as unexplained and the verdict is `ASK`.
- **`internal_to_callee` can now cover a leg into a contract the words name**, such as `ETH WETH -> Uniswap router` inside a swap.
- **New field `verdict.compare.ignored_labels`**, a list of addresses whose address-book label was dropped. When it isn't empty, `verdict.reasons` ends with `address-book label ignored (not a plain name) for 0x…`. Show it as a warning.

## Address book: new requirements

This matters most for the Safe{Wallet} integration.

- **Labels must be plain names:** at most 48 characters, no line breaks, and none of `: ; < > [ ] { } |`. Any other label is dropped and its address shown raw. Validate imports with `judge.labeller.plain_address_book(book)`, which returns `(kept, dropped_addresses)`.
- **Every counterparty the Safe pays or approves must be in the book**, or written as a `0x` address in the description. A name that matches only a verified contract's name doesn't count for outflows, because anyone can deploy a contract called "Treasury".
- **Every token the Safe sends must be in the book** (USDC, WETH, aUSDC and so on; ETH needs no entry). "Send 1,000 USDT" with no USDT entry is `ASK`.
- **A new wallet goes into the book first.** For "her new wallet from the email", the forward pass leaves the payment out and asks for the address.
- **The book is now treated as untrusted** and is spotlighted in every model call. Identity is still the address; labels are for display only.

## How descriptions are now read

This is useful for proposer-facing copy or hints in the UI.

- **Every outflow or allowance needs an amount or a bound** ("up to", "at least", "about"). In a partly vague description, the forward pass lists the fixed items and asks about the open ones.
- **"Approve the invoice" means sign-off**, not an ERC-20 allowance.
- **A swap through a router implies an approval** for the amount going in, the same as a deposit does.
- **Adding an owner without stating a threshold** means the threshold is assumed unchanged.
- **Text in a description addressed to the reviewer or the system is ignored.**

## What the signers see

- **`escalate.compose()` no longer adds the "Caution:" or "Note:" sentence**, and `escalate.CAUTION` is gone. For `ASK`, `JudgeResult.note` is the gap label plus the question; for `REJECT`, it is the statement.
- **`HumanQuestion.would_an_honest_proposer_write_this` still exists.** If you show it, show it as a minor note, not a warning.
- **Every case that isn't `MATCH` now has a recorded question** in `fixtures/outputs/<id>.question.json`.

## Fork and chain setup

- **The recorded bundles assume the Safe holds 10,000 USDC at nonce 1** (after `setGuard`). `secondsig reset` and the CLI's fork helper now top the USDC up, as `web/server.py` always did.
- **If your UI drives the fork itself, call `judge.run_fixture.ensure_usdc(w3, safe_address)` before executing a replayed `MATCH`.** Otherwise the guard accepts the stamp, and then the deposit reverts inside the Safe with `GS013`.
- **A `MATCH` that executes advances the nonce.** Reset before replaying again.

## Recorded data and cases

- **Every forward and backward form has been re-recorded** with the new prompts. `fixtures/outputs/demo_aave.leftovers.json` now exists, so Aave replays to `MATCH`, with its 8 storage writes explained from source.
- **`fixtures/outputs/<id>.backward.argon.json` files are a model comparison only.** The pipeline never reads them.
- **Cases moved folders; ids are unchanged:**
  - 31–34, 37, 40, 41 and 43 are now in `cases/ask/`;
  - 38 and 50 are now in `cases/reject/`, which holds 35, 38 and 50.

  If the UI lists cases by folder or hard-codes expected verdicts, update it.
- **`demo_aave`'s address book gained `aUSDC`.**
- **All 33 cases replay to their expected verdict.** See `reports/compare/summary.json` and `reports/compare/FINDINGS.md`.

## Live model calls

- **Each line of `logs/calls.jsonl` now carries `usage`** (`input`, `output`, `thought`, `cached`) **and `est_usd`.** Use them for any latency or token panel.
- **There is an optional spend cap:** set `GEMINI_SPEND_CAP_USD`, and optionally `GEMINI_SPEND_SINCE`. Past the cap, calls raise `ModelUnavailable` and the verdict is `ASK`. `uv run python scripts/spend.py` prints the running total.
- **`backward.run(..., timeout_s=)`** is a new optional argument.

