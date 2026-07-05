"""Second-pass CIK fixes: list EDGAR company-search candidates and pick by
name pattern. Candidates printed for manual eyeball; CIKs come from EDGAR."""

import re
import time
import urllib.parse
import urllib.request

import pandas as pd

UA = {"User-Agent": "AlphaSync research chamberblue@gmail.com"}

# ticker -> (search term, regex the correct conformed name must match)
FIXES = {
    "ALTR": ("Altera", r"^ALTERA CORP"),
    "LMCA": ("Liberty Media", r"^LIBERTY MEDIA CORP"),
    "LMCK": ("Liberty Media", r"^LIBERTY MEDIA CORP"),
    "VIAB": ("Viacom", r"^VIACOM INC"),
    "CA": ("CA, Inc", r"^CA,? INC"),
    "CTRP": ("Ctrip", r"CTRIP|TRIP\.COM"),
    "SIAL": ("Sigma Aldrich", r"SIGMA[ -]?ALDRICH"),
    "VIP": ("VimpelCom", r"VIMPELCOM|VEON"),
}


def candidates(term):
    url = "https://www.sec.gov/cgi-bin/browse-edgar?" + urllib.parse.urlencode(
        {"action": "getcompany", "company": term, "type": "10-K", "count": 40}
    )
    req = urllib.request.Request(url, headers=UA)
    body = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", errors="ignore")
    pairs = re.findall(r"CIK=(\d{10})[^\"]*\"[^>]*>([^<]+)</a>", body)
    if not pairs:  # single exact match redirects to company page
        cik = re.search(r"CIK=(\d{10})", body)
        name = re.search(r"companyName\">([^<]+)<", body) or re.search(
            r"<span class=\"companyName\">([^(<]+)", body
        )
        if cik and name:
            pairs = [(cik.group(1), name.group(1).strip())]
    return pairs


def main():
    path = "data/ticker_cik_map.csv"
    m = pd.read_csv(path, dtype={"cik": str})
    for t, (term, pat) in FIXES.items():
        cands = candidates(term)
        pick = [(c, n) for c, n in cands if re.search(pat, n.upper())]
        print(f"--- {t} (search '{term}') {len(cands)} candidates")
        for c, n in cands[:6]:
            mark = " <== PICK" if pick and (c, n) == pick[0] else ""
            print(f"    {c} | {n}{mark}")
        if pick:
            cik, name = pick[0]
            m.loc[m["ticker"] == t, ["cik", "company_name", "found"]] = [cik, name, True]
        else:
            print("    NO MATCH for pattern", pat)
        time.sleep(0.15)
    m.to_csv(path, index=False)
    left = m[m["cik"].isna() & ~m["ticker"].isin(["MTUM", "VTV"])]["ticker"].tolist()
    print("\nstill unresolved:", left)


if __name__ == "__main__":
    main()
