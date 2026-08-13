# Meat Market Analysis: Futures Spreads, Demand Trends & Sheep/Goat Price Index

Applied agricultural-economics project in three notebooks:

1. **Futures spreads & farm-to-retail basis** — cattle vs hogs, price transmission (`01`)
2. **Demand by species** — beef, pork, chicken, sheep/goat to 2035 (`02`)
3. **US sheep & goat price index** — the price-discovery gap, reconstructed (`03`)

Notebook 03 is the concrete step toward *fixing* the inefficiency: packaging fragmented
USDA AMS auction reports into a continuous national lamb index, regional basis, and a
goat-vs-lamb auction snapshot.

## Key findings

**Futures & spreads (2005–present)**
- Feeder cattle +230% and live cattle +145% since 2005; lean hogs only ~+10%.
- Feeder–live spread near historic extremes (~120 ¢/lb vs ~35 ¢/lb mean); cattle/hog
  ratio ~2.5σ expensive — favors substitution toward pork/poultry.
- Real farm-to-retail spread widened +74% for ground beef and +41% for bacon.

**Demand by species (1961–2023 → 2035)**
- **Chicken** is the clearest demand winner (US +10%, world +19% by 2035).
- **Beef** demand index +46% since 1997 even with flat per-capita volume.
- **Sheep & goat** — tiny US base (0.6 kg/person) but fastest US 10y growth (+2.7%/yr)
  and #2 globally (+22% forecast). Growing demand, thin price infrastructure.

**Price discovery (notebook 03)**
- Reconstructed a **national slaughter-lamb index** from AMS SA_LS855 (live + Wayback
  snapshots, 2000–present). Latest reading ~$296/cwt across 5 markets.
- **Regional basis** shows large, persistent gaps (e.g. Missouri recently ~$80/cwt
  under the national average) — the actionable signal for producers.
- **Goat vs lamb** at the two largest rings (same week): goats trade at ~78–86% of
  sheep/lamb prices (San Angelo $251 vs $324; New Holland $254 vs $297), with no
  national goat summary equivalent to SA_LS855.

## Data sources

| Source | Data | Key? |
|---|---|---|
| CME via Yahoo Finance | Live cattle, feeder cattle, lean hogs futures | No |
| FAO / Our World in Data | Per-capita meat consumption by type | No |
| BLS public API | Retail meat prices + CPI | No |
| USDA AMS SA_LS855 + Wayback Machine | Weekly National Sheep Summary (text) | No |
| USDA AMS auction PDFs | San Angelo (2014), New Holland (1913) graded lots | No |
| My Market News / MARS API | Optional structured history | Free key (optional) |

## Run it

```powershell
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m jupyter nbconvert --to notebook --execute --inplace `
  notebooks\01_futures_spreads.ipynb `
  notebooks\02_demand_trends.ipynb `
  notebooks\03_sheep_goat_price_index.ipynb
```

Notebook 03’s first run downloads Wayback snapshots (a few minutes); later runs use `data/`.

Optional: copy `.env.example` → `.env` and add a free `MARS_API_KEY` from
[My Market News](https://mymarketnews.ams.usda.gov/) for structured API access.

## Structure

```
meat-market-analysis/
├── src/
│   ├── data_fetch.py      # futures, FAO, BLS
│   └── ams_reports.py     # SA_LS855 + auction PDFs → index/basis
├── notebooks/
│   ├── 01_futures_spreads.ipynb
│   ├── 02_demand_trends.ipynb
│   └── 03_sheep_goat_price_index.ipynb
├── outputs/
│   ├── lamb_national_index.csv
│   ├── lamb_market_basis.csv
│   ├── major_auction_lots_latest.csv
│   └── figures/
└── .env.example
```

## Publish this as a portfolio repo

Don’t wait — ship notebooks 01–03 together. This folder is self-contained; init git
**inside** `meat-market-analysis/` (not the parent TableFlow app).

```powershell
cd meat-market-analysis
git init
git add .
git status   # confirm .venv, .env, data/ caches are NOT staged
git commit -m "Add meat market spreads, demand trends, and sheep/goat price index"
gh repo create meat-market-analysis --public --source=. --remote=origin --push
```

Then put the repo URL on your resume next to the project bullets.

## Next product steps

- Weekly cron to append new SA_LS855 + San Angelo/New Holland goat lots
- Archive goat lots into a continuous goat index (the thinner, higher-leverage series)
- Free MARS key for cleaner history; outreach to LMIC / American Sheep Industry / Lamb Board
  with `outputs/lamb_national_index.csv` + figure 11
