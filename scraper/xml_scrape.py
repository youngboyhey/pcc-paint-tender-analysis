"""Scrape vendor history data from PCC's Open Data XML files.
No CAPTCHA needed, no IP blocking - direct XML downloads."""
import xml.etree.ElementTree as ET
import os
import time
import requests

SUPABASE_URL = "https://chclxcbmdzgdozldufzs.supabase.co"
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNoY2x4Y2JtZHpnZG96bGR1ZnpzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM5MTcwMzEsImV4cCI6MjA4OTQ5MzAzMX0.X50CLwSq1PRDDMFlsGKlSsi-n52JlZC55drAoiddo1I"
PCC_XML_BASE = "https://web.pcc.gov.tw/tps/tp/OpenData/downloadFile?fileName="


def get_pending_records():
    """Get all vendor_history records that still need data."""
    headers = {'apikey': ANON_KEY, 'Authorization': f'Bearer {ANON_KEY}'}
    all_records = []
    offset = 0
    while True:
        r = requests.get(
            f'{SUPABASE_URL}/rest/v1/vendor_history?budget=is.null'
            f'&select=id,vendor_name,case_no&order=id&offset={offset}&limit=1000',
            headers=headers)
        data = r.json()
        all_records.extend(data)
        if len(data) < 1000:
            break
        offset += 1000
    return all_records


def build_lookup(records):
    """Build case_no -> list of records lookup."""
    lookup = {}
    for rec in records:
        cn = rec['case_no']
        if cn not in lookup:
            lookup[cn] = []
        lookup[cn].append(rec)
    return lookup


def generate_xml_filenames():
    """Generate all award XML filenames from 105 (2016) to 115 (2026)."""
    filenames = []
    for year in range(2016, 2027):  # 105年=2016 to 115年=2026
        for month in range(1, 13):
            for half in ['01', '02']:
                fn = f"award_{year}{month:02d}{half}.xml"
                filenames.append(fn)
    return filenames


def parse_xml_for_cases(xml_content, target_cases):
    """Parse XML and extract data for target case numbers."""
    results = {}
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        return results

    for tender in root.findall('.//TENDER'):
        case_no = tender.findtext('TENDER_CASE_NO', '').strip()
        if case_no not in target_cases:
            continue

        award_price_str = tender.findtext('TENDER_AWARD_PRICE', '')
        award_price = None
        if award_price_str:
            try:
                award_price = int(award_price_str.replace(',', ''))
            except ValueError:
                pass

        # Collect winner and non-winner names
        winners = set()
        non_winners = set()
        bidder_list = tender.find('BIDDER_LIST')
        if bidder_list is not None:
            for elem in bidder_list.findall('BIDDER_SUPP_NAME'):
                if elem.text:
                    winners.add(elem.text.strip())
            for elem in bidder_list.findall('NOT_OBTAIN_SUPP_NAME'):
                if elem.text:
                    non_winners.add(elem.text.strip())

        results[case_no] = {
            'award_price': award_price,
            'winners': winners,
            'non_winners': non_winners,
            'tender_name': tender.findtext('TENDER_NAME', ''),
        }

    return results


def main():
    # Get pending records
    pending = get_pending_records()
    print(f"Pending records: {len(pending)}")
    if not pending:
        print("All done!")
        return

    lookup = build_lookup(pending)
    target_cases = set(lookup.keys())
    print(f"Unique case numbers to find: {len(target_cases)}")

    if not SERVICE_KEY:
        print("WARNING: No SUPABASE_SERVICE_KEY, running in dry-run mode")

    supa_headers = {
        'Authorization': f'Bearer {SERVICE_KEY}',
        'apikey': SERVICE_KEY,
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal',
    }

    found_cases = set()
    updated = 0
    xml_files = generate_xml_filenames()
    print(f"Will scan {len(xml_files)} XML files...")

    for idx, fn in enumerate(xml_files):
        url = PCC_XML_BASE + fn
        try:
            r = requests.get(url, timeout=30)
            if r.status_code != 200 or len(r.content) < 100:
                continue

            # Parse and find matches
            remaining = target_cases - found_cases
            if not remaining:
                print(f"\nAll {len(target_cases)} cases found!")
                break

            results = parse_xml_for_cases(r.content, remaining)

            for case_no, data in results.items():
                found_cases.add(case_no)
                records = lookup[case_no]

                for rec in records:
                    vendor = rec['vendor_name']
                    is_winner = None

                    # Check if vendor is in winners or non-winners
                    for w in data['winners']:
                        if vendor in w or w in vendor:
                            is_winner = True
                            break
                    if is_winner is None:
                        for nw in data['non_winners']:
                            if vendor in nw or nw in vendor:
                                is_winner = False
                                break

                    update = {}
                    if data['award_price'] is not None:
                        update['award_price'] = data['award_price']
                    if is_winner is not None:
                        update['is_winner'] = is_winner

                    # Mark as processed (budget=0 means "from XML, no budget data")
                    update['budget'] = 0

                    if SERVICE_KEY and update:
                        requests.patch(
                            f'{SUPABASE_URL}/rest/v1/vendor_history?id=eq.{rec["id"]}',
                            headers=supa_headers,
                            json=update
                        )
                        updated += 1

            if (idx + 1) % 10 == 0:
                print(f"  [{idx+1}/{len(xml_files)}] found={len(found_cases)}/{len(target_cases)} updated={updated}")

        except Exception as e:
            print(f"  Error on {fn}: {str(e)[:80]}")

        time.sleep(0.5)  # Be polite

    # Mark remaining unfound records (budget=0 to stop retrying)
    unfound = target_cases - found_cases
    print(f"\nFound: {len(found_cases)}, Unfound: {len(unfound)}, Updated: {updated}")

    if SERVICE_KEY and unfound:
        print("Marking unfound records...")
        for case_no in unfound:
            for rec in lookup[case_no]:
                requests.patch(
                    f'{SUPABASE_URL}/rest/v1/vendor_history?id=eq.{rec["id"]}',
                    headers=supa_headers,
                    json={'budget': 0}
                )

    print("Done!")


if __name__ == '__main__':
    main()
