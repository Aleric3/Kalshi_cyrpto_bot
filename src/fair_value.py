from __future__ import annotations

from dataclasses import dataclass
from math import erf, sqrt


@dataclass
class FairValueInput:
    asset: str
    current_price: float
    reference_price: float
    seconds_remaining: float
    recent_volatility: float
    momentum: float = 0.0


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def estimate_up_probability(inp: FairValueInput) -> float:
    """Estimate P(final_price > reference_price) for a short binary market.

    This is intentionally simple and interpretable. It is not a production model.
    """
    if inp.reference_price <= 0 or inp.current_price <= 0:
        return 0.50

    seconds = max(inp.seconds_remaining, 1.0)
    vol = max(inp.recent_volatility, 1e-6)

    distance_pct = (inp.current_price - inp.reference_price) / inp.reference_price
    time_scale = sqrt(seconds / 900.0)  # 900 seconds = 15 minutes
    z_score = (distance_pct + 0.25 * inp.momentum) / (vol * time_scale)

    probability = normal_cdf(z_score)
    return max(0.01, min(0.99, probability))
