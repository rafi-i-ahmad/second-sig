# Fixtures

Attack and injection examples live here and in the eval set only. Never paste them into runtime prompts.

`build.py` generates every case file from plain Python (`uv run python fixtures/build.py`). Edit the
Python, not the JSON. Each file holds the treasurer's `description`, the `address_book` the forward
pass may see, the exact `safe_tx` bytes, a decoded `calls` view for humans, and the `intent` ground
truth (movements, permission changes, Safe config changes, `nothing_else`, `expect_question`).

- `cases/`: ten ordinary proposals, the forward-pass test set. No demo scenario ever goes here, so
  forward-pass tests and few-shot examples cannot read the demos.
- `bybit/`: the Bybit attack shape (delegatecall to the attackers' contract), expected REJECT.
  The real transaction is mainnet block 21,895,238.
- `aave/`: a benign Aave v3 deposit batch, expected MATCH.
- `auditor/`: a true-but-incomplete payment with an unlimited approval riding along, expected ASK.
- `transfer/`: the first forward-pass dry run (fork context plus a recorded Argon output).
- `tornado/`: a sanctioned-destination case (not yet built).
- `injection/`: descriptions that try to steer the model (not yet built).
- `anvil-state.json`: dumped fork state for offline runs (`anvil --load-state`), gitignored.

The Safe address in every file is the placeholder `0x5AFE…5AFE`; replace it once the fork
deployment exists. People and wallets are invented, deterministic addresses derived from their
names. USDC, the Aave v3 Pool, the Uniswap V2 router, WETH and MultiSendCallOnly are real mainnet
contracts (Etherscan links in `build.py`).
