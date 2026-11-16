"""herecraft — the Python surface a unit programs against.

`__api__` is the series this runtime offers, and the only thing a unit is checked against before it runs
(ADR 0003): a manifest declares the series it was written for, and a mismatch is refused with both sides named
instead of failing somewhere inside a half-loaded unit.
"""

from __future__ import annotations

__api__ = "0.1"
