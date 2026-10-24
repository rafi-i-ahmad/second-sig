"""Layer 4: validate model forms' citations.

Two kinds of citation, two checks, both pure:

- Backward (trace ids such as "c4", "s0"): every id must resolve through ``bundle.entry``.
  An item with a missing id is not dropped; canon.py marks it ``cited_ok=False`` and
  compare.py treats it as unexplained, so it can still force ASK or REJECT. A bad citation
  must never hide a critical finding (fail closed, invariant 6).
- Forward (a phrase from the description): the phrase must appear in the description after
  normalisation. An unsupported item cannot explain an observed effect.
"""

from __future__ import annotations

import re

from judge.schemas import EvidenceBundle

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]")


def check_citations(cites: list[str], bundle: EvidenceBundle) -> list[str]:
    """The cited ids that do not exist in the bundle. Empty means every citation resolves."""
    return [c for c in cites if bundle.entry(c) is None]


def normalise(text: str) -> str:
    """Lower case, punctuation removed, whitespace collapsed: the comparison form for phrases."""
    return _WS.sub(" ", _PUNCT.sub(" ", text.lower())).strip()


def phrase_supported(phrase: str, description: str) -> bool:
    """True if the cited phrase is a normalised substring of the description."""
    p = normalise(phrase)
    return bool(p) and p in normalise(description)
