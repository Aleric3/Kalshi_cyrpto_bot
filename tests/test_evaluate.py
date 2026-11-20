import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import evaluate_kalshi as evaluation


class EvaluationTests(unittest.TestCase):
    def test_selects_exact_premarket_close_offsets(self):
        row = dict(asset="BTC", ticker="TEST", close_utc="2026-11-13T00:15:00+00:00", result="yes")
        opened = 1794528000

        def bar(offset, price):
            quote = {"close_dollars": price}
            return dict(end_period_ts=opened + offset, yes_bid=quote, yes_ask=quote)

        response = {"markets": [{"market_ticker": "TEST", "candlesticks": [
            bar(300, "0.30"), bar(600, "0.55"), bar(900, "0.99"),
        ]}]}
        with patch.object(evaluation, "fetch_page", return_value=response) as fetch:
            result = evaluation.get_batch([row])[0]
        self.assertEqual(fetch.call_args.args[0]["end_ts"], opened + 600)
        self.assertEqual(result["bid_10m"], "0.30")
        self.assertEqual(result["ask_5m"], "0.55")

    def test_holdout_labels_do_not_change_weight(self):
        base = dict(asset="BTC", ticker="TEST", bid_10m="0.38", ask_10m="0.42",
                    bid_5m="0.58", ask_5m="0.62", result="yes")
        dev = {**base, "close_utc": evaluation.SPLIT}
        test = {**base, "close_utc": "2026-11-17T00:15:00+00:00"}
        first = evaluation.evaluate([dev, test])
        second = evaluation.evaluate([dev, {**test, "result": "no"}])
        self.assertEqual(first["selected_weight"], second["selected_weight"])
        self.assertNotEqual(first["holdout_model"], second["holdout_model"])

    def test_excludes_crossed_or_missing_quotes(self):
        rows = [
            dict(bid_10m="0.45", ask_10m="0.40", bid_5m="0.4", ask_5m="0.5"),
            dict(bid_10m="", ask_10m="0.40", bid_5m="0.4", ask_5m="0.5"),
        ]
        self.assertEqual(list(evaluation.probability_rows(rows)), [])
