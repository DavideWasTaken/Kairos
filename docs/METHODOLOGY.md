# Methodology and limitations

## Historical analogs

The standard analog compares the latest 90 trading observations with rolling historical windows. The seasonal view uses 60 observations and a day-of-year constraint on the historical end date, initially exact and with a one-day fallback. The API reports the matching dates and correlation.

Windows are ranked by Pearson correlation of closing-price levels. The following 60 historical observations are displayed as a continuation. Both the candidate window and its continuation must precede the current window. This avoids overlap with that current window, but does not constitute an out-of-sample evaluation of a trading strategy.

Selection across many windows introduces selection bias. Price-level correlation, changing market regimes, provider adjustments and calendar differences can all affect interpretation. Correlation is not a success probability.

## Technical calculations

Technical indicators use available OHLCV observations. The loader preserves Open, High, Low, Close and Volume for either supported single-symbol Yahoo MultiIndex layout. RSI reports 100 when the observation window only rises, 0 when it only falls, and 50 when it is flat. Missing or insufficient history can make an indicator unavailable.

## Composite heuristic

The API retains the `model_confidence` field for compatibility, while the interface identifies it as a heuristic score. The component weights are:

| Component | Weight |
| --- | ---: |
| Valuation | 34% |
| Technical | 24% |
| Data quality | 22% |
| Estimate revisions | 12% |
| News/social | 8% |

Thresholds and weights are manual. A missing component is exposed as `null` and contributes a neutral 50 to a partial weighted score. `missing_components` and `observed_weight` disclose coverage. No score is returned if every component is unavailable; a genuine quality score of zero remains zero. None of these values is calibrated against future returns.

The offline demo intentionally supplies no composite score, even though technical indicators are available, because its purpose is demonstrating the interface and calculation paths with synthetic prices.

## Valuation scenarios

DCF projects available free cash flow over a finite horizon and adds a discounted terminal value. Profiles change growth, discount-rate and terminal-growth assumptions. The implementation also makes simplifying assumptions around cash-flow normalization, capital structure and valuation adjustments. The API and interface expose applied inputs, scenario assumptions and limitations.

These calculations are sensitive to incomplete statements, non-recurring cash flows, units, share counts and assumptions. Some asset types lack suitable fundamentals. Compare the assumptions and provider data before interpreting an output; unavailable inputs do not establish that an asset is cheap or expensive.

## Insider records

Only transaction descriptions that explicitly indicate a purchase count as buys. Positive shares alone do not establish a purchase: grants, gifts, awards, vesting and unknown acquisitions are excluded. The requested lookback is passed through to retrieval and filtering. Summary counts are computed before the display limit; individual rows or purchase values may still be unavailable from the provider.

Market-segment scans disclose the scanned universe and its source. A curated fallback universe is incomplete. Reported activity is neither a complete market census nor a trading recommendation.

## Chat

Supported requests route to deterministic data retrieval and calculations. Responses expose the actual observation period, source and structured metrics. Numerical text is formatted directly from those metrics; missing values appear as unavailable.

An optional model call may select the matching predefined qualitative explanation. Only the expected JSON key and allowed value are accepted; other prose or claims are discarded. `used_llm` is true only when a valid explanation is accepted. It is a constrained explanation selector, not a general investment adviser.

The demo supports fixture returns and correlation over the full fixed fixture period. It explicitly reports that period rather than pretending to satisfy arbitrary live-data timeframes. Fundamentals, news and insider requests are unavailable in the demo.
