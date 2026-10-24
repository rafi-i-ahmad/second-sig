# Second Sig: the view

24 October 2026 · Rafi. The 22 October version specified a React page over an HTTP API. Neither was built, and with the time left neither will be. The product's face is the three-panel terminal view in `cli/view.py`, rendered with `rich`. This file describes that view as it is, and keeps the one design idea from the old spec that still matters: three columns, words, bytes, verdict, filling in that order.

## Purpose

Make the argument to a judge who is an AI engineer, not an EVM auditor, in one screen per scenario: what the signer was told, what the bytes did, what code decided, and then what the chain did about it. Every element either shows what the bytes do, shows what the judge decided, or explains the one concept needed at that moment. Anything else is cut.

## The three panels

Printed by `view.show(JudgeResult)` after every `secondsig judge`, `answer` or `demo` run.

**Panel 1, blue: The words (forward pass).** The description in bold. Under it, each owner amendment on its own line in cyan, attributed `+ Owner 0x7099…79C8: ...`. Then the forward pass's reading of the words, rendered through `canon`: movements (`Safe sends 2,500 USDC to Dana`), permission changes (`Safe allows Uniswap router to spend up to 1,000 USDC`), Safe config changes (`add owner Priya`). `(no forward form)` if the pass did not run.

**Panel 2, magenta: The bytes (backward pass) · safeTxHash 0x… · block N.** The backward pass's movements, permissions and config changes in the same rendering, so the two panels read side by side. Then one row per observed effect: severity in dim, yellow or red; the sentence; the evidence ids it cites in dim. Below that, in order and only when present:

- floor hits, each in red: `FLOOR delegatecall_not_allowlisted: ...`
- the source check: a bold heading `storage writes explained from verified source and checked by code (98,412 tokens of source read)`, then one row per write: green `source` with the variable and `path:line` for corroborated claims, red `source` for writes the reader raised, dim `unconfirmed` for claims code could not reproduce
- a yellow line `N storage write(s) nobody has explained: s4, s7` when unlabelled writes remain

**Panel 3, coloured by the verdict: The verdict (code).** `MATCH` in green, `ASK` in yellow or `REJECT` in red, bold. Then the per-effect table from `CompareResult`: `✓` matched items with the tier that explained them in dim (`exact`, `amount_bounded`, `counterparty_via_callee`, ...); `?` observed items nothing explains, with severity and cites; `∅` expected items the trace did not show, marked `promised, not seen`. Then the note for the signer: Argon's question on ASK, its statement on REJECT, written from the saved comparison. Then the stamp line in green on MATCH: `stamp: forkBlock 21895241, judgeVersion 0xcfcf56ce…, signed 0x…`. Last, dim: `model calls: forward gemini-3.8-flash 20134 ms <interaction id>; ...`, or nothing on a pure replay.

## The chain lines

Printed by `view.show_chain` when `--chain` or `demo` runs against anvil, one line per step, a green `●` for a step that happened and a red `○` for a refusal:

```
● stamp            signed by the judge key: 0x3f9a12c0d1…
● attest           guard 0xf4932401… recorded the stamp in block 21895242
● execTransaction  two owner signatures, block 21895243: ExecutionSuccess
```

```
○ stamp            none: the verdict was not MATCH
○ execTransaction  two owner signatures, reverted. SecondSig__NoStamp: the guard refused
```

The `execTransaction` line is sent on every verdict, because the point is that execution is attempted and the chain decides.

## Rules the view follows

- Colour means state and nothing else: green is MATCH, a stamp or a step that happened; yellow is ASK or notable; red is REJECT, critical, a floor hit or a refusal. Everything else is the terminal's default.
- Plain English first, hex second. Amounts carry their symbol and thousands separators. Evidence ids and slot ids are short and dim, present so a judge can see that every line points at something.
- Identity is the address. Where an address has an address-book name the name is shown; a raw address is shown shortened, never hidden. (Open item: show the verified contract name next to a raw address, display only, never for matching.)
- Nothing in the view computes a verdict or a label. It renders `JudgeResult` and `CompareResult`, which code produced.
- Untrusted text (the description, amendments, on-chain strings) is shown as text, never interpreted as markup.

## Demo ergonomics

- Terminal font at 18 pt or larger, dark background, window wide enough that panel 2's rows do not wrap (about 160 columns).
- The four demo commands live in shell history in order; nothing is typed from scratch on stage.
- Open item: `secondsig reset` prints nothing of its own today. A one-line summary (fork block, Safe address and version, guard set) would make a good opening frame.
- Open item: a per-pass status line during a live run, so a 60-second model wait is not a blank screen. Replay runs print immediately and do not need it.

## If a web page is ever built

The 22 October design still applies and is summarised here so it is not lost: a dark, flat, monochrome page with colour reserved for the verdict; three equal cards that fill left to right as the pipeline runs, mapping one to one onto the three panels above; a top bar stating what is real (`Anvil mainnet fork · block · real Safe v1.4.1 · guard set`); a context banner of three sentences per scenario for someone who has never used a multisig; `Judge` and `Execute on the vault` as the only primary buttons; a `Replay from log` text button when the model is unavailable. Tokens: background `#0A0A0A`, surface `#141414`, border `#262626`, text `#EDEDED` / `#A3A3A3` / `#6B6B6B`, match `#3DBF7A` on `#0F2A1C`, ask `#D9A441` on `#2A2008`, reject `#D14D4D` on `#2A1010`; Inter for text, JetBrains Mono for addresses, hashes and amounts. The server would own the owner keys, the judge key and the fork; the page would own nothing and compute nothing. Everything it needs already exists as `JudgeResult`.
