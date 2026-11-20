from dataclasses import dataclass, field

from config import BotConfig
from fill_model import FillResult
from strategy_modes import Side, StrategySignal


@dataclass
class PaperTrader:
    config: BotConfig
    cash: float
    positions: dict[tuple[str, Side], float] = field(default_factory=dict, init=False)
    settled: set[str] = field(default_factory=set, init=False)

    def apply_fill(
        self, market_id: str, signal: StrategySignal, fill: FillResult, fee_per_contract: float
    ) -> tuple[float, float]:
        if market_id in self.settled:
            raise ValueError(f"Market already settled: {market_id}")
        if not fill.filled or signal.action != "BUY" or signal.side is None:
            return 0.0, 0.0
        if fill.fill_price is None or not 0 < fill.fill_price <= 1 or not fee_per_contract >= 0:
            raise ValueError("Invalid fill price or fee")
        key = (market_id, signal.side)
        current = self.positions.get(key, 0.0)
        unit_cost = fill.fill_price + fee_per_contract
        size = max(0.0, min(fill.filled_size, self.config.max_position_size - current, self.cash / unit_cost))
        if size:
            self.positions[key] = current + size
            self.cash = max(0.0, self.cash - size * unit_cost)
        return size, size * fee_per_contract

    def settle(self, market_id: str, winner: Side) -> float:
        if market_id in self.settled:
            raise ValueError(f"Market already settled: {market_id}")
        if winner not in ("UP", "DOWN"):
            raise ValueError("Invalid settlement side")
        up = self.positions.pop((market_id, "UP"), 0.0)
        down = self.positions.pop((market_id, "DOWN"), 0.0)
        payout = up if winner == "UP" else down
        self.cash += payout
        self.settled.add(market_id)
        return payout
