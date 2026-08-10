# Meat Market Analysis: Futures Spreads & Demand Trends by Species

An applied agricultural-economics project answering two questions with free public data:

1. **How efficiently do US meat markets price proteins relative to each other, and how do
   farm-gate prices transmit to retail?** (`notebooks/01_futures_spreads.ipynb`)
2. **Which animal proteins — beef, pork, chicken, lamb/mutton/goat — are on a rising demand
   path, in the US and globally?** (`notebooks/02_demand_trends.ipynb`)

## Key findings

**Futures & spreads (2005–present)**
- Feeder cattle +230% and live cattle +145% since 2005, while lean hogs gained only ~10% —
  the slow cattle cycle vs the fast hog cycle, amplified by the post-2020 US herd contraction.
- The feeder–live spread (~120 ¢/lb vs ~35 ¢/lb long-run mean) signals historic calf scarcity;
  the cattle/hog ratio is ~2.5 standard deviations above its mean, making beef historically
  expensive relative to pork.
- The **real farm-to-retail spread widened +74% for ground beef** and +41% for bacon —
  an increasing share of the consumer dollar goes to processing/retail, not the producer.
- Futures lead retail prices by ~2 months for pork but ~5 months for beef, with modest
  correlations — retail meat prices are sticky.

**Demand by species (1961–2023, forecast to 2035)**
- **Chicken** is the unambiguous demand winner: rising consumption without falling real prices,
  in the US (+10% forecast by 2035) and globally (+19%).
- **Beef** demand is strong even though US per-capita volume is flat: the price-adjusted demand
  index (K-State methodology, elasticity-corrected) is up ~46% since 1997 — consumers keep
  absorbing record real prices.
- **Pork** demand is flat-to-modest, but has near-term substitution upside while beef is 2.5σ
  expensive relative to hogs.
- **Sheep & goat** is a niche-growth story: tiny US base (0.6 kg/person/yr) but the fastest US
  10-year growth rate of any meat (+2.7%/yr), and the second-fastest globally (+22% per-capita
  forecast by 2035) — demographic-driven demand with no futures contract and thin price data,
  i.e. a growing market that price-discovery infrastructure hasn't caught up with.

## Data sources (all free, no API keys)

| Source | Data | Access |
|---|---|---|
| CME via Yahoo Finance | Live cattle (LE=F), feeder cattle (GF=F), lean hogs (HE=F) daily futures, 2005–present | `yfinance` |
| FAO Food Balance Sheets via Our World in Data | Per-capita meat consumption by type and country, 1961–2023 | CSV endpoint |
| US Bureau of Labor Statistics | Retail prices (ground beef, chicken, bacon, pork chops) and CPI, 1997–present | public v1 API |

All downloads are cached to `data/`, so notebooks re-run offline after the first fetch.

## Methods

- Inter-commodity spread analysis (feeding-margin proxy, cattle/hog relative-value z-scores)
- Seasonality decomposition (calendar-month deviations from annual means)
- Farm-to-retail spread in real (CPI-deflated) terms
- Lead–lag cross-correlation for price transmission
- Price-adjusted demand indices following the Kansas State (Tonsor/Schroeder) methodology,
  with own-price elasticities from the ag-econ literature
- Holt damped-trend exponential smoothing forecasts to 2035 (`statsmodels`)

## Run it

```powershell
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace notebooks\01_futures_spreads.ipynb notebooks\02_demand_trends.ipynb
```

Or open the notebooks interactively with `jupyter lab`. Figures are saved to `outputs/figures/`.

## Structure

```
meat-market-analysis/
├── src/data_fetch.py        # cached fetchers: futures, FAO consumption, BLS prices
├── notebooks/
│   ├── 01_futures_spreads.ipynb   # spreads, seasonality, farm-to-retail basis, transmission
│   └── 02_demand_trends.ipynb     # consumption trends, demand indices, 2035 forecasts
├── data/                    # cached raw downloads (gitignored)
└── outputs/figures/         # exported charts (gitignored)
```

## Extensions

- True basis analysis with USDA AMS cash prices (free API key) instead of the retail proxy
- Split sheep vs goat using USDA slaughter statistics
- Estimate elasticities directly (2SLS with supply-side instruments) instead of literature values
- Panel demand model with income, price, and demographics; scenario forecasts vs USDA baseline
