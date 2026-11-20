"""Collect resolved 15-minute crypto markets from Kalshi's public Trade API."""

import argparse
import csv
import hashlib
import json
import time
from datetime import date, datetime, time as midnight, timedelta, timezone
from itertools import combinations
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ENDPOINT = "https://api.elections.kalshi.com/trade-api/v2/markets"
SERIES = {"BTC": "KXBTC15M", "ETH": "KXETH15M", "XRP": "KXXRP15M"}


def fetch_page(params, endpoint=ENDPOINT):
    request = Request(f"{endpoint}?{urlencode(params)}", headers={"Accept": "application/json"})
    for attempt in range(4):
        try:
            with urlopen(request, timeout=20) as response:
                return json.load(response)
        except (URLError, TimeoutError) as error:
            if attempt == 3 or (isinstance(error, HTTPError) and error.code not in {429, 500, 502, 503, 504}):
                raise
            time.sleep(2 ** attempt)


def collect_series(asset, start, end, fetch=fetch_page):
    series = SERIES[asset]
    params = dict(series_ticker=series, limit=100,
                  min_close_ts=int(start.timestamp()), max_close_ts=int(end.timestamp()) + 1)
    rows, windows, cursors = {}, set(), set()
    for page_count in range(1, 101):
        page = fetch(params.copy())
        for market in page["markets"]:
            result = market["result"]
            if market["status"] != "finalized" or result not in {"yes", "no"}:
                continue
            close = datetime.fromisoformat(market["close_time"].replace("Z", "+00:00"))
            opened = datetime.fromisoformat(market["open_time"].replace("Z", "+00:00"))
            if not start < close <= end or close - opened != timedelta(minutes=15):
                continue
            ticker = market["ticker"]
            if not ticker.startswith(series + "-"):
                raise ValueError(f"Unexpected ticker for {series}: {ticker}")
            row = dict(asset=asset, ticker=ticker, close_utc=close.astimezone(timezone.utc).isoformat(),
                       result=result)
            if ticker in rows:
                if row != rows[ticker]:
                    raise ValueError(f"Conflicting data for {ticker}")
                continue
            if close in windows:
                raise ValueError(f"Duplicate window for {series}: {close}")
            rows[ticker] = row
            windows.add(close)
        cursor = page.get("cursor")
        if not cursor:
            return list(rows.values()), page_count
        if cursor in cursors:
            raise ValueError(f"Repeated cursor for {series}")
        cursors.add(cursor)
        params["cursor"] = cursor
    raise ValueError(f"Page limit exceeded for {series}")


def summarize(rows):
    by_asset = {
        asset: {r["close_utc"]: r["result"] for r in rows if r["asset"] == asset}
        for asset in SERIES
    }
    agreement = {}
    for left, right in combinations(SERIES, 2):
        lhs, rhs = by_asset[left], by_asset[right]
        shared = lhs.keys() & rhs.keys()
        agreement[f"{left}/{right}"] = {
            "matched_windows": len(shared),
            "same_result": sum(lhs[t] == rhs[t] for t in shared),
        }
    return dict(contracts=len(rows),
                contracts_by_asset={asset: len(windows) for asset, windows in by_asset.items()},
                result_agreement=agreement)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.start >= args.end or args.out_dir.exists():
        parser.error("Choose an increasing UTC date range and a new output directory")
    start, end = [datetime.combine(d, midnight(), timezone.utc) for d in (args.start, args.end)]
    rows, pages = [], {}
    for asset in SERIES:
        batch, pages[asset] = collect_series(asset, start, end)
        rows.extend(batch)
    if not rows:
        parser.error("No finalized contracts found in the selected window")
    rows.sort(key=lambda r: (r["close_utc"], r["asset"]))
    args.out_dir.mkdir(parents=True, exist_ok=False)
    csv_path = args.out_dir / "markets.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    result = dict(source=ENDPOINT, start_exclusive=start.isoformat(), end_inclusive=end.isoformat(),
                  retrieved_utc=datetime.now(timezone.utc).isoformat(), pages_by_asset=pages,
                  expected_windows_per_asset=int((end - start).total_seconds() // 900),
                  csv_sha256=hashlib.sha256(csv_path.read_bytes()).hexdigest(), **summarize(rows))
    report = json.dumps(result, indent=2) + "\n"
    (args.out_dir / "summary.json").write_text(report, encoding="utf-8")
    print(report, end="")


if __name__ == "__main__":
    main()
