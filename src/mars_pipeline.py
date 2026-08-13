"""USDA sheep & goat auction data pipeline.

Two access tiers:

1. **Keyless (works today).** USDA Market News publishes the *latest* version of
   several sheep reports as plain text at ``https://www.ams.usda.gov/mnreports/``.
   We download and parse them into tidy DataFrames. Each fetch is archived to
   ``data/mnreports/`` with a date stamp, so simply running this weekly (Task
   Scheduler / n8n) accumulates a history.

2. **Authenticated (free API key).** The MARS "My Market News" API serves the
   full *historical* archive of every auction report as structured JSON.
   Register at https://mymarketnews.ams.usda.gov (eAuth), click your name ->
   "Show API key", then either set the ``MARS_API_KEY`` environment variable or
   paste the key into a ``.mars_api_key`` file in the project root (gitignored).

Useful slug IDs (from the public listPublishedReports endpoint):

- 2014  Producers Livestock Sheep and Goat Auction - San Angelo, TX
- 1913  New Holland Sheep and Goat Auction - New Holland, PA
- 2153  Kalona Sheep and Goat Auction - Kalona, IA
- 1899  Centennial Livestock Sheep and Goat Auction - Fort Collins, CO
- SA_LS855  Weekly National Sheep Summary (text)
"""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
ARCHIVE_DIR = DATA_DIR / "mnreports"
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

TEXT_REPORTS = {
    "sa_ls850": "National Sheep Summary (daily)",
    "sa_ls855": "Weekly National Sheep Summary",
    "lm_lm352": "National Weekly Slaughter Sheep Review",
}

MARS_BASE = "https://marsapi.ams.usda.gov/services/v1.2"


# ---------------------------------------------------------------------------
# Tier 1: keyless text reports
# ---------------------------------------------------------------------------

def fetch_text_report(slug: str = "sa_ls855") -> str:
    """Download the latest text report and archive a dated copy."""
    url = f"https://www.ams.usda.gov/mnreports/{slug}.txt"
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    text = resp.text
    (ARCHIVE_DIR / f"{slug}_{date.today():%Y%m%d}.txt").write_text(text, encoding="utf-8")
    return text


_CATEGORY_RE = re.compile(r"^([A-Z][A-Za-z /]+):\s+(.*?):\s*$")
_MARKET_RE = re.compile(r"^\s{2,}([A-Za-z .&']+):\s{2,}(.+)$")
_ENTRY_RE = re.compile(
    r"(\d+)-(\d+)\s+lbs\s+(\d+(?:\.\d+)?)(?:-(\d+(?:\.\d+)?))?"
)


def parse_national_summary(text: str) -> pd.DataFrame:
    """Parse SA_LS855/SA_LS850 into tidy rows.

    Output columns: report_date, category, grade, market, weight_low_lbs,
    weight_high_lbs, price_low_cwt, price_high_cwt, price_mid_cwt.
    """
    m = re.search(r"for (?:week ending )?\w+day, (\w+ \d+, \d{4})", text)
    report_date = pd.to_datetime(m.group(1)) if m else pd.NaT

    rows = []
    category = grade = market = None
    buffer = ""

    def flush():
        nonlocal buffer
        if market and buffer:
            for w_lo, w_hi, p_lo, p_hi in _ENTRY_RE.findall(buffer):
                if int(w_hi) <= int(w_lo):  # source reports contain occasional typos
                    continue
                p_lo = float(p_lo)
                p_hi = float(p_hi) if p_hi else p_lo
                rows.append(
                    {
                        "report_date": report_date,
                        "category": category,
                        "grade": grade,
                        "market": market,
                        "weight_low_lbs": int(w_lo),
                        "weight_high_lbs": int(w_hi),
                        "price_low_cwt": p_lo,
                        "price_high_cwt": p_hi,
                        "price_mid_cwt": (p_lo + p_hi) / 2,
                    }
                )
        buffer = ""

    for line in text.splitlines():
        cat = _CATEGORY_RE.match(line)
        mkt = _MARKET_RE.match(line)
        if cat:
            flush()
            category, grade = cat.group(1).strip(), cat.group(2).strip()
            market = None
        elif mkt and category:
            flush()
            market = mkt.group(1).strip()
            buffer = mkt.group(2)
        elif market and line.startswith(" " * 8):
            buffer += " " + line.strip()  # wrapped continuation line
        elif not line.strip():
            flush()
            market = None
    flush()
    df = pd.DataFrame(rows)
    if not df.empty:
        # Drop malformed entries (typos in the source reports do occur)
        df = df[df["weight_high_lbs"] > df["weight_low_lbs"]].reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Tier 2: authenticated MARS API (full history)
# ---------------------------------------------------------------------------

def get_mars_key() -> str | None:
    key = os.environ.get("MARS_API_KEY")
    if key:
        return key.strip()
    key_file = PROJECT_ROOT / ".mars_api_key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    return None


def _mars_get(path: str, params: dict | None = None) -> dict | list:
    key = get_mars_key()
    if not key:
        raise RuntimeError(
            "No MARS API key found. Register (free) at "
            "https://mymarketnews.ams.usda.gov, click your name -> 'Show API "
            "key', then set MARS_API_KEY or create a .mars_api_key file in "
            "the project root."
        )
    resp = requests.get(
        f"{MARS_BASE}/{path.lstrip('/')}", params=params, auth=(key, ""), timeout=120
    )
    resp.raise_for_status()
    return resp.json()


def find_sheep_goat_reports() -> pd.DataFrame:
    """All MARS reports whose title mentions sheep, goat, or lamb."""
    reports = _mars_get("reports")
    df = pd.DataFrame(reports)
    mask = df["report_title"].str.contains("sheep|goat|lamb", case=False, na=False)
    return df[mask].reset_index(drop=True)


def fetch_auction_history(
    slug_id: str | int,
    begin: str,
    end: str,
    refresh: bool = False,
) -> pd.DataFrame:
    """Full structured history for one auction report.

    ``begin``/``end`` are MM/DD/YYYY strings. Cached per slug+range.
    """
    cache = DATA_DIR / f"mars_{slug_id}_{begin.replace('/', '')}_{end.replace('/', '')}.csv"
    if cache.exists() and not refresh:
        return pd.read_csv(cache)

    body = _mars_get(
        f"reports/{slug_id}",
        params={"q": f"report_begin_date={begin}:{end}", "allSections": "true"},
    )
    results = body.get("results", body) if isinstance(body, dict) else body
    df = pd.json_normalize(results)
    df.to_csv(cache, index=False)
    return df


if __name__ == "__main__":
    text = fetch_text_report("sa_ls855")
    parsed = parse_national_summary(text)
    print(f"Parsed {len(parsed)} price observations "
          f"from report dated {parsed['report_date'].iloc[0]:%Y-%m-%d}")
    print(parsed.head(12).to_string(index=False))
    print("\nMarkets:", sorted(parsed["market"].unique()))
    print("Categories:", sorted(parsed["category"].unique()))
    key = get_mars_key()
    print("\nMARS API key:", "found" if key else "not set (tier-2 history disabled)")
