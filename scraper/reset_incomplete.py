"""Reset incomplete records (budget=0 placeholder) back to null for re-scraping."""
import os
import requests

SUPABASE_URL = "https://chclxcbmdzgdozldufzs.supabase.co"
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNoY2x4Y2JtZHpnZG96bGR1ZnpzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM5MTcwMzEsImV4cCI6MjA4OTQ5MzAzMX0.X50CLwSq1PRDDMFlsGKlSsi-n52JlZC55drAoiddo1I"


def main():
    if not SERVICE_KEY:
        print("ERROR: SUPABASE_SERVICE_KEY not set")
        return

    headers = {
        'Authorization': f'Bearer {SERVICE_KEY}',
        'apikey': SERVICE_KEY,
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal',
    }
    read_headers = {'apikey': ANON_KEY, 'Authorization': f'Bearer {ANON_KEY}'}

    # Count records with budget=0 (incomplete)
    r = requests.get(
        f'{SUPABASE_URL}/rest/v1/vendor_history?budget=eq.0&select=id',
        headers={**read_headers, 'Prefer': 'count=exact'},
        params={'limit': '1'})
    count = r.headers.get('content-range', '?/?').split('/')[-1]
    print(f"Records with budget=0 (incomplete): {count}")

    # Reset budget=0 back to null
    r = requests.patch(
        f'{SUPABASE_URL}/rest/v1/vendor_history?budget=eq.0',
        headers=headers,
        json={'budget': None})
    print(f"Reset budget to null: status {r.status_code}")

    # Verify
    r = requests.get(
        f'{SUPABASE_URL}/rest/v1/vendor_history?budget=is.null&select=id',
        headers={**read_headers, 'Prefer': 'count=exact'},
        params={'limit': '1'})
    pending = r.headers.get('content-range', '?/?').split('/')[-1]
    print(f"Records now pending (budget=null): {pending}")
    print("Done! These records will be re-scraped by auto_scrape.py")


if __name__ == '__main__':
    main()
