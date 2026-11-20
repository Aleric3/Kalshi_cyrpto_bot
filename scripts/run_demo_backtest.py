from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from config import BotConfig
from fair_value import FairValueInput, estimate_up_probability
from fill_model import simulate_fill
from paper_trader import PaperTrader
from strategy_modes import MarketSnapshot, generate_signal


STARTING_CASH = 100.0
REQUESTED_SIZE = 0.25
SCENARIOS = (
    ("quoted", "optimistic", 0.0, 0.0),
    ("base", "realistic", 0.50, 0.002),
    ("stress", "pessimistic", 0.50, 0.010),
)


def synthetic_snapshot(asset: str, i: int, rng: random.Random) -> tuple[MarketSnapshot, float]:
    reference = {"BTC": 100_000, "ETH": 4_000, "XRP": 2.50}[asset]
    current = reference * (1 + rng.gauss(0, 0.002))
    seconds_remaining = rng.randint(45, 850)
    vol = rng.uniform(0.001, 0.004)
    momentum = rng.gauss(0, 0.001)

    fair_up = estimate_up_probability(
        FairValueInput(asset, current, reference, seconds_remaining, vol, momentum)
    )

    # Synthetic market prices with noise so some opportunities appear.
    up_ask = max(0.01, min(0.99, fair_up + rng.gauss(-0.015, 0.045)))
    down_ask = max(0.01, min(0.99, (1 - fair_up) + rng.gauss(-0.015, 0.045)))

    # Inject occasional cheap-tail setups.
    if i % 35 == 0:
        if rng.random() < 0.5:
            up_ask = rng.uniform(0.01, 0.03)
        else:
            down_ask = rng.uniform(0.01, 0.03)

    terminal_distance = (current / reference - 1) + rng.gauss(0, vol * (seconds_remaining / 900) ** 0.5)
    return MarketSnapshot(asset, seconds_remaining, up_ask, down_ask, fair_up, momentum), terminal_distance


def run(seed: int, out_dir: Path) -> dict:
    market_rng = random.Random(seed)
    config = BotConfig()
    markets = [
        synthetic_snapshot(market_rng.choice(("BTC", "ETH", "XRP")), i, market_rng)
        for i in range(180)
    ]
    rows = []
    summaries = {}
    for name, mode, miss_prob, fee_rate in SCENARIOS:
        execution_rng = random.Random(seed + 1)
        scenario = replace(config, fill_model_mode=mode, competition_miss_prob=miss_prob)
        trader = PaperTrader(scenario, STARTING_CASH)
        buy_count = filled_orders = 0
        contracts = fees = slippage = quoted_cost = payouts = 0.0
        for i, (snapshot, terminal_distance) in enumerate(markets):
            market_id = f"synthetic-{i:03d}"
            winner = "UP" if terminal_distance > 0 else "DOWN"
            signal = generate_signal(snapshot, config)
            fill = simulate_fill(signal, scenario, REQUESTED_SIZE, rng=execution_rng)
            size, fee = trader.apply_fill(market_id, signal, fill, fee_rate)
            payout = trader.settle(market_id, winner)
            price = fill.fill_price if size else None
            quoted = (signal.market_price or 0.0) * size
            impact = (price or 0.0) * size - quoted
            buy_count += signal.action == "BUY"
            filled_orders += size > 0
            contracts += size
            fees += fee
            slippage += impact
            quoted_cost += quoted
            payouts += payout
            rows.append(dict(
                scenario=name, market_id=market_id, asset=snapshot.asset,
                fair_up=snapshot.fair_up, up_ask=snapshot.up_ask, down_ask=snapshot.down_ask,
                seconds_remaining=snapshot.seconds_remaining, winner=winner,
                action=signal.action, side=signal.side, strategy=signal.strategy_mode,
                quoted_edge=signal.edge, quote=signal.market_price, fill_price=price,
                size=size, fee=fee, slippage=impact, payout=payout, cash=trader.cash,
                reason=fill.missed_reason or ("cash or position limit" if not size else ""),
            ))
        summaries[name] = dict(
            buy_signals=buy_count, filled_orders=filled_orders,
            order_fill_rate=filled_orders / buy_count if buy_count else 0.0,
            filled_contracts=contracts,
            quantity_fill_rate=contracts / (buy_count * REQUESTED_SIZE) if buy_count else 0.0,
            quoted_cost=quoted_cost, fees=fees, slippage=slippage, payouts=payouts,
            ending_cash=trader.cash, net_simulated_pnl=trader.cash - STARTING_CASH,
            competition_miss_probability=miss_prob, fee_per_contract=fee_rate,
            fill_model=mode,
        )
    metrics = dict(data="synthetic", seed=seed, snapshots=len(markets),
                   starting_cash=STARTING_CASH, requested_contracts=REQUESTED_SIZE,
                   scenarios=summaries)
    out_dir.mkdir(parents=True, exist_ok=False)
    with (out_dir / "trades.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the offline synthetic crypto market study")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        metrics = run(args.seed, args.out_dir)
    except FileExistsError:
        parser.error("Choose a new output directory")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
