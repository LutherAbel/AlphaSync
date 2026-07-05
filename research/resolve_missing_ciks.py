"""Resolve CIKs for delisted tickers missing from the SEC current-ticker map.

Strategy: query EDGAR company search by ticker first, then by company name.
The CIK always comes from EDGAR's response (never hardcoded). Every match is
printed with EDGAR's conformed name for manual eyeballing before use.
Updates data/ticker_cik_map.csv in place (source column notes the method).
"""

import re
import time
import urllib.parse
import urllib.request

import pandas as pd

UA = {"User-Agent": "AlphaSync research chamberblue@gmail.com"}

# Former company names for delisted tickers (search terms only; CIK comes from EDGAR)
NAMES = {
    "ALTR": "Altera Corp", "ALXN": "Alexion Pharmaceuticals", "ANSS": "Ansys Inc",
    "BRCM": "Broadcom Corp", "CA": "CA Inc", "CELG": "Celgene Corp",
    "CERN": "Cerner Corp", "CTRP": "Ctrip.com International", "CTRX": "Catamaran Corp",
    "CTXS": "Citrix Systems", "DISCA": "Discovery Communications", "DISCK": "Discovery Communications",
    "DISH": "DISH Network", "DTV": "DIRECTV", "ENDP": "Endo International",
    "ESRX": "Express Scripts", "GMCR": "Green Mountain Coffee Roasters", "HOLX": "Hologic",
    "KRFT": "Kraft Foods Group", "LLTC": "Linear Technology", "LMCA": "Liberty Media Corp",
    "LMCK": "Liberty Media Corp", "MXIM": "Maxim Integrated Products", "MYL": "Mylan",
    "NLOK": "NortonLifeLock", "QRTEA": "Qurate Retail", "SGEN": "Seattle Genetics",
    "SHPG": "Shire plc", "SIAL": "Sigma-Aldrich", "SPLK": "Splunk", "SPLS": "Staples",
    "SRCL": "Stericycle", "VIAB": "Viacom Inc", "VIP": "VimpelCom",
    "WBA": "Walgreens Boots Alliance", "WFM": "Whole Foods Market",
    "WLTW": "Willis Towers Watson", "XLNX": "Xilinx", "YHOO": "Yahoo",
}


def edgar_atom(params: dict) -> str:
    url = "https://www.sec.gov/cgi-bin/browse-edgar?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=20).read().decode("utf-8", errors="ignore")


def parse_cik_name(body: str):
    cik = re.search(r"<cik>(\d+)</cik>", body, re.I)
    name = re.search(r"<conformed-name>([^<]+)</conformed-name>", body, re.I)
    if cik:
        return cik.group(1).zfill(10), (name.group(1).strip() if name else "?")
    return None, None


def lookup(ticker: str):
    # 1) ticker as CIK param (works for some delisted tickers)
    body = edgar_atom({"action": "getcompany", "CIK": ticker, "type": "10-K", "count": 1, "output": "atom"})
    cik, name = parse_cik_name(body)
    if cik:
        return cik, name, "ticker-search"
    # 2) company name search, require 10-K filer
    q = NAMES.get(ticker)
    if q:
        body = edgar_atom({"action": "getcompany", "company": q, "type": "10-K", "count": 1, "output": "atom"})
        cik, name = parse_cik_name(body)
        if cik:
            return cik, name, "name-search"
    return None, None, "unresolved"


def main():
    path = "data/ticker_cik_map.csv"
    m = pd.read_csv(path, dtype={"cik": str})
    missing = m[m["cik"].isna() & ~m["ticker"].isin(["MTUM", "VTV"])]["ticker"].tolist()
    print(f"resolving {len(missing)} tickers\n")
    resolved = {}
    for t in missing:
        cik, name, how = lookup(t)
        print(f"{t:6} -> {cik or 'UNRESOLVED':10} | {name or '':40} | {how}")
        if cik:
            resolved[t] = (cik, name, how)
        time.sleep(0.15)
    for t, (cik, name, how) in resolved.items():
        m.loc[m["ticker"] == t, ["cik", "company_name", "found"]] = [cik, name, True]
    m.to_csv(path, index=False)
    print(f"\nupdated {path}: resolved {len(resolved)}/{len(missing)}")


if __name__ == "__main__":
    main()
