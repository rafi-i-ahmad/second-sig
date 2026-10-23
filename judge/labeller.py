"""Layer 2: spotlighting.

All attacker-authored text (descriptions, on-chain strings, revert reasons, names,
source comments) passes through here, wrapped in per-call random delimiters.
Never place such text in a system instruction.
"""
