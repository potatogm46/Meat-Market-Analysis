"""Data acquisition for the meat market analysis project.

Sources (all free, no API keys required):
- CME meat futures (continuous front-month) via Yahoo Finance:
    LE=F live cattle, GF=F feeder cattle, HE=F lean hogs  (all quoted cents/lb)
- Per-capita meat consumption by type via Our World in Data (FAO Food
  Balance Sheets): poultry, beef, pork, sheep & goat.
- US retail meat prices + CPI via the BLS public API (v1, keyless).

All fetchers cache to ``data/`` so notebooks re-run offline.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DATA_DIR.mkdir(exist_ok=True)

UA = {"User-Agent": "meat-market-analysis (student research project)"}


# ---------------------------------------------------------------------------
# Futures (Yahoo Finance)
# ---------------------------------------------------------------------------

FUTURES = {
    "LE=F": "live_cattle",
    "GF=F": "feeder_cattle",
    "HE=F": "lean_hogs",
}


def fetch_futures(start: str = "2005-01-01", refresh: bool = False) -> pd.DataFrame:
    """Daily settlement (close) prices in cents/lb, one column per contract."""
    cache = DATA_DIR / "meat_futures.csv"
    if cache.exists() and not refresh:
        return pd.read_csv(cache, index_col=0, parse_dates=True)

    import yfinance as yf

    frames = {}
    for ticker, name in FUTURES.items():
        hist = yf.Ticker(ticker).history(start=start, auto_adjust=False)
        if hist.empty:
            raise RuntimeError(f"No data returned for {ticker}")
        close = hist["Close"]
        close.index = pd.to_datetime(close.index).tz_localize(None)
        frames[name] = close
    df = pd.DataFrame(frames).sort_index()
    df.index.name = "date"
    df.to_csv(cache)
    return df


# ---------------------------------------------------------------------------
# Per-capita consumption (Our World in Data / FAO Food Balance Sheets)
# ---------------------------------------------------------------------------

OWID_SLUGS = [
    "per-capita-meat-type",
    "per-capita-meat-consumption-by-type-kilograms-per-year",
]

MEAT_KEYWORDS = {
    "poultry": "chicken_poultry",
    "beef": "beef",
    "bovine": "beef",
    "pig": "pork",
    "pork": "pork",
    "sheep": "sheep_goat",
    "mutton": "sheep_goat",
}


def fetch_owid_consumption(refresh: bool = False) -> pd.DataFrame:
    """Long dataframe: entity, year, meat, kg_per_capita (FAO food supply)."""
    cache = DATA_DIR / "owid_meat_consumption.csv"
    if cache.exists() and not refresh:
        return pd.read_csv(cache)

    last_err: Exception | None = None
    raw = None
    for slug in OWID_SLUGS:
        url = f"https://ourworldindata.org/grapher/{slug}.csv"
        try:
            resp = requests.get(url, headers=UA, timeout=60)
            resp.raise_for_status()
            from io import StringIO

            raw = pd.read_csv(StringIO(resp.text))
            break
        except Exception as exc:  # try next slug
            last_err = exc
    if raw is None:
        raise RuntimeError(f"Could not download OWID meat data: {last_err}")

    # Map indicator columns to canonical meat names via keyword match.
    col_map = {}
    for col in raw.columns:
        low = col.lower()
        for kw, name in MEAT_KEYWORDS.items():
            if kw in low and name not in col_map.values():
                col_map[col] = name
                break
    if not col_map:
        raise RuntimeError(f"Unrecognised OWID columns: {list(raw.columns)}")

    df = raw.rename(columns=col_map)
    keep = ["Entity", "Year"] + list(col_map.values())
    df = df[keep].melt(
        id_vars=["Entity", "Year"], var_name="meat", value_name="kg_per_capita"
    )
    df = df.rename(columns={"Entity": "entity", "Year": "year"}).dropna(
        subset=["kg_per_capita"]
    )
    df.to_csv(cache, index=False)
    return df


# ---------------------------------------------------------------------------
# BLS retail prices and CPI (public v1 API, no key, 10y per request)
# ---------------------------------------------------------------------------

BLS_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/"

BLS_SERIES = {
    "APU0000703112": "ground_beef_lb",
    "APU0000706111": "chicken_whole_lb",
    "APU0000704111": "bacon_lb",
    "APU0000FD3101": "pork_chops_boneless_lb",
    "CUUR0000SA0": "cpi_all_items",
}


def _bls_chunk(series_ids: list[str], start_year: int, end_year: int) -> list[dict]:
    payload = json.dumps(
        {
            "seriesid": series_ids,
            "startyear": str(start_year),
            "endyear": str(end_year),
        }
    )
    resp = requests.post(
        BLS_URL, data=payload, headers={"Content-type": "application/json"}, timeout=60
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("status") != "REQUEST_SUCCEEDED":
        raise RuntimeError(f"BLS API error: {body.get('message')}")
    return body["Results"]["series"]


def fetch_bls_prices(
    start_year: int = 1997, end_year: int = 2026, refresh: bool = False
) -> pd.DataFrame:
    """Monthly retail prices ($/lb) and CPI, one column per series."""
    cache = DATA_DIR / "bls_retail_prices.csv"
    if cache.exists() and not refresh:
        return pd.read_csv(cache, index_col=0, parse_dates=True)

    ids = list(BLS_SERIES)
    records: dict[str, dict[pd.Timestamp, float]] = {v: {} for v in BLS_SERIES.values()}
    year = start_year
    while year <= end_year:
        chunk_end = min(year + 9, end_year)
        for series in _bls_chunk(ids, year, chunk_end):
            name = BLS_SERIES[series["seriesID"]]
            for item in series["data"]:
                if not item["period"].startswith("M"):
                    continue
                ts = pd.Timestamp(int(item["year"]), int(item["period"][1:]), 1)
                try:
                    records[name][ts] = float(item["value"])
                except ValueError:
                    pass
        year = chunk_end + 1

    df = pd.DataFrame(records).sort_index()
    df.index.name = "date"
    df = df.dropna(how="all")
    df.to_csv(cache)
    return df


if __name__ == "__main__":
    fut = fetch_futures()
    print("futures:", fut.shape, fut.index.min().date(), "->", fut.index.max().date())
    print(fut.tail(3), "\n")

    cons = fetch_owid_consumption()
    print("consumption:", cons.shape)
    us = cons[cons["entity"] == "United States"]
    print(
        us.groupby("meat")["year"].agg(["min", "max", "count"]),
        "\n",
    )

    bls = fetch_bls_prices()
    print("bls:", bls.shape, bls.index.min().date(), "->", bls.index.max().date())
    print(bls.tail(3))
    print("non-null counts:\n", bls.notna().sum())
