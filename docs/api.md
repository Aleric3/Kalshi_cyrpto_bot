# Kalshi market data

The collector uses Kalshi’s public [Get Markets endpoint](https://docs.kalshi.com/api-reference/market/get-markets), querying `KXBTC15M`, `KXETH15M`, and `KXXRP15M` separately. It requests a UTC close-time range, follows cursor pagination, and uses bounded exponential backoff for rate-limit responses and transient server or transport errors.

The analysis counts intervals that close after the start midnight and at or before the end midnight. It keeps finalized YES/NO contracts whose open-to-close interval is exactly 15 minutes. The collector deduplicates tickers and rejects conflicting duplicates, repeated cursors, and multiple contracts for the same asset and close time.

`markets.csv` contains asset, market ticker, UTC close time, and final result. `summary.json` includes collection timestamps, page counts, observed and expected coverage, paired result agreement, and a SHA-256 hash of the normalized CSV. Pair agreement counts matching YES/NO outcomes only where both assets have a finalized contract with the same close time.

If the requested market data has moved beyond the provider’s current data cutoff, consult Kalshi’s [historical data documentation](https://docs.kalshi.com/getting_started/historical_data).
