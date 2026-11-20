# Historical Kalshi quote benchmark

The benchmark uses the 1,992 contracts in the saved November 13–20, 2026 UTC market study. For each ticker it takes the closing YES bid and ask from one-minute Kalshi candlesticks ending exactly ten and five minutes before market close. Both snapshots must have a valid two-sided quote strictly inside the probability bounds. The analysis uses finalized YES/NO only as the label.

Five minutes before close, the baseline is the YES midpoint. The experimental forecast adjusts it by a multiple of the midpoint change over the prior five minutes. Both probabilities are clipped to [0.01, 0.99]. The candidate weights are −1, −0.5, −0.25, +0.25, +0.5, and +1. The zero-weight midpoint is scored separately as the benchmark. The script minimizes Brier score among the nonzero candidates on contracts closing through November 17 at 00:00 UTC and freezes the weight before scoring the later contracts. The matched holdout reports Brier score, log loss, and direction accuracy. Brier and log loss are lower-is-better. Direction accuracy treats probabilities of 0.50 as YES.

The best development adjustment also trailed the midpoint on the development sample. On the holdout its Brier loss rose by 0.00558. A paired percentile bootstrap over six-hour UTC blocks (4,000 draws, seed 7) gave an approximate 95% interval of +0.00205 to +0.00854 for model minus midpoint Brier loss. There are only 13 blocks, and dependence can persist across block boundaries.

The quote signal was added for this benchmark. The original spot-based fair-value model requires a separate historical price feed aligned to the contract settlement reference. The benchmark uses public quote data and measures forecast quality. It has no fill, latency, fee, or executed-return model. The short sample and overlapping asset exposure limit generalization.

## Reproduce

```sh
python scripts/evaluate_kalshi.py --quotes docs/kalshi_quote_sample.csv --out-dir runs/benchmark
```

To retrieve fresh quotes for the same contract set, run the market collector for the dates in the README, then use `--markets runs/kalshi-week/markets.csv` in place of `--quotes`. The public [batch candlestick endpoint](https://docs.kalshi.com/api-reference/market/batch-get-market-candlesticks) provides the one-minute quote bars.
