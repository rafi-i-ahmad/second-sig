# Second Sig: product overview

An extra signer for Safe multisigs. It checks that a transaction does what its description says, and the Safe refuses to execute anything that hasn't been checked.

This document describes Second Sig as a product: who uses it, where it runs, and what using it looks like. For how it is built, see `build-spec-v2.md` and `CLAUDE.md`.

## The problem

A Safe owner approving a transaction sees a hex blob, maybe a decoded function name, and a description written by whoever proposed it. In practice owners trust the description and the wallet UI. If either one lies, everyone signs.

That is how Bybit lost about $1.5bn in February 2025. The signers' interface showed a routine transfer. The bytes they signed replaced the Safe's logic with the attacker's. Every signature was genuine, and nothing on-chain checked that the transaction matched what the signers thought they were approving.

## What Second Sig does

1. **Rehearses** each proposed transaction on a private copy of the chain and records exactly what it does: every call, balance change, storage write and permission change.
2. **Compares** that against the description. Two separate passes do this: one reads only the description and says what it should do, the other reads only the rehearsal and says what it actually did. Code, not a model, reconciles the two.
3. **Gives a verdict**: Match, Ask or Reject.
4. **Signs a stamp** only on a Match. The stamp is bound to that exact transaction hash.
5. **Enforces it on-chain.** A guard contract installed on the Safe reverts any transaction without a valid stamp, however many owner signatures it has.

Some patterns are rejected outright whatever the description says: a delegatecall to an unknown contract, rewriting the Safe's core slots, enabling a module, or a call into unverified code.

## Who it's for

- DAO treasuries and protocol multisigs holding upgrade keys or large balances
- Funds and companies running operations through a Safe
- Any team whose signers can't realistically decode every transaction themselves

## Where it runs

Nothing runs on the owners' machines, and owners don't install anything.

| | Hosted | Self-hosted |
|---|---|---|
| Who runs it | A Second Sig operator, much as Blockaid or Hypernative run their services today | The treasury's own team, on its own server or cloud account |
| What runs | Watcher, simulation nodes, model calls, judge key in an HSM | The same, as a container image plus an RPC endpoint and a model API key |
| Who holds the judge key | The operator | You |
| Who gets paged when it's down | The operator | You |
| Suited to | Most teams | Large treasuries that don't want to trust a vendor |

On-chain, the only addition is the guard contract, at one address per chain.

## What it looks like to the user

### Setup (once)

1. Register the Safe with Second Sig (hosted) or point your deployment at it (self-hosted).
2. An admin proposes a "set guard" transaction in Safe{Wallet}, using the guard address Second Sig gives you.
3. Owners sign and execute it like any other transaction. From then on the Safe is protected.

### Every transaction

Owners keep using Safe{Wallet} and their hardware wallets as before. The changes are a description, a verdict and a stamp.

1. **Propose.** Alice proposes "Pay Acme 50,000 USDC for the Q3 audit", writing the description in the place she already writes notes, or in the Second Sig Safe App.
2. **Verdict.** Within a minute or so the verdict appears wherever the team already looks: a Slack or Telegram message, an email, or a badge on the transaction in Safe{Wallet}.

   - ✅ **Match.** "Sends 50,000 USDC to 0xAc…me (Acme). Nothing else happens." Owners sign as normal.
   - ❓ **Ask.** "The description doesn't say how much, or who 0x71… is." Alice makes the description more precise and it runs again.
   - ❌ **Reject.** "The description says 'routine upgrade', but this transaction changes who controls the Safe." Do not sign.

   Every verdict links to a three-panel view: what the description says, what the transaction actually does, and where the two differ.
3. **Sign.** Owners sign on their devices as usual.
4. **Execute.** Just before execution Second Sig re-checks the transaction against the current chain state and puts a fresh stamp on-chain. On a Match the executor doesn't notice this step.

### When Second Sig is wrong or unavailable

Every owner (more than the normal threshold) approves an override, and it can run once a delay has passed, for example 48 hours. That is slow on purpose: it's fine for a legitimate edge case or an outage, and too slow for an attacker who has phished a signer or two. Removing the guard is itself a guarded transaction, so it needs either a stamp or the same override.

## Before and after

| Today | With Second Sig |
|---|---|
| Signers see a hex blob and trust the proposer | Signers see a plain-language check of whether the transaction does what it claims |
| A compromised UI shows the wrong thing and everyone signs | The check runs on separate infrastructure, so a compromised UI can't get a mismatched transaction past the guard |
| Enough signatures always execute | Enough signatures and no stamp → revert |
| Descriptions can be vague | Vague descriptions get an Ask: the one new habit teams have to adopt |

## How it differs from existing tools

- **Transaction simulation** (Tenderly, built into Safe{Wallet}) shows what a transaction does but leaves the signer to notice that it's wrong. Second Sig makes the comparison and enforces it.
- **Threat scanners** (Blockaid, Hypernative and similar) flag known-bad patterns and addresses. Second Sig checks each transaction against what the proposer says it does, so it can also catch an attack nobody has seen before, as long as the description is precise.
- **Both of these warn. Second Sig blocks.** The guard sits on-chain, so the check can't be bypassed by signing anyway.

## Safety properties

- **The model never decides.** It describes and compares, and fixed code turns its cited output into a verdict. Every claim must cite the rehearsal or the description, or it doesn't count.
- **The model never touches keys** and has no tool that can sign or send.
- **Some patterns always get rejected,** whatever any model says.
- **A stamp covers one exact transaction,** the block it was checked at, and the judge version, and it expires after about 20 minutes.
- **The worst case is a slow path, never an unlocked Safe.** If Second Sig fails, the full override still works.

## Limits

- Safe v1.3.0 or later; older Safes can't install guards.
- Safe v1.4.1 doesn't run guards on module transactions. Second Sig closes this gap by refusing to enable modules, so Safes that already have modules installed need them reviewed.
- Rehearsal can't predict state that changes between the check and execution. That's why the stamp is short-lived and taken just before execution.
- Each execution needs one extra on-chain call (`attest`), and so a little more gas.
- A hosted deployment means trusting the operator's judge key. Self-hosting or multiple independent judges reduce that.
