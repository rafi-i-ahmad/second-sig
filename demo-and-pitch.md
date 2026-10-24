# Second Sig: demo and pitch

24 October 2026 · Rafi. Rewritten for the CLI as built; the 22 October version assumed a web page.

One script serves the live demo and the video: three scenarios, one terminal, three minutes. Every beat is a command typed from shell history, the three panels appear, and the verdict is said out loud only after it is on screen.

## What is on screen

One terminal at a large font (18 pt or more; the back row has to read a storage slot id), `anvil` in a second window that is never shown. Each `secondsig` command prints three panels and then the chain steps:

| Panel | Title on screen | Shows |
| --- | --- | --- |
| 1, blue | The words (forward pass) | the description, any owner amendments in cyan, and what the forward pass says the words promise: movements, permissions, config changes |
| 2, magenta | The bytes (backward pass) · safeTxHash · block | what the rehearsal showed, one line per effect with its severity and evidence ids; floor hits in red; storage writes explained from source with their `path:line`; a yellow count of writes nobody has explained |
| 3, green / yellow / red | The verdict (code) | MATCH, ASK or REJECT; the per-effect table (✓ matched with its tier, ? unexplained, ∅ promised but not seen); the note for the signer; the stamp line; the model calls made |
| chain lines | ● stamp, ● attest, ● execTransaction | green dot for a step that happened, red for a refusal, with the block number or the guard's revert |

## The three-minute demo

Bybit goes first because it is the whole argument in a minute; Aave shows the judge is not a brick wall; the auditor shows the human staying in the loop. Replay is the default and is said out loud (invariant 11). The one live model call is the owner's answer in the auditor scenario: an amended description has no recorded form, so the forward pass must run. It is a small Flash call that has gone through every time the key worked; if it fails, the fallback is one sentence and the recorded clip.

| Time | Command | Say |
| --- | --- | --- |
| 0:00 | (terminal showing the output of `uv run secondsig reset`: Safe and guard found on the fork) | "In February 2025, Bybit's signers approved what their screen showed them. The bytes they signed did something else, and about $1.4 billion left. Second Sig checks the bytes, and the vault itself refuses to run anything it hasn't checked." |
| 0:15 | `uv run secondsig demo bybit` | "This is a real Safe multisig on a fork of Ethereum, at the block of the attack. Two of three owners have signed. The description says transfer 500 ETH. We rehearse the bytes." |
| 0:30 | panels appear | "Left, what the signer was told. Middle, what the bytes do when we run them: no ETH moves; a delegatecall into the attackers' contract, still on mainnet, overwrites the vault's master-code slot." |
| 0:45 | panel 3 | "Right: REJECT. Three hard rules in code fired before any model ran. The statement under it was written by Gemini 4 Argon from the evidence, for the signer to read. The model explains; it does not decide." |
| 0:55 | chain lines | "No stamp. The real Safe contract asks our guard, and with two valid signatures it reverts: `SecondSig__NoStamp`. The signers' screen could have said anything." |
| 1:05 | `uv run secondsig demo aave` | "Now honest work. Depositing 10,000 USDC into Aave touches several contracts and eight storage writes nobody's layout labels. A rule engine would panic, or wave it through." |
| 1:20 | panel 2, source lines | "Two Flash passes read the words and the bytes separately. For the eight writes, Argon read the verified Aave source, about a hundred thousand tokens, and claimed what each one is. Code recomputed every slot from the claim. All eight reproduce; here are the source lines." |
| 1:40 | panel 3, chain lines | "MATCH. The judge key signs a stamp for this exact hash and this fork block. Attested. Executed. The vault holds aUSDC, and no human was interrupted." |
| 1:55 | `uv run secondsig demo auditor` | "Last one. Pay our auditor 100 USDC. True. The bytes also let the auditor spend unlimited USDC, forever. No rule catches this without false alarms, because unlimited approvals are sometimes intended." |
| 2:10 | panel 3 | "ASK. One question, written by Argon, naming the party and the amount. No stamp, so the chain refuses until a human answers." |
| 2:20 | `uv run secondsig answer fixtures/cases/demo/demo_auditor.json "Yes, grant the auditor an unlimited USDC allowance for monthly invoicing." --owner 1 --chain` | "An owner answers. That is live: the words changed, so the forward pass runs again on the same bytes. The answer is on the record, attributed. The bytes never changed, so the rehearsal and the hard floor stand." |
| 2:40 | panels, chain lines | "MATCH, stamp, executed. Everything you saw is real: a Safe deployed through Safe's own factory, real Aave, the real Bybit contract. The only thing we wrote on-chain is a hundred-line guard, installed with one transaction. Second Sig: the signature your signatures can't replace." |
| 2:55 | | Questions. |

**Until the Aave leftovers file is recorded**, `demo aave` is ASK ("eight storage writes nobody has explained") and the 1:20 line becomes: "Without the source read, the judge refuses to lower suspicion on writes it cannot explain, and asks." Say that, do not fake the MATCH.

**If something stalls.** The live answer past twenty seconds: say "the model is slow; this is the recorded run", play the auditor clip from the video, move on. The fork misbehaves: `uv run secondsig reset`, re-run the scenario; if it fails twice, play that scenario's clip. Never narrate a failure for more than one sentence.

## Video plan

One 3:00 screen recording of the terminal with the script above as voice-over. It satisfies the Gemini brief (three minutes) and Agents That Ship (two to four), and it is the fallback for any live beat that fails.

| Time | Shot |
| --- | --- |
| 0:00 to 0:12 | Plain text: the Bybit date, the loss, "Signers approved what their screen showed. The chain ran what they signed." |
| 0:12 to 1:05 | Bybit, exactly as the script: command, panels, revert |
| 1:05 to 1:55 | Aave, with the source lines held on screen for five seconds |
| 1:55 to 2:40 | Auditor: ASK, revert, the owner's answer, MATCH, execution |
| 2:40 to 3:00 | Slow scroll over the guard's `checkTransaction` in the editor, closing line, repo URL |

- Record each scenario as its own clip the moment it works end to end. Bybit and auditor can be recorded today by replay; Aave waits for the leftovers file.
- Voice-over recorded separately, one take per row, then cut to the clips.
- Captions burned in for every command and verdict, so it reads with the sound off.
- Final export by Sunday noon, uploaded before the freeze.

## Judges' questions

Short, honest answers; most are "yes, that is a limit, and here is what bounds it". The name in brackets takes it on the day.

| Question | Answer |
| --- | --- |
| Why not just hard rules? (Rafi) | Rules are in the system and they catch Bybit on their own. They only hold rules with no honest counterexample. The model's job is the rest: letting honest complexity through without interrupting a human, and asking about the true-but-incomplete case. |
| Does the model decide? (Rafi) | No. Two Flash passes fill typed forms, one from the words and one from the bytes, never both. Code checks every citation, reconciles the two, and a fixed decision table produces the verdict. A floor hit is REJECT whatever any model says. |
| Why Gemini 4 Argon specifically? (Rafi) | Two jobs. It reads the whole verified source of every touched contract in one context and says what each unlabelled storage write is; on Aave that is about a hundred thousand tokens after trimming, and code recomputed every slot it claimed. And it writes the question or the statement the signer reads. Flash runs the two blind passes, where speed matters more than depth. |
| Why no agent on the stamp path? (Rafi) | Under our invariants an agent's output can only be a hypothesis code must verify, or a reason to raise suspicion, never lower it. Every tool it could call is deterministic and already run by code. On our cases a probe agent moves zero verdicts. We built the agent anyway, `scripts/investigate.py`, as a developer aid that explains residuals with read-only tools, deliberately off the stamp path. |
| What about prompt injection in the description? (Rafi) | The backward pass never sees the description, so the words can't steer what the bytes are reported to do. Untrusted text reaches a model only inside per-call random delimiters. Every output is a typed form whose citations code checks. Cases 37 to 43 are injections in the description, an address-book label, a contract label and a forged rehearsal tag; the worst any achieves is ASK. |
| What if the proposer keeps answering? (Rafi) | Only owners may amend, every amendment is attributed and on the record, and each answer re-runs only the forward pass; the bytes, the rehearsal and the hard floor never move. Today the loop is unbounded; the planned bound is two rounds, then REJECT as unresolved. |
| Isn't this all replayed? (Rafi) | The forms are recorded from live runs and every one has an interaction id in the log. The chain is live on every beat. The owner's answer was a live call. `--live` re-runs everything, and we keep it off on stage because a hackathon key 429s. |
| Can't Argon just say MATCH on a hijack? (Rafi) | Not for the floor's cases: a floor hit is REJECT whatever the model says. For subtler cases the model can be wrong, and the pitch says so; the floor is why that doesn't lose the vault's code or its owners. |
| What if the judge is offline, or its key is lost? (Daniel) | Every owner calls `approveOverride` on the guard directly, and after a delay the transaction executes without a stamp. Wider than the normal threshold and slow on purpose. |
| What if the judge key is stolen? (Daniel) | The stamp is necessary, not sufficient. A thief still needs the owners' signatures. Stealing the key removes one check; it doesn't move funds. |
| The fork can differ from mainnet. (Daniel) | True. The stamp binds the fork block and expires after 100 blocks; environment-sensitive contracts are future work. |
| Bybit's Safe didn't support guards. (Daniel) | Right, it was v1.1.1. We replay the attack shape against a v1.4.1 Safe with the guard set. Any Safe from 1.3.0 on can install this today with one `setGuard` transaction. |
| Isn't the judge a central point of trust? (both) | One judge today, and it can only add a requirement, never remove one. Several independent judges with k-of-n stamps is the obvious next step. |
| How slow, how much does it cost? (Rafi) | The one fully live run took about 65 seconds, 58 of them model latency, three calls. Read the token count from the panel and the latency from `logs/calls.jsonl`. Never estimate on stage. |

## Pre-flight, ten minutes before

- [ ] `anvil` running at the pinned block on the paid RPC; `uv run secondsig reset` done
- [ ] All three scenarios run once by replay in the last ten minutes; `logs/proposals/` cleared by the reset
- [ ] `.env` has the judge key and `GEMINI_API_KEY`; one tiny Flash call succeeded in the last hour, or the live answer is cut
- [ ] Terminal at demo font size, shell history holding the four commands in order
- [ ] Backup video open in a second window, paused at 0:00
- [ ] Laptop plugged in, notifications off, display mirroring on, screen never sleeps
- [ ] Second laptop with the repo and the video
- [ ] Whoever isn't typing holds the Q&A sheet

## Submission checklist

Both briefs want the same package: a repo with a README and setup instructions, a two-to-four-minute video, and a plain statement of which models and agents we used and how.

- [ ] README: the problem, the one-paragraph mechanism, setup from clone to `secondsig demo bybit`, the models-used table from the build spec, the agent's tools and steps and where a human approves, the invariants in plain words, where the record lives (`logs/`, `fixtures/outputs/`)
- [ ] Video uploaded; link in the README
- [ ] Which Gemini models and agents, and how: copy the table from `build-spec-v2.md`
- [ ] Repo public, `.env` not in it, `logs/` gitignored
