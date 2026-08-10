"""Quick probes for AMS sheep/goat report URLs and Wayback coverage."""
from __future__ import annotations

import re

import requests

UA = {"User-Agent": "meat-market-analysis (student research)"}


def check(url: str) -> None:
    try:
        r = requests.get(url, headers=UA, timeout=45)
        ctype = r.headers.get("content-type", "?")[:45]
        print(f"{r.status_code:>3} {len(r.content):>8} {ctype:<45} {url}")
        if r.status_code == 200 and "text" in ctype and len(r.content) < 8000:
            print(r.text[:400])
            print("---")
    except Exception as exc:
        print(f"ERR {exc} {url}")


urls = [
    "https://www.ams.usda.gov/mnreports/sa_ls855.txt",
    "https://www.ams.usda.gov/mnreports/SA_LS855.TXT",
    "https://www.ams.usda.gov/mnreports/sa_ls850.txt",
    "https://www.ams.usda.gov/mnreports/ams_2014.pdf",
    "https://www.ams.usda.gov/mnreports/ams_1913.pdf",
    "https://www.ams.usda.gov/mnreports/lm_lm352.txt",
    "https://web.archive.org/cdx/search/cdx?url=ams.usda.gov/mnreports/sa_ls855.txt&output=json&limit=5&fl=timestamp,original,statuscode",
    "https://web.archive.org/cdx/search/cdx?url=www.ams.usda.gov/mnreports/sa_ls855.txt&output=json&limit=5&fl=timestamp,original,statuscode",
    "https://web.archive.org/cdx/search/cdx?url=ams.usda.gov/mnreports/*ls855*&output=json&limit=20&fl=timestamp,original,statuscode",
]

for u in urls:
    check(u)

# Cornell publication page
print("\n=== Cornell ESMIS ===")
r = requests.get(
    "https://usda.library.cornell.edu/concern/publications/vq27zn42r.json",
    headers=UA,
    timeout=60,
)
print("cornell json", r.status_code, len(r.content))
if r.ok:
    data = r.json()
    # print top-level keys and any file urls
    print("keys", list(data.keys())[:20])
    text = r.text
    for m in re.findall(r"https?://[^\"']+\.txt", text)[:15]:
        print("txt", m)
    for m in re.findall(r"/downloads/[^\"']+", text)[:15]:
        print("dl", m)
