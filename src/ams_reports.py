"""USDA AMS sheep & goat auction report acquisition and parsing.

Primary source (no API key required):
  Weekly National Sheep Summary (SA_LS855) — current AMS text report plus
  Internet Archive Wayback Machine snapshots (~2000–present).

Secondary source (no API key required):
  Individual auction PDFs for San Angelo (AMS_2014) and New Holland (AMS_1913),
  which include graded goat lots that the national sheep summary omits.

Optional:
  My Market News / MARS API — set MARS_API_KEY in the environment (or .env)
  to pull structured historical series. Registration is free at
  https://mymarketnews.ams.usda.gov/
"""

from __future__ import annotations

import json
import os
import re
import time
from io import BytesIO
from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
RAW_DIR = DATA_DIR / "mnreports"
RAW_DIR.mkdir(parents=True, exist_ok=True)

UA = {"User-Agent": "meat-market-analysis (student research; contact via GitHub)"}
AMS_TXT = "https://www.ams.usda.gov/mnreports/sa_ls855.txt"
AUCTION_PDFS = {
    "san_angelo": "https://www.ams.usda.gov/mnreports/ams_2014.pdf",
    "new_holland": "https://www.ams.usda.gov/mnreports/ams_1913.pdf",
}

# Canonical market names appearing in SA_LS855
MARKET_ALIASES = {
    "san angelo": "San Angelo",
    "new holland": "New Holland",
    "new holland, pa": "New Holland",
    "billings": "Billings",
    "ft. collins": "Ft. Collins",
    "ft. col1ins": "Ft. Collins",  # OCR/typo seen in reports
    "fort collins": "Ft. Collins",
    "mount hope": "Mount Hope",
    "kalona": "Kalona",
    "sioux falls": "Sioux Falls",
    "equity coop": "Equity Coop",
    "equity cooperative": "Equity Coop",
    "midwest": "Midwest",
    "eastern area": "Eastern Area",
    "south dakota": "South Dakota",
    "missouri": "Missouri",
    "buffalo, mo": "Buffalo MO",
    "arkansas": "Arkansas",
}

SECTION_PATTERNS = [
    (re.compile(r"^slaughter\s+lambs", re.I), "slaughter_lambs"),
    (re.compile(r"^slaughter\s+ewes", re.I), "slaughter_ewes"),
    (re.compile(r"^feeder\s+lambs", re.I), "feeder_lambs"),
    (re.compile(r"^replacement\s+ewes", re.I), "replacement_ewes"),
]

DATE_PATTERNS = [
    re.compile(
        r"week ending\s+\w+,\s+([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})", re.I
    ),
    re.compile(
        r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})",
        re.I,
    ),
]

# weight band + price: "80-90 lbs 297.00" or "90-145 lbs 105.00-114.50"
QUOTE_RE = re.compile(
    r"(?P<wlo>\d{2,3})\s*-\s*(?P<whi>\d{2,3})\s*lbs?\s+"
    r"(?P<p1>\d+(?:\.\d+)?)\s*(?:-\s*(?P<p2>\d+(?:\.\d+)?))?",
    re.I,
)
# price-only fallback when weight is stated at section level: "105.00-114.50"
PRICE_ONLY_RE = re.compile(
    r"(?<![\d.])(?P<p1>\d{2,3}(?:\.\d{2})?)\s*-\s*(?P<p2>\d{2,3}(?:\.\d{2})?)"
)


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(UA)
    return s


def _get(session: requests.Session, url: str, retries: int = 4) -> requests.Response:
    last: Exception | None = None
    for i in range(retries):
        try:
            r = session.get(url, timeout=90)
            if r.status_code in (429, 503):
                time.sleep(2 + i * 2)
                continue
            r.raise_for_status()
            return r
        except Exception as exc:
            last = exc
            time.sleep(1.5 + i)
    raise RuntimeError(f"Failed to GET {url}: {last}")


# ---------------------------------------------------------------------------
# SA_LS855: current + Wayback history
# ---------------------------------------------------------------------------

def fetch_wayback_cdx(refresh: bool = False) -> list[tuple[str, str]]:
    """Return [(timestamp, original_url), ...] for successful SA_LS855 snapshots."""
    cache = DATA_DIR / "wayback_cdx_sa_ls855.json"
    if cache.exists() and not refresh:
        rows = json.loads(cache.read_text(encoding="utf-8"))
        return [(r[0], r[1]) for r in rows]

    session = _session()
    r = _get(
        session,
        "https://web.archive.org/cdx/search/cdx?"
        + "url=www.ams.usda.gov/mnreports/sa_ls855.txt"
        + "&output=json&fl=timestamp,original,statuscode"
        + "&filter=statuscode:200&collapse=timestamp:8",
    )
    rows = r.json()[1:]
    cache.write_text(json.dumps(rows), encoding="utf-8")
    return [(r[0], r[1]) for r in rows]


def fetch_sa_ls855_texts(
    max_snapshots: int | None = None,
    refresh: bool = False,
    pause: float = 0.8,
) -> list[tuple[pd.Timestamp | None, str, str]]:
    """Download current + historical SA_LS855 texts.

    Returns list of (approx_date_from_archive, source_label, text).
    """
    session = _session()
    out: list[tuple[pd.Timestamp | None, str, str]] = []

    # Always pull the live report
    live_path = RAW_DIR / "sa_ls855_latest.txt"
    if refresh or not live_path.exists():
        text = _get(session, AMS_TXT).text
        live_path.write_text(text, encoding="utf-8")
    else:
        text = live_path.read_text(encoding="utf-8")
    out.append((None, "live", text))

    snaps = fetch_wayback_cdx(refresh=refresh)
    if max_snapshots is not None and len(snaps) > max_snapshots:
        # Evenly sample across the full archive (not just the oldest N)
        idxs = [
            int(round(i * (len(snaps) - 1) / (max_snapshots - 1)))
            for i in range(max_snapshots)
        ]
        snaps = [snaps[i] for i in dict.fromkeys(idxs)]

    for ts, original in snaps:
        cache_path = RAW_DIR / f"sa_ls855_{ts}.txt"
        if cache_path.exists() and not refresh:
            text = cache_path.read_text(encoding="utf-8", errors="replace")
        else:
            url = f"https://web.archive.org/web/{ts}id_/{original}"
            try:
                text = _get(session, url).text
            except Exception as exc:
                print(f"skip {ts}: {exc}")
                continue
            cache_path.write_text(text, encoding="utf-8")
            time.sleep(pause)
        out.append((pd.Timestamp(ts[:8]), f"wayback:{ts}", text))

    return out


def _parse_report_date(text: str) -> pd.Timestamp | None:
    for pat in DATE_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                return pd.Timestamp(f"{m.group(1)} {m.group(2)} {m.group(3)}")
            except Exception:
                continue
    return None


def _normalize_market(raw: str) -> str | None:
    key = re.sub(r"\s+", " ", raw.strip().lower().rstrip(":"))
    if key in MARKET_ALIASES:
        return MARKET_ALIASES[key]
    # prefix match for "New Holland, PA:" etc.
    for alias, name in MARKET_ALIASES.items():
        if key.startswith(alias):
            return name
    return None


def parse_sa_ls855(text: str, source: str = "") -> pd.DataFrame:
    """Parse a Weekly National Sheep Summary into long quote rows."""
    report_date = _parse_report_date(text)
    lines = text.replace("\r", "").split("\n")

    section = None
    market: str | None = None
    # continuation buffer for wrapped market lines
    buf = ""
    rows: list[dict] = []

    def flush(chunk: str):
        nonlocal market
        if not chunk.strip():
            return
        # New market line starts with indent + Name:
        mkt_match = re.match(r"^\s{2,}([A-Za-z][A-Za-z0-9.,' &\-/]+):\s*(.*)$", chunk)
        if mkt_match:
            market = _normalize_market(mkt_match.group(1))
            body = mkt_match.group(2)
        else:
            body = chunk.strip()
        if market is None or section is None:
            return
        if re.search(r"no\s+(test|report|sales)", body, re.I):
            return

        quotes = list(QUOTE_RE.finditer(body))
        if quotes:
            for q in quotes:
                p1 = float(q.group("p1"))
                p2 = float(q.group("p2")) if q.group("p2") else p1
                rows.append(
                    {
                        "report_date": report_date,
                        "section": section,
                        "market": market,
                        "wt_lo": int(q.group("wlo")),
                        "wt_hi": int(q.group("whi")),
                        "price_lo": min(p1, p2),
                        "price_hi": max(p1, p2),
                        "price_mid": (p1 + p2) / 2,
                        "source": source,
                    }
                )
            return

        # Section-level weight class, price-only quotes on the market line
        for q in PRICE_ONLY_RE.finditer(body):
            p1, p2 = float(q.group("p1")), float(q.group("p2"))
            # skip obvious non-prices (years, head counts) — prices are typically 50-600
            if not (40 <= p1 <= 700 and 40 <= p2 <= 700):
                continue
            rows.append(
                {
                    "report_date": report_date,
                    "section": section,
                    "market": market,
                    "wt_lo": pd.NA,
                    "wt_hi": pd.NA,
                    "price_lo": min(p1, p2),
                    "price_hi": max(p1, p2),
                    "price_mid": (p1 + p2) / 2,
                    "source": source,
                }
            )

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if buf:
                flush(buf)
                buf = ""
            continue

        # Section headers are left-aligned (or lightly indented) title lines
        sec_hit = None
        for pat, name in SECTION_PATTERNS:
            if pat.match(stripped):
                sec_hit = name
                break
        if sec_hit:
            if buf:
                flush(buf)
                buf = ""
            section = sec_hit
            market = None
            continue

        # Stop parsing once slaughter stats / source footer begins
        if re.match(r"^(sheep and lamb slaughter|source:)", stripped, re.I):
            break

        # Market lines are indented; continuations are more indented or bare
        if re.match(r"^\s{2,}[A-Za-z]", line):
            if buf:
                flush(buf)
            buf = line
        elif buf:
            buf += " " + stripped
        else:
            continue

    if buf:
        flush(buf)

    df = pd.DataFrame(rows)
    if not df.empty:
        df["report_date"] = pd.to_datetime(df["report_date"])
    return df


def fetch_sheep_quotes(
    max_snapshots: int | None = None,
    refresh: bool = False,
) -> pd.DataFrame:
    """End-to-end: download + parse SA_LS855 into a cached quote panel."""
    cache = DATA_DIR / "sheep_auction_quotes.csv"
    if cache.exists() and not refresh:
        return pd.read_csv(cache, parse_dates=["report_date"])

    texts = fetch_sa_ls855_texts(max_snapshots=max_snapshots, refresh=refresh)
    frames = []
    for approx, source, text in texts:
        df = parse_sa_ls855(text, source=source)
        if df.empty:
            continue
        if df["report_date"].isna().all() and approx is not None:
            df["report_date"] = approx
        frames.append(df)

    if not frames:
        raise RuntimeError("No SA_LS855 quotes parsed")

    out = pd.concat(frames, ignore_index=True)
    # Deduplicate overlapping live + wayback snapshots by date/market/section/weights
    out = out.dropna(subset=["report_date"])
    out = out.sort_values(["report_date", "source"]).drop_duplicates(
        subset=["report_date", "section", "market", "wt_lo", "wt_hi", "price_mid"],
        keep="last",
    )
    out.to_csv(cache, index=False)
    return out


def build_lamb_index(
    quotes: pd.DataFrame,
    section: str = "slaughter_lambs",
    wt_lo: int = 80,
    wt_hi: int = 130,
) -> pd.DataFrame:
    """Weekly national slaughter-lamb index + regional basis.

    Index construction:
    1. Keep quotes in ``section`` whose weight band overlaps [wt_lo, wt_hi]
       (or has no weight info — common in older reports for the 90-160 class).
    2. Market-week price = mean of price_mid across qualifying quotes.
    3. National index = equal-weight mean across markets reporting that week.
    4. Basis = market price − national index.
    """
    q = quotes[quotes["section"] == section].copy()
    if q.empty:
        return q

    has_wt = q["wt_lo"].notna() & q["wt_hi"].notna()
    overlaps = has_wt & (q["wt_lo"] <= wt_hi) & (q["wt_hi"] >= wt_lo)
    # older reports often omit per-band weights for the 90-160 class
    keep = overlaps | ~has_wt
    q = q[keep]
    if q.empty:
        return q

    market_week = (
        q.groupby(["report_date", "market"], as_index=False)["price_mid"]
        .mean()
        .rename(columns={"price_mid": "price"})
    )
    national = (
        market_week.groupby("report_date", as_index=False)
        .agg(national_index=("price", "mean"), n_markets=("market", "nunique"))
    )
    panel = market_week.merge(national, on="report_date")
    panel["basis"] = panel["price"] - panel["national_index"]
    panel = panel.sort_values(["report_date", "market"])
    return panel


# ---------------------------------------------------------------------------
# Auction PDFs (goat + lamb lots at major markets)
# ---------------------------------------------------------------------------

def fetch_auction_pdf_text(market_key: str, refresh: bool = False) -> str:
    """Download and extract text from a current auction PDF."""
    if market_key not in AUCTION_PDFS:
        raise KeyError(market_key)
    cache = RAW_DIR / f"{market_key}_latest.txt"
    if cache.exists() and not refresh:
        return cache.read_text(encoding="utf-8")

    from pypdf import PdfReader

    session = _session()
    pdf = _get(session, AUCTION_PDFS[market_key]).content
    (RAW_DIR / f"{market_key}_latest.pdf").write_bytes(pdf)
    reader = PdfReader(BytesIO(pdf))
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    cache.write_text(text, encoding="utf-8")
    return text


def parse_auction_lots(text: str, market: str) -> pd.DataFrame:
    """Parse graded lot blocks from an AMS auction PDF text extract.

    pypdf emits each table cell on its own line::

        14
        51-59
        56
        315.00-350.00
        328.77
        Average
    """
    report_date = _parse_report_date(text)
    m = re.search(
        r"Weighted Average Report for\s+(\d{1,2}/\d{1,2}/\d{4})", text, re.I
    )
    if m:
        report_date = pd.Timestamp(m.group(1))

    section = "unknown"
    grade = ""
    rows: list[dict] = []
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]

    section_re = re.compile(
        r"^(SLAUGHTER SHEEP/?LAMBS|FEEDER SHEEP/?LAMBS|SLAUGHTER GOATS|"
        r"FEEDER GOATS|REPLACEMENT EWES)",
        re.I,
    )
    grade_re = re.compile(
        r"^(WOOLED|HAIR|KIDS|NANNIES|BUCKS|WETHERS|EWES|SELECTION)\b",
        re.I,
    )
    head_re = re.compile(r"^\d{1,5}$")
    wt_re = re.compile(r"^(\d{2,3})(?:\s*-\s*(\d{2,3}))?$")
    price_re = re.compile(r"^(\d+(?:\.\d+)?)(?:\s*-\s*(\d+(?:\.\d+)?))?$")
    avg_re = re.compile(r"^(\d+(?:\.\d+)?)$")

    i = 0
    while i < len(lines):
        ln = lines[i]
        if section_re.match(ln):
            section = re.sub(r"\s+", "_", ln.split("(")[0].strip().lower())
            grade = ""
            i += 1
            continue
        if grade_re.match(ln):
            grade = ln
            i += 1
            continue

        # Sequential lot: head, wt, avg_wt, price, avg_price, "Average"
        if (
            head_re.match(ln)
            and i + 5 < len(lines)
            and wt_re.match(lines[i + 1])
            and avg_re.match(lines[i + 2])
            and price_re.match(lines[i + 3])
            and avg_re.match(lines[i + 4])
            and lines[i + 5].lower().startswith("average")
        ):
            wlo, whi = wt_re.match(lines[i + 1]).groups()
            p1, p2 = price_re.match(lines[i + 3]).groups()
            p1f = float(p1)
            p2f = float(p2) if p2 else p1f
            species = (
                "goat"
                if "goat" in section
                else "sheep"
                if any(k in section for k in ("sheep", "lamb", "ewe"))
                else "other"
            )
            rows.append(
                {
                    "report_date": report_date,
                    "market": market,
                    "section": section,
                    "species": species,
                    "grade": grade,
                    "head": int(ln),
                    "wt_lo": int(wlo),
                    "wt_hi": int(whi or wlo),
                    "avg_wt": float(lines[i + 2]),
                    "price_lo": min(p1f, p2f),
                    "price_hi": max(p1f, p2f),
                    "avg_price": float(lines[i + 4]),
                }
            )
            i += 6
            continue
        i += 1

    return pd.DataFrame(rows)


def fetch_major_auction_lots(refresh: bool = False) -> pd.DataFrame:
    """Latest San Angelo + New Holland graded lots (sheep and goat)."""
    cache = DATA_DIR / "major_auction_lots.csv"
    if cache.exists() and not refresh:
        return pd.read_csv(cache, parse_dates=["report_date"])

    frames = []
    for key, label in [("san_angelo", "San Angelo"), ("new_holland", "New Holland")]:
        text = fetch_auction_pdf_text(key, refresh=refresh)
        df = parse_auction_lots(text, market=label)
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out.to_csv(cache, index=False)
    return out


# ---------------------------------------------------------------------------
# Optional MARS API helpers
# ---------------------------------------------------------------------------

def mars_api_key() -> str | None:
    key = os.environ.get("MARS_API_KEY")
    if key:
        return key.strip()
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("MARS_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def fetch_mars_report(slug_id: str | int, q: str | None = None) -> dict:
    """Fetch a MARS report JSON. Requires MARS_API_KEY."""
    key = mars_api_key()
    if not key:
        raise RuntimeError(
            "MARS_API_KEY not set. Register free at "
            "https://mymarketnews.ams.usda.gov/ and add MARS_API_KEY to .env"
        )
    url = f"https://marsapi.ams.usda.gov/services/v1.2/reports/{slug_id}"
    if q:
        url += f"?q={q}"
    r = requests.get(url, auth=(key, ""), headers=UA, timeout=90)
    r.raise_for_status()
    return r.json()


if __name__ == "__main__":
    print("Fetching/parsing SA_LS855 history (this may take a few minutes on first run)...")
    quotes = fetch_sheep_quotes(max_snapshots=60, refresh=False)
    print("quotes:", quotes.shape)
    print(quotes.groupby("section")["report_date"].agg(["min", "max", "count"]))
    print("markets:", sorted(quotes["market"].dropna().unique()))

    idx = build_lamb_index(quotes)
    print("\nindex weeks:", idx["report_date"].nunique(), "rows:", len(idx))
    print(idx.groupby("report_date")["national_index"].first().tail())

    lots = fetch_major_auction_lots()
    print("\nauction lots:", lots.shape)
    print(lots.groupby(["market", "species"])["head"].sum())
