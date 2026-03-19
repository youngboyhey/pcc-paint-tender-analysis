"""Fetch vendor history detail data via Python requests (no CAPTCHA)"""
import requests
import json
import time
import re
import os
from html.parser import HTMLParser

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://chclxcbmdzgdozldufzs.supabase.co")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNoY2x4Y2JtZHpnZG96bGR1ZnpzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM5MTcwMzEsImV4cCI6MjA4OTQ5MzAzMX0.X50CLwSq1PRDDMFlsGKlSsi-n52JlZC55drAoiddo1I"

def parse_amount(text):
    if not text:
        return None
    m = re.search(r'[\d,]+', text.replace(',', ''))
    if m:
        return int(m.group().replace(',', ''))
    return None

def extract_from_html(html, vendor_name):
    """Extract budget, base_price, award_price, is_winner from detail HTML"""
    # Simple td-based extraction
    td_pattern = re.compile(r'<td[^>]*>(.*?)</td>', re.DOTALL)
    tds = [re.sub(r'<[^>]+>', '', t).strip().replace('\n', '').replace('\r', '').replace('\t', '') for t in td_pattern.findall(html)]
    tds = [re.sub(r'\s+', ' ', t).strip() for t in tds]

    budget = None
    base_price = None
    award_price = None
    is_winner = None

    for i in range(len(tds) - 1):
        l, v = tds[i], tds[i+1]
        if l == '預算金額' and budget is None:
            budget = parse_amount(v)
        if l == '底價金額' and base_price is None:
            base_price = parse_amount(v)
        if l == '總決標金額' and award_price is None:
            award_price = parse_amount(v)

    # Find vendor's is_winner status
    in_section = False
    for i in range(len(tds) - 1):
        l, v = tds[i], tds[i+1]
        if re.match(r'^(得標廠商|未得標廠商)\d*$', l) and v == '':
            in_section = True
            continue
        if not in_section and l == '廠商名稱' and v == vendor_name:
            for j in range(i+1, min(i+10, len(tds)-1)):
                if tds[j] == '是否得標':
                    is_winner = '是' in tds[j+1]
                    break
                if tds[j] == '廠商名稱':
                    break
            break

    return {
        'budget': budget,
        'base_price': base_price,
        'award_price': award_price,
        'is_winner': is_winner,
    }

def main():
    # Get all vendor_history records
    headers = {'apikey': ANON_KEY, 'Authorization': f'Bearer {ANON_KEY}'}
    all_records = []
    offset = 0
    while True:
        r = requests.get(
            f'{SUPABASE_URL}/rest/v1/vendor_history?select=id,vendor_name,case_no,detail_url,budget&order=id&offset={offset}&limit=1000',
            headers=headers
        )
        data = r.json()
        all_records.extend(data)
        if len(data) < 1000:
            break
        offset += 1000

    # Filter records that need data
    needs_data = [r for r in all_records if r.get('budget') is None]
    print(f"Total: {len(all_records)}, needs data: {len(needs_data)}")

    # Create session for PCC
    session = requests.Session()
    session.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

    # Update headers for Supabase
    supa_headers = {
        'Authorization': f'Bearer {SERVICE_KEY}',
        'apikey': SERVICE_KEY,
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal',
    }

    results = []
    errors = 0

    for i, record in enumerate(needs_data):
        url = record['detail_url']
        if not url:
            continue

        try:
            r = session.get(url, allow_redirects=True, timeout=15)
            html = r.text

            if '驗證碼' in html:
                print(f"  [{i+1}] CAPTCHA for {record['case_no']} - creating new session")
                session = requests.Session()
                session.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                time.sleep(5)
                r = session.get(url, allow_redirects=True, timeout=15)
                html = r.text
                if '驗證碼' in html:
                    errors += 1
                    continue

            data = extract_from_html(html, record['vendor_name'])
            results.append({'id': record['id'], **data})

            # Update Supabase if we have service key
            if SERVICE_KEY:
                update = {}
                if data['budget'] is not None:
                    update['budget'] = data['budget']
                if data['base_price'] is not None:
                    update['base_price'] = data['base_price']
                if data['award_price'] is not None:
                    update['award_price'] = data['award_price']
                if data['is_winner'] is not None:
                    update['is_winner'] = data['is_winner']

                if update:
                    requests.patch(
                        f'{SUPABASE_URL}/rest/v1/vendor_history?id=eq.{record["id"]}',
                        headers=supa_headers,
                        json=update
                    )

            if (i + 1) % 10 == 0:
                print(f"  [{i+1}/{len(needs_data)}] {record['case_no']}: budget={data['budget']}, award={data['award_price']}, winner={data['is_winner']}")

        except Exception as e:
            errors += 1
            if (i + 1) % 10 == 0:
                print(f"  [{i+1}] ERROR: {str(e)[:60]}")

        # Rate limiting: 1 request per second
        time.sleep(1)

    # Save results to file
    with open('vendor_details.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nDone! {len(results)} results, {errors} errors")
    print(f"Saved to vendor_details.json")

if __name__ == '__main__':
    main()
