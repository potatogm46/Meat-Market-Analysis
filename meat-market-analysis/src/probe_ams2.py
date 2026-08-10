"""Deeper probe: Wayback history + MyMarketNews filerepo + PDF text extractability."""
from __future__ import annotations

import json
import re
from io import BytesIO

import requests

UA = {"User-Agent": "meat-market-analysis (student research)"}


def get(url: str, **kw):
    r = requests.get(url, headers=UA, timeout=60, **kw)
    print(f"{r.status_code} {len(r.content)} {url[:120]}")
    return r


# Wayback CDX - full history for weekly national sheep summary
r = get(
    "https://web.archive.org/cdx/search/cdx",
    params={
        "url": "www.ams.usda.gov/mnreports/sa_ls855.txt",
        "output": "json",
        "fl": "timestamp,original,statuscode,mimetype",
        "filter": "statuscode:200",
        "collapse": "timestamp:8",  # one per day
    },
)
if r.ok:
    rows = r.json()
    print("wayback rows", len(rows) - 1)
    print("first", rows[1] if len(rows) > 1 else None)
    print("last", rows[-1] if len(rows) > 1 else None)
    # show year counts
    years = {}
    for row in rows[1:]:
        years[row[0][:4]] = years.get(row[0][:4], 0) + 1
    print("by year", dict(sorted(years.items())))

# Try filerepo search pages / possible JSON endpoints
candidates = [
    "https://mymarketnews.ams.usda.gov/filerepo/reports?field_slug_id_value=3173&_format=json",
    "https://marsapi.ams.usda.gov/services/v1.2/reports/3173",
    "https://marsapi.ams.usda.gov/services/v1.2/reports/SA_LS855",
    "https://marsapi.ams.usda.gov/services/v3.1/reports/3173",
]
for u in candidates:
    try:
        rr = get(u)
        print(rr.text[:300].replace("\n", " "))
        print("---")
    except Exception as e:
        print("ERR", e)

# Can we extract text from San Angelo PDF without pdfplumber?
r = get("https://www.ams.usda.gov/mnreports/ams_2014.pdf")
text = r.content
# crude PDF text strings
strings = re.findall(rb"[\x20-\x7e]{4,}", text)
decoded = [s.decode("ascii", errors="ignore") for s in strings]
hits = [s for s in decoded if re.search(r"(goat|lamb|sheep|\$|cwt|lbs)", s, re.I)]
print("pdf string hits", len(hits))
for h in hits[:40]:
    print(" ", h[:120])
