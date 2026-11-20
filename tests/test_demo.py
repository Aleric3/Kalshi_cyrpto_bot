import importlib.util
import tempfile
import unittest
from pathlib import Path

DEMO = Path(__file__).resolve().parents[1] / "scripts" / "run_demo_backtest.py"
spec = importlib.util.spec_from_file_location("demo", DEMO)
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)

from fill_model import FillResult
from strategy_modes import StrategySignal


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.signal = StrategySignal("BTC", "UP", "BUY", "directional_reallocation",
                                     0.4, 0.6, 0.2, "fixture")
        self.fill = FillResult(True, 0.4, 0.75, None, 0)

    def test_market_limits_and_settlement(self):
        trader = demo.PaperTrader(demo.BotConfig(), 10)
        self.assertEqual(trader.apply_fill("a", self.signal, self.fill, 0.01)[0], 0.75)
        self.assertEqual(trader.apply_fill("a", self.signal, self.fill, 0.01)[0], 0.25)
        self.assertEqual(trader.apply_fill("b", self.signal, self.fill, 0.01)[0], 0.75)
        self.assertEqual(trader.settle("a", "UP"), 1)
        self.assertEqual(trader.settle("b", "DOWN"), 0)
        self.assertAlmostEqual(trader.cash, 10 + 1 - 1.75 * 0.41)
        self.assertFalse(trader.positions)
        with self.assertRaises(ValueError):
            trader.settle("a", "UP")
        with self.assertRaises(ValueError):
            trader.apply_fill("a", self.signal, self.fill, 0)

    def test_cash_limit(self):
        trader = demo.PaperTrader(demo.BotConfig(), 0.2)
        self.assertEqual(trader.apply_fill("a", self.signal, self.fill, 0)[0], 0.5)
        self.assertEqual(trader.cash, 0)
        self.assertEqual(trader.apply_fill("b", self.signal, self.fill, 0)[0], 0)

    def test_missed_fill_has_no_cost(self):
        trader = demo.PaperTrader(demo.BotConfig(), 10)
        missed = FillResult(False, None, 0, "miss", 0)
        self.assertEqual(trader.apply_fill("a", self.signal, missed, 0.1), (0, 0))
        self.assertEqual(trader.cash, 10)


class DemoTests(unittest.TestCase):
    def test_reproducible_and_reconciled(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            result = demo.run(7, a)
            self.assertEqual(result, demo.run(7, b))
            for name in ("trades.csv", "metrics.json"):
                self.assertEqual((a / name).read_bytes(), (b / name).read_bytes())
            before = (a / "metrics.json").read_bytes()
            with self.assertRaises(FileExistsError):
                demo.run(8, a)
            self.assertEqual(before, (a / "metrics.json").read_bytes())
            scenarios = result["scenarios"]
            self.assertEqual(scenarios["base"]["filled_contracts"],
                             scenarios["stress"]["filled_contracts"])
            self.assertEqual(scenarios["quoted"]["order_fill_rate"], 1)
            for row in scenarios.values():
                pnl = row["payouts"] - row["quoted_cost"] - row["slippage"] - row["fees"]
                self.assertAlmostEqual(row["net_simulated_pnl"], pnl)
