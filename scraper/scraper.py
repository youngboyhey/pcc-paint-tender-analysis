"""
PCC Government e-Procurement Scraper
爬取政府電子採購網「建築物及道路零星油漆長約工作」決標資料
"""
import re
import time
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from config import *

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
})


def parse_amount(text):
    """Parse amount from text like '4,891,216元' """
    if not text:
        return None
    text = text.replace(",", "").replace("元", "").replace(" ", "").replace("\xa0", "").strip()
    m = re.search(r"([\d.]+)", text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def search_tenders(year, page_size=100):
    """Search tenders for a specific ROC year"""
    params = {
        "querySentence": SEARCH_KEYWORD,
        "tenderStatusType": "決標",
        "sortCol": "AWARD_NOTICE_DATE",
        "timeRange": str(year),
        "pageSize": str(page_size),
    }
    print(f"  搜尋 {year} 年...")
    resp = SESSION.get(PCC_SEARCH_URL, params=params, timeout=30)
    resp.encoding = "utf-8"
    return parse_search_results(resp.text, year)


def parse_search_results(html, year):
    """Parse search results from HTML - handles JS-rendered case names"""
    soup = BeautifulSoup(html, "lxml")
    results = []

    # Find the results table - it's the last table with 10-column header
    tables = soup.find_all("table")
    result_table = None
    for t in tables:
        header_row = t.find("tr")
        if header_row:
            cells = header_row.find_all(["th", "td"])
            if len(cells) == 10:
                first_text = cells[0].get_text(strip=True)
                if "項次" in first_text or "種類" in first_text:
                    result_table = t
                    break

    if not result_table:
        print("    找到 0 筆資料")
        return results

    rows = result_table.find_all("tr")
    data_rows = rows[1:]  # Skip header
    print(f"    找到 {len(data_rows)} 筆資料")

    for row in data_rows:
        cells = row.find_all("td")
        if len(cells) < 10:
            continue

        # Cell 0: index, Cell 1: type, Cell 2: agency, Cell 3: case info, ...
        tender_type = cells[1].get_text(strip=True)  # 決標公告
        agency = cells[2].get_text(strip=True)

        # Cell 3: case_no + case_name (name is in JS call)
        cell3 = cells[3]
        # Extract case number from text
        case_no_text = cell3.get_text(strip=True)
        case_no = ""
        m = re.search(r"([A-Za-z0-9-]+)", case_no_text)
        if m:
            case_no = m.group(1)

        # Extract case name from JavaScript: Geps3.CNS.pageCode2Img("case_name")
        script = cell3.find("script")
        case_name = ""
        if script and script.string:
            m = re.search(r'pageCode2Img\("([^"]+)"\)', script.string)
            if m:
                case_name = m.group(1)

        # Find link (pk)
        link = cell3.find("a", href=re.compile(r"/prkms/urlSelector/common/"))
        if not link:
            link = cells[9].find("a", href=re.compile(r"/prkms/urlSelector/common/"))
        if not link:
            continue

        href = link.get("href", "")
        is_non_atm = "nonAtm" in href
        pk_match = re.search(r"pk=([A-Za-z0-9=]+)", href)
        if not pk_match:
            continue
        pk = pk_match.group(1)

        award_date_text = cells[5].get_text(strip=True)
        is_failed = "無法決標" in award_date_text or is_non_atm

        results.append({
            "case_no": case_no,
            "case_name": case_name,
            "agency": agency,
            "award_date": award_date_text,
            "pk": pk,
            "detail_url": urljoin(PCC_BASE_URL, href),
            "is_failed": is_failed,
            "is_atm": not is_non_atm,
            "year": year,
        })

    return results


def fetch_award_detail(pk):
    """Fetch award detail page and extract financial/bidder data"""
    url = f"{PCC_AWARD_DETAIL_URL}?pkAtmMain={pk}"
    resp = SESSION.get(url, timeout=30)
    resp.encoding = "utf-8"
    return parse_award_detail(resp.text)


def parse_award_detail(html):
    """Parse award detail page for budget, prices, bidders"""
    soup = BeautifulSoup(html, "lxml")
    detail = {
        "budget": None,
        "base_price": None,
        "award_price": None,
        "bidders": [],
    }

    # Extract all label-value pairs from th-td structure
    all_rows = soup.find_all("tr")

    # First pass: get financial info
    for row in all_rows:
        ths = row.find_all("th")
        tds = row.find_all("td")
        if not ths or not tds:
            continue

        for th, td in zip(ths, tds):
            label = th.get_text(strip=True)
            value = td.get_text(strip=True)

            if "預算金額" in label and "是否" not in label:
                detail["budget"] = parse_amount(value)
            elif "底價金額" in label and "是否訂有底價" not in label:
                detail["base_price"] = parse_amount(value)
            elif "總決標金額" in label:
                amt = parse_amount(value)
                if amt:
                    detail["award_price"] = amt
            elif label == "決標金額" or ("決標金額" in label and "合計" not in label and "總" not in label):
                if detail["award_price"] is None:
                    detail["award_price"] = parse_amount(value)

    # Second pass: extract bidder sections
    # Bidders are in numbered sections with 廠商名稱, 投標金額, 是否得標
    current_bidder = None
    for row in all_rows:
        ths = row.find_all("th")
        tds = row.find_all("td")
        if not ths or not tds:
            continue

        for th, td in zip(ths, tds):
            label = th.get_text(strip=True)
            value = td.get_text(strip=True)

            # Also check for JS-rendered vendor names
            script = td.find("script")
            if script and script.string:
                m = re.search(r'pageCode2Img\("([^"]+)"\)', script.string)
                if m:
                    value = m.group(1)

            if "廠商名稱" in label:
                if current_bidder and current_bidder.get("name"):
                    detail["bidders"].append(current_bidder)
                current_bidder = {
                    "name": value,
                    "bid_amount": None,
                    "is_winner": False,
                    "original_bid": None,
                }
            elif current_bidder:
                if "是否得標" in label:
                    current_bidder["is_winner"] = "是" in value
                elif "原始投標金額" in label:
                    current_bidder["original_bid"] = parse_amount(value)
                elif "投標金額" in label or "標價金額" in label:
                    current_bidder["bid_amount"] = parse_amount(value)

    if current_bidder and current_bidder.get("name"):
        detail["bidders"].append(current_bidder)

    return detail


def search_vendor_tenders(vendor_name, year_start=YEAR_START, year_end=YEAR_END):
    """Search all awarded tenders for a specific vendor across years"""
    all_results = []
    for year in range(year_start, year_end + 1):
        params = {
            "querySentence": vendor_name,
            "tenderStatusType": "決標",
            "sortCol": "AWARD_NOTICE_DATE",
            "timeRange": str(year),
            "pageSize": "100",
        }
        try:
            resp = SESSION.get(PCC_SEARCH_URL, params=params, timeout=30)
            resp.encoding = "utf-8"
            soup = BeautifulSoup(resp.text, "lxml")

            tables = soup.find_all("table")
            result_table = None
            for t in tables:
                hr = t.find("tr")
                if hr and len(hr.find_all(["th", "td"])) == 10:
                    if "項次" in hr.get_text():
                        result_table = t
                        break

            if not result_table:
                time.sleep(0.3)
                continue

            rows = result_table.find_all("tr")[1:]
            for row in rows:
                cells = row.find_all("td")
                if len(cells) < 10:
                    continue

                agency = cells[2].get_text(strip=True)
                cell3 = cells[3]

                case_no = ""
                m = re.search(r"([A-Za-z0-9-]+)", cell3.get_text(strip=True))
                if m:
                    case_no = m.group(1)

                case_name = ""
                script = cell3.find("script")
                if script and script.string:
                    m = re.search(r'pageCode2Img\("([^"]+)"\)', script.string)
                    if m:
                        case_name = m.group(1)

                link = cell3.find("a", href=re.compile(r"/prkms/urlSelector/common/atm"))
                if not link:
                    link = cells[9].find("a", href=re.compile(r"/prkms/urlSelector/common/atm"))
                if not link:
                    continue  # Skip non-award entries

                href = link.get("href", "")
                pk_match = re.search(r"pk=([A-Za-z0-9=]+)", href)
                pk = pk_match.group(1) if pk_match else ""

                all_results.append({
                    "vendor_name": vendor_name,
                    "case_no": case_no,
                    "case_name": case_name,
                    "agency": agency,
                    "year": year,
                    "pk": pk,
                    "detail_url": urljoin(PCC_BASE_URL, href),
                })
            time.sleep(0.3)
        except Exception as e:
            print(f"      搜尋 {vendor_name} {year}年 失敗: {e}")
    return all_results


def upload_to_supabase(tenders_data, vendor_history_data):
    """Upload all data to Supabase"""
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "apikey": SUPABASE_SERVICE_KEY,
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    base = f"{SUPABASE_URL}/rest/v1"

    print("\n[Upload] 上傳標案資料到 Supabase...")

    for tender in tenders_data:
        # Upsert tender
        tender_row = {
            "case_no": tender["case_no"],
            "case_name": tender["case_name"],
            "agency": tender.get("agency"),
            "budget": tender.get("budget"),
            "base_price": tender.get("base_price"),
            "award_price": tender.get("award_price"),
            "award_date": tender.get("award_date"),
            "is_awarded": True,
            "tender_year": tender.get("year"),
            "detail_url": tender.get("detail_url"),
        }

        # Try upsert
        resp = requests.post(
            f"{base}/tenders",
            headers={**headers, "Prefer": "return=representation,resolution=merge-duplicates"},
            json=tender_row,
            params={"on_conflict": "case_no"},
        )
        tender_id = None
        if resp.status_code in (200, 201) and resp.json():
            tender_id = resp.json()[0]["id"]
        else:
            # Get existing
            resp2 = requests.get(
                f"{base}/tenders",
                headers=headers,
                params={"case_no": f"eq.{tender['case_no']}", "select": "id"},
            )
            if resp2.status_code == 200 and resp2.json():
                tender_id = resp2.json()[0]["id"]

        if not tender_id:
            print(f"  WARN: Could not get tender_id for {tender['case_no']}")
            continue

        # Insert bidders
        for bidder in tender.get("bidders", []):
            bidder_row = {
                "tender_id": tender_id,
                "company_name": bidder["name"],
                "bid_amount": bidder.get("bid_amount"),
                "is_winner": bidder.get("is_winner", False),
                "original_bid_amount": bidder.get("original_bid", bidder.get("bid_amount")),
            }
            requests.post(f"{base}/bidders", headers=headers, json=bidder_row)

    print("[Upload] 標案資料完成")

    # Upload vendor history
    if vendor_history_data:
        print("[Upload] 上傳廠商歷史資料...")
        # Batch insert in chunks of 50
        for i in range(0, len(vendor_history_data), 50):
            chunk = vendor_history_data[i:i+50]
            rows = [{
                "vendor_name": r["vendor_name"],
                "case_no": r.get("case_no"),
                "case_name": r.get("case_name"),
                "agency": r.get("agency"),
                "budget": r.get("budget"),
                "base_price": r.get("base_price"),
                "award_price": r.get("award_price"),
                "is_winner": r.get("is_winner"),
                "tender_year": r.get("year"),
                "detail_url": r.get("detail_url"),
            } for r in chunk]
            requests.post(f"{base}/vendor_history", headers=headers, json=rows)
        print("[Upload] 廠商歷史資料完成")


def main():
    print("=" * 60)
    print("PCC Scraper - 建築物及道路零星油漆長約工作")
    print("=" * 60)

    # Phase 1: Search 105~115
    print("\n[Phase 1] 搜尋 105~115 年決標公告...")
    all_search = []
    for year in range(YEAR_START, YEAR_END + 1):
        results = search_tenders(year)
        all_search.extend(results)
        time.sleep(0.5)

    awarded = [r for r in all_search if not r["is_failed"] and r["is_atm"]]
    failed = [r for r in all_search if r["is_failed"]]
    print(f"\n  Total: {len(all_search)}, Awarded: {len(awarded)}, Failed: {len(failed)}")

    # Phase 2: Get details for awarded tenders
    print("\n[Phase 2] 取得決標詳細資料...")
    tenders_with_detail = []
    for i, tender in enumerate(awarded):
        print(f"  [{i+1}/{len(awarded)}] {tender['case_name'][:50]} (pk={tender['pk']})")
        try:
            detail = fetch_award_detail(tender["pk"])
            tender.update(detail)
            tenders_with_detail.append(tender)
            print(f"    Budget={detail.get('budget')}, Base={detail.get('base_price')}, Award={detail.get('award_price')}")
            print(f"    Bidders: {[b['name'] for b in detail.get('bidders', [])]}")
        except Exception as e:
            print(f"    ERROR: {e}")
        time.sleep(0.8)

    # Phase 3: Collect unique vendors
    print("\n[Phase 3] 搜尋各廠商歷史投標紀錄...")
    all_vendors = set()
    for tender in tenders_with_detail:
        for bidder in tender.get("bidders", []):
            if bidder.get("name"):
                all_vendors.add(bidder["name"])

    print(f"  共 {len(all_vendors)} 家廠商: {sorted(all_vendors)}")

    all_vendor_history = []
    for vi, vendor in enumerate(sorted(all_vendors)):
        print(f"\n  [{vi+1}/{len(all_vendors)}] {vendor}")
        history = search_vendor_tenders(vendor)
        print(f"    找到 {len(history)} 筆歷史")

        # Get detail for each (budget, base_price, award_price, is_winner)
        for hi, h in enumerate(history):
            try:
                det = fetch_award_detail(h["pk"])
                h["budget"] = det.get("budget")
                h["base_price"] = det.get("base_price")
                h["award_price"] = det.get("award_price")
                h["is_winner"] = any(
                    b.get("is_winner") and vendor in b.get("name", "")
                    for b in det.get("bidders", [])
                )
                time.sleep(0.5)
            except Exception as e:
                print(f"      Detail error: {e}")

        all_vendor_history.extend(history)

    # Phase 4: Upload
    upload_to_supabase(tenders_with_detail, all_vendor_history)

    # Save local backup
    output = {
        "tenders": tenders_with_detail,
        "vendor_history": all_vendor_history,
    }
    with open("output.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)

    print(f"\nDone! {len(tenders_with_detail)} tenders, {len(all_vendor_history)} vendor history records")


if __name__ == "__main__":
    main()
