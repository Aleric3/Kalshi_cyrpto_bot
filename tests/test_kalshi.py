import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "scripts" / "collect_kalshi.py"
spec = importlib.util.spec_from_file_location("kalshi", path)
kalshi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kalshi)

START = datetime(2026, 11, 13, tzinfo=timezone.utc)
END = START + timedelta(days=1)


def market(series="KXBTC15M", result="yes", minute=15):
    return dict(ticker=f"{series}-TEST-{minute}", status="finalized", result=result,
                open_time=(START + timedelta(minutes=minute - 15)).isoformat(),
                close_time=(START + timedelta(minutes=minute)).isoformat())


class KalshiTests(unittest.TestCase):
    def test_pagination_deduplication_and_filtering(self):
        first = market()
        pending = dict(market(minute=45), status="active")
        out_of_range = market(minute=0)

        def fetch(params):
            self.assertEqual(params["series_ticker"], "KXBTC15M")
            self.assertEqual(params["min_close_ts"], int(START.timestamp()))
            if "cursor" not in params:
                return {"markets": [first, pending], "cursor": "next"}
            self.assertEqual(params["cursor"], "next")
            return {"markets": [first, market(result="no", minute=30), out_of_range], "cursor": ""}

        rows, pages = kalshi.collect_series("BTC", START, END, fetch)
        self.assertEqual(pages, 2)
        self.assertEqual([r["result"] for r in rows], ["yes", "no"])

    def test_repeated_cursor_fails(self):
        def fetch(_):
            return {"markets": [], "cursor": "same"}

        with self.assertRaisesRegex(ValueError, "Repeated cursor"):
            kalshi.collect_series("BTC", START, END, fetch)

    def test_conflicting_duplicate_fails(self):
        def fetch(_):
            return {"markets": [market(), market(result="no")], "cursor": ""}

        with self.assertRaisesRegex(ValueError, "Conflicting data"):
            kalshi.collect_series("BTC", START, END, fetch)

    def test_matches_only_shared_windows(self):
        rows = [
            dict(asset="BTC", close_utc="1", result="yes"),
            dict(asset="ETH", close_utc="1", result="yes"),
            dict(asset="XRP", close_utc="1", result="no"),
            dict(asset="BTC", close_utc="2", result="no"),
        ]
        results = kalshi.summarize(rows)["result_agreement"]
        self.assertEqual(results["BTC/ETH"], {"matched_windows": 1, "same_result": 1})
        self.assertEqual(results["BTC/XRP"], {"matched_windows": 1, "same_result": 0})
