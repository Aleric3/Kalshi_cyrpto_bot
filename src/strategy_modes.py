from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from config import BotConfig

Side = Literal["UP", "DOWN"]
Action = Literal["BUY", "HOLD", "NO_TRADE", "TAKE_PROFIT", "STOP_LOSS"]
StrategyMode = Literal[
    "early_market_making",
    "directional_reallocation",
    "cheap_tail_reversal",
    "no_trade",
]


@dataclass
class MarketSnapshot:
    asset: str
    seconds_remaining: float
    up_ask: float
    down_ask: float
    fair_up: float
    recent_move: float


@dataclass
class StrategySignal:
    asset: str
    side: Side | None
    action: Action
    strategy_mode: StrategyMode
    market_price: float | None
    fair_value: float | None
    edge: float
    reason: str


def generate_signal(snapshot: MarketSnapshot, config: BotConfig) -> StrategySignal:
    """Generate a paper-trading signal from one market snapshot."""
    fair_down = 1.0 - snapshot.fair_up
    edge_up = snapshot.fair_up - snapshot.up_ask
    edge_down = fair_down - snapshot.down_ask

    # Cheap-tail setup: asymmetric payoff when a nearly-dead side is still plausibly alive.
    if 0.01 <= snapshot.up_ask <= 0.03 and edge_up >= config.divergence_threshold:
        return StrategySignal(snapshot.asset, "UP", "BUY", "cheap_tail_reversal", snapshot.up_ask, snapshot.fair_up, edge_up, "cheap UP tail appears underpriced")

    if 0.01 <= snapshot.down_ask <= 0.03 and edge_down >= config.divergence_threshold:
        return StrategySignal(snapshot.asset, "DOWN", "BUY", "cheap_tail_reversal", snapshot.down_ask, fair_down, edge_down, "cheap DOWN tail appears underpriced")

    # Directional reallocation: stronger side has clear edge.
    if edge_up >= config.divergence_threshold and edge_up >= edge_down:
        return StrategySignal(snapshot.asset, "UP", "BUY", "directional_reallocation", snapshot.up_ask, snapshot.fair_up, edge_up, "UP is cheap relative to model fair value")

    if edge_down >= config.divergence_threshold:
        return StrategySignal(snapshot.asset, "DOWN", "BUY", "directional_reallocation", snapshot.down_ask, fair_down, edge_down, "DOWN is cheap relative to model fair value")

    return StrategySignal(snapshot.asset, None, "NO_TRADE", "no_trade", None, None, max(edge_up, edge_down), "no edge above threshold")
