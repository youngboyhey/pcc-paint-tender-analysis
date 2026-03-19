"""Search vendor history from PCC search results (no CAPTCHA needed)"""
import re
import time
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

import os
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://chclxcbmdzgdozldufzs.supabase.co")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
PCC_BASE = "https://web.pcc.gov.tw"
SEARCH_URL = f"{PCC_BASE}/prkms/tender/common/bulletion/readBulletion"

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
})

VENDORS = [
    "石明油漆工程有限公司", "均嘉工程有限公司", "筑丰工程有限公司",
    "祥泰和營造有限公司", "松彬工程行", "亞成工程行",
    "九驊工程股份有限公司", "鉅嘉室內裝修有限公司", "炬森興業有限公司",
    "育碩工程有限公司",
]


def search_vendor_year(vendor, year):
    """Search awarded tenders mentioning this vendor in a given year"""
    params = {
        "querySentence": vendor,
        "tenderStatusType": "決標",
        "sortCol": "AWARD_NOTICE_DATE",
        "timeRange": str(year),
        "pageSize": "100",
    }
    try:
        resp = SESSION.get(SEARCH_URL, params=params, timeout=30)
        resp.encoding = "utf-8"
        return parse_results(resp.text, vendor, year)
    except Exception as e:
        print(f"      Error: {e}")
        return []


def parse_results(html, vendor, year):
    """Parse search results for vendor history"""
    soup = BeautifulSoup(html, "lxml")
    results = []

    tables = soup.find_all("table")
    result_table = None
    for t in tables:
        hr = t.find("tr")
        if hr and len(hr.find_all(["th", "td"])) == 10:
            if "項次" in hr.get_text():
                result_table = t
                break

    if not result_table:
        return results

    rows = result_table.find_all("tr")[1:]
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 10:
            continue

        agency = cells[2].get_text(strip=True)
        cell3 = cells[3]

        # Case number
        case_no = ""
        m = re.search(r"([A-Za-z0-9-]+)", cell3.get_text(strip=True))
        if m:
            case_no = m.group(1)

        # Case name from JavaScript
        case_name = ""
        script = cell3.find("script")
        if script and script.string:
            m = re.search(r'pageCode2Img\("([^"]+)"\)', script.string)
            if m:
                case_name = m.group(1)

        # Link and type
        link = cell3.find("a", href=re.compile(r"/prkms/urlSelector/common/"))
        if not link:
            link = cells[9].find("a", href=re.compile(r"/prkms/urlSelector/common/"))
        if not link:
            continue

        href = link.get("href", "")
        is_atm = "nonAtm" not in href
        award_date = cells[5].get_text(strip=True)
        is_failed = "無法決標" in award_date

        if is_failed or not is_atm:
            continue  # Skip failed awards

        results.append({
            "vendor_name": vendor,
            "case_no": case_no,
            "case_name": case_name,
            "agency": agency,
            "tender_year": year,
            "detail_url": urljoin(PCC_BASE, href),
        })

    return results


def main():
    print("Searching vendor history (105~115)...")
    all_history = []

    for vi, vendor in enumerate(VENDORS):
        print(f"\n[{vi+1}/{len(VENDORS)}] {vendor}")
        vendor_records = []
        for year in range(105, 116):
            records = search_vendor_year(vendor, year)
            if records:
                print(f"    {year}: {len(records)} records")
            vendor_records.extend(records)
            time.sleep(0.3)
        print(f"  Total: {len(vendor_records)} records")
        all_history.extend(vendor_records)

    # Deduplicate by vendor_name + case_no
    seen = set()
    unique = []
    for r in all_history:
        key = (r["vendor_name"], r["case_no"])
        if key not in seen:
            seen.add(key)
            unique.append(r)

    print(f"\nTotal unique records: {len(unique)}")

    # Upload to Supabase
    headers = {
        "Authorization": f"Bearer {SERVICE_KEY}",
        "apikey": SERVICE_KEY,
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    base = f"{SUPABASE_URL}/rest/v1"

    print("Uploading vendor history...")
    for i in range(0, len(unique), 50):
        chunk = unique[i:i+50]
        rows = [{
            "vendor_name": r["vendor_name"],
            "case_no": r.get("case_no"),
            "case_name": r.get("case_name"),
            "agency": r.get("agency"),
            "tender_year": r.get("tender_year"),
            "detail_url": r.get("detail_url"),
        } for r in chunk]
        resp = requests.post(f"{base}/vendor_history", headers=headers, json=rows)
        if resp.status_code in (200, 201):
            print(f"  Uploaded {i+1}-{i+len(chunk)}")
        else:
            print(f"  Error: {resp.status_code} {resp.text[:100]}")

    # Save backup
    with open("vendor_history.json", "w", encoding="utf-8") as f:
        json.dump(unique, f, ensure_ascii=False, indent=2)

    print(f"\nDone! {len(unique)} vendor history records uploaded.")


if __name__ == "__main__":
    main()
