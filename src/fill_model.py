from __future__ import annotations

from dataclasses import dataclass
import random

from config import BotConfig
from strategy_modes import StrategySignal


@dataclass
class FillResult:
    filled: bool
    fill_price: float | None
    filled_size: float
    missed_reason: str | None
    slippage_pct: float


def simulate_fill(signal: StrategySignal, config: BotConfig, requested_size: float = 1.0, *, rng: random.Random) -> FillResult:
    """Simulate whether a paper signal would fill.

    This is deliberately conservative enough to remind reviewers that visible edge is not
    the same as executable edge.
    """
    if signal.action != "BUY" or signal.market_price is None:
        return FillResult(False, None, 0.0, "no buy action", 0.0)

    # Competition: large obvious edges are more likely to disappear before our order arrives.
    if signal.edge >= 0.08 and rng.random() < config.competition_miss_prob:
        return FillResult(False, None, 0.0, "competition missed fill", 0.0)

    if config.fill_model_mode == "optimistic":
        return FillResult(True, signal.market_price, requested_size, None, 0.0)

    slippage = config.default_slippage_bps / 10_000
    if config.fill_model_mode == "pessimistic":
        slippage *= 2.0

    fill_price = min(0.99, signal.market_price * (1.0 + slippage))

    # Simple partial-fill assumption for the demo.
    filled_size = requested_size
    if config.fill_model_mode in {"realistic", "pessimistic"} and rng.random() < 0.20:
        filled_size = requested_size * 0.50

    return FillResult(True, fill_price, filled_size, None, fill_price / signal.market_price - 1.0)
