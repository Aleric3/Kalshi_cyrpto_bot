"""Collect fixed-time public quotes and evaluate a chronological benchmark."""

import argparse
import csv
import hashlib
import json
import random
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from math import log
from pathlib import Path
from statistics import mean

from collect_kalshi import ENDPOINT, fetch_page

SPLIT = "2026-11-17T00:00:00+00:00"
MOMENTUM_WEIGHTS = (-1.0, -0.5, -0.25, 0.25, 0.5, 1.0)
CANDLES = ENDPOINT + "/candlesticks"
MAX_BATCH_SPAN = timedelta(hours=4)


def read_rows(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def get_batch(rows):
    close_by_ticker = {
        row["ticker"]: int(datetime.fromisoformat(row["close_utc"]).timestamp()) for row in rows
    }
    page = fetch_page(dict(market_tickers=",".join(close_by_ticker),
                           start_ts=min(close_by_ticker.values()) - 600,
                           end_ts=max(close_by_ticker.values()) - 300, period_interval=1), CANDLES)
    quotes = {}
    for market in page["markets"]:
        ticker = market["market_ticker"]
        close = close_by_ticker[ticker]
        candles = {bar["end_period_ts"]: bar for bar in market["candlesticks"]}
        if len(candles) != len(market["candlesticks"]) or ticker in quotes:
            raise ValueError(f"Duplicate candle data for {ticker}")
        snapshots = []
        for timestamp in (close - 600, close - 300):
            bar = candles.get(timestamp, {})
            bid = bar.get("yes_bid", {}).get("close_dollars")
            ask = bar.get("yes_ask", {}).get("close_dollars")
            snapshots.extend((bid, ask))
        quotes[ticker] = snapshots
    output = []
    for row in rows:
        values = quotes.get(row["ticker"], [None] * 4)
        output.append({**row, **dict(zip(("bid_10m", "ask_10m", "bid_5m", "ask_5m"), values))})
    return output


def collect(source):
    rows = sorted(read_rows(source), key=lambda r: (r["close_utc"], r["asset"]))
    if not rows or len({r["ticker"] for r in rows}) != len(rows):
        raise ValueError("Expected unique market tickers")
    # 36 contracts span about three hours with three assets per interval.
    batches = []
    batch = []
    for row in rows:
        if batch and (len(batch) == 36 or datetime.fromisoformat(row["close_utc"])
                      - datetime.fromisoformat(batch[0]["close_utc"]) > MAX_BATCH_SPAN):
            batches.append(batch)
            batch = []
        batch.append(row)
    if batch:
        batches.append(batch)
    with ThreadPoolExecutor(max_workers=3) as executor:
        return [row for group in executor.map(get_batch, batches) for row in group]


def clip(value):
    return max(0.01, min(0.99, value))


def probability_rows(rows):
    for row in rows:
        try:
            bid10, ask10, bid5, ask5 = (
                float(row[key]) for key in ("bid_10m", "ask_10m", "bid_5m", "ask_5m")
            )
        except (TypeError, ValueError):
            continue
        if 0 < bid10 <= ask10 < 1 and 0 < bid5 <= ask5 < 1:
            yield (row, (bid5 + ask5) / 2, (bid10 + ask10) / 2, int(row["result"] == "yes"))


def score(rows, weight):
    forecasts = [(y, clip(mid + weight * (mid - prior))) for _, mid, prior, y in rows]
    return {
        "brier": mean((p - y) ** 2 for y, p in forecasts),
        "log_loss": mean(-log(p if y else 1 - p) for y, p in forecasts),
        "direction_accuracy": mean((p >= 0.5) == bool(y) for y, p in forecasts),
    }


def brier_difference_interval(rows, weight):
    """Resample six-hour UTC blocks, keeping contemporaneous assets together."""
    blocks = {}
    for row, mid, prior, y in rows:
        block = int(datetime.fromisoformat(row["close_utc"]).timestamp()) // (6 * 3600)
        p = clip(mid + weight * (mid - prior))
        blocks.setdefault(block, []).append((p - y) ** 2 - (clip(mid) - y) ** 2)
    totals = [(sum(values), len(values)) for values in blocks.values()]
    rng = random.Random(7)
    draws = []
    for _ in range(4000):
        sample = rng.choices(totals, k=len(totals))
        draws.append(sum(total for total, _ in sample) / sum(count for _, count in sample))
    draws.sort()
    return {"blocks": len(totals), "low": draws[100], "high": draws[3899]}


def evaluate(rows):
    eligible = list(probability_rows(rows))
    dev = [r for r in eligible if r[0]["close_utc"] <= SPLIT]
    test = [r for r in eligible if r[0]["close_utc"] > SPLIT]
    if not dev or not test:
        raise ValueError("Expected eligible contracts on both sides of the split")
    scores = {w: score(dev, w)["brier"] for w in MOMENTUM_WEIGHTS}
    weight = min(scores, key=scores.get)
    return dict(split_close_utc=SPLIT, total_contracts=len(rows),
                development_eligible=len(dev), holdout_eligible=len(test),
                holdout_windows=len({r[0]["close_utc"] for r in test}),
                development_baseline=score(dev, 0), development_candidates=scores, selected_weight=weight,
                holdout_baseline=score(test, 0), holdout_model=score(test, weight),
                brier_model_minus_baseline_interval=brier_difference_interval(test, weight))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--markets", type=Path, help="Collect quotes from API for this markets.csv")
    source.add_argument("--quotes", type=Path, help="Replay a saved quote CSV offline")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.out_dir.exists():
        parser.error("Choose a new output directory")
    rows = collect(args.markets) if args.markets else read_rows(args.quotes)
    result = evaluate(rows)
    args.out_dir.mkdir(parents=True, exist_ok=False)
    output = args.out_dir / "quotes.csv"
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    result["quotes_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    report = json.dumps(result, indent=2) + "\n"
    (args.out_dir / "evaluation.json").write_text(report, encoding="utf-8")
    print(report, end="")


if __name__ == "__main__":
    main()
