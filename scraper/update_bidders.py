"""Update bidder data with complete bid amounts"""
import requests

import os
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://chclxcbmdzgdozldufzs.supabase.co")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

headers = {
    "Authorization": f"Bearer {SERVICE_KEY}",
    "apikey": SERVICE_KEY,
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}
base = f"{SUPABASE_URL}/rest/v1"

# Complete data with ALL bid amounts
tenders = [
    {"case_no": "MAA0470016", "bidders": [
        {"name": "石明油漆工程有限公司", "is_winner": True, "bid_amount": 3810000, "original_bid": None},
        {"name": "均嘉工程有限公司", "is_winner": False, "bid_amount": 4092157, "original_bid": None},
    ]},
    {"case_no": "MAA0670004", "bidders": [
        {"name": "石明油漆工程有限公司", "is_winner": True, "bid_amount": 3580000, "original_bid": None},
        {"name": "筑丰工程有限公司", "is_winner": False, "bid_amount": 3738705, "original_bid": None},
    ]},
    {"case_no": "MAA0870001", "bidders": [
        {"name": "石明油漆工程有限公司", "is_winner": True, "bid_amount": 3364069, "original_bid": None},
        {"name": "祥泰和營造有限公司", "is_winner": False, "bid_amount": 4232016, "original_bid": None},
        {"name": "均嘉工程有限公司", "is_winner": False, "bid_amount": 3680707, "original_bid": None},
        {"name": "松彬工程行", "is_winner": False, "bid_amount": 3487334, "original_bid": None},
    ]},
    {"case_no": "MAA1070002", "bidders": [
        {"name": "亞成工程行", "is_winner": True, "bid_amount": 3432214, "original_bid": None},
    ]},
    {"case_no": "MAA1170006", "bidders": [
        {"name": "亞成工程行", "is_winner": True, "bid_amount": 3499770, "original_bid": None},
    ]},
    {"case_no": "MAA1270003", "bidders": [
        {"name": "亞成工程行", "is_winner": True, "bid_amount": 3087410, "original_bid": None},
        {"name": "九驊工程股份有限公司", "is_winner": False, "bid_amount": 3252095, "original_bid": None},
        {"name": "松彬工程行", "is_winner": False, "bid_amount": 3759320, "original_bid": None},
    ]},
    {"case_no": "MAA1370007", "bidders": [
        {"name": "鉅嘉室內裝修有限公司", "is_winner": True, "bid_amount": 5356638, "original_bid": None},
        {"name": "亞成工程行", "is_winner": False, "bid_amount": 5372955, "original_bid": None},
        {"name": "均嘉工程有限公司", "is_winner": False, "bid_amount": 5461533, "original_bid": None},
    ]},
    {"case_no": "MAA1270010", "bidders": [
        {"name": "均嘉工程有限公司", "is_winner": True, "bid_amount": 5738922, "original_bid": None},
        {"name": "亞成工程行", "is_winner": False, "bid_amount": 6229598, "original_bid": None},
        {"name": "炬森興業有限公司", "is_winner": False, "bid_amount": 6094400, "original_bid": None},
        {"name": "鉅嘉室內裝修有限公司", "is_winner": False, "bid_amount": 6166661, "original_bid": None},
        {"name": "育碩工程有限公司", "is_winner": False, "bid_amount": 6113980, "original_bid": None},
    ]},
]

# First, delete all existing bidders
print("Deleting old bidders...")
resp = requests.delete(
    f"{base}/bidders",
    headers={**headers, "Prefer": "return=minimal"},
    params={"id": "gt.0"},
)
print(f"  Delete: {resp.status_code}")

# Re-insert with correct data
print("Inserting updated bidders...")
for t in tenders:
    # Get tender_id
    resp = requests.get(
        f"{base}/tenders",
        headers=headers,
        params={"case_no": f"eq.{t['case_no']}", "select": "id"},
    )
    if resp.status_code != 200 or not resp.json():
        print(f"  ERROR: tender {t['case_no']} not found")
        continue
    tid = resp.json()[0]["id"]

    for b in t["bidders"]:
        row = {
            "tender_id": tid,
            "company_name": b["name"],
            "bid_amount": b["bid_amount"],
            "is_winner": b["is_winner"],
            "original_bid_amount": b.get("original_bid") or b["bid_amount"],
        }
        resp = requests.post(f"{base}/bidders", headers=headers, json=row)
        if resp.status_code in (200, 201):
            print(f"  {t['case_no']} -> {b['name']}: {b['bid_amount']}")
        else:
            print(f"  ERROR: {resp.text[:100]}")

print("\nDone!")
