"""Upload all scraped tender data to Supabase"""
import requests
import json

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

# All 8 awarded tenders
tenders = [
    {
        "case_no": "MAA0470016",
        "case_name": "105-106年度建築物及道路零星油漆長約工作",
        "agency": "台灣中油股份有限公司煉製事業部桃園煉油廠",
        "budget": 4713093, "base_price": 3850000, "award_price": 3810000,
        "award_date": "105/01/26", "tender_year": 105,
        "detail_url": "https://web.pcc.gov.tw/tps/atm/AtmAwardWithoutSso/QueryAtmAwardDetail?pkAtmMain=NTE3Njg3MDM=",
        "bidders": [
            {"name": "石明油漆工程有限公司", "is_winner": True, "bid_amount": 3810000, "original_bid": None},
            {"name": "均嘉工程有限公司", "is_winner": False, "bid_amount": 4092157, "original_bid": None},
        ],
    },
    {
        "case_no": "MAA0670004",
        "case_name": "106-108年度建築物及道路零星油漆長約工作",
        "agency": "台灣中油股份有限公司煉製事業部桃園煉油廠",
        "budget": 4713093, "base_price": 3581970, "award_price": 3580000,
        "award_date": "106/06/02", "tender_year": 106,
        "detail_url": "https://web.pcc.gov.tw/tps/atm/AtmAwardWithoutSso/QueryAtmAwardDetail?pkAtmMain=NTIxNTQxNzQ=",
        "bidders": [
            {"name": "石明油漆工程有限公司", "is_winner": True, "bid_amount": 3580000, "original_bid": None},
            {"name": "筑丰工程有限公司", "is_winner": False, "bid_amount": 3738705, "original_bid": 3688045},
        ],
    },
    {
        "case_no": "MAA0870001",
        "case_name": "108-110年度建築物及道路零星油漆長約工作",
        "agency": "台灣中油股份有限公司煉製事業部桃園煉油廠",
        "budget": 4809930, "base_price": 3759125, "award_price": 3364069,
        "award_date": "108/03/08", "tender_year": 108,
        "detail_url": "https://web.pcc.gov.tw/tps/atm/AtmAwardWithoutSso/QueryAtmAwardDetail?pkAtmMain=NTI3MTg0OTI=",
        "bidders": [
            {"name": "石明油漆工程有限公司", "is_winner": True, "bid_amount": 3364069, "original_bid": None},
            {"name": "祥泰和營造有限公司", "is_winner": False, "bid_amount": None, "original_bid": None},
            {"name": "均嘉工程有限公司", "is_winner": False, "bid_amount": None, "original_bid": None},
            {"name": "松彬工程行", "is_winner": False, "bid_amount": 3487334, "original_bid": 3364069},
        ],
    },
    {
        "case_no": "MAA1070002",
        "case_name": "110-111年度建築物及道路零星油漆長約工作",
        "agency": "台灣中油股份有限公司煉製事業部桃園煉油廠",
        "budget": 4891216, "base_price": 3758000, "award_price": 3432214,
        "award_date": "110/03/24", "tender_year": 110,
        "detail_url": "https://web.pcc.gov.tw/tps/atm/AtmAwardWithoutSso/QueryAtmAwardDetail?pkAtmMain=NTMzNTk4ODk=",
        "bidders": [
            {"name": "亞成工程行", "is_winner": True, "bid_amount": 3432214, "original_bid": 3432214},
        ],
    },
    {
        "case_no": "MAA1170006",
        "case_name": "112-113年度桃廠建築物及道路零星油漆長約工作",
        "agency": "台灣中油股份有限公司煉製事業部桃園煉油廠",
        "budget": 4972175, "base_price": 3940000, "award_price": 3499770,
        "award_date": "111/09/06", "tender_year": 111,
        "detail_url": "https://web.pcc.gov.tw/tps/atm/AtmAwardWithoutSso/QueryAtmAwardDetail?pkAtmMain=NzAwODM4MDg=",
        "bidders": [
            {"name": "亞成工程行", "is_winner": True, "bid_amount": 3499770, "original_bid": 3499770},
        ],
    },
    {
        "case_no": "MAA1270003",
        "case_name": "112年度桃廠建築物及道路零星油漆長約工作",
        "agency": "台灣中油股份有限公司煉製事業部桃園煉油廠",
        "budget": 4686044, "base_price": 3650000, "award_price": 3087410,
        "award_date": "112/04/26", "tender_year": 112,
        "detail_url": "https://web.pcc.gov.tw/tps/atm/AtmAwardWithoutSso/QueryAtmAwardDetail?pkAtmMain=NzAyODAxNjM=",
        "bidders": [
            {"name": "亞成工程行", "is_winner": True, "bid_amount": 3087410, "original_bid": None},
            {"name": "九驊工程股份有限公司", "is_winner": False, "bid_amount": None, "original_bid": None},
            {"name": "松彬工程行", "is_winner": False, "bid_amount": 3759320, "original_bid": 3087410},
        ],
    },
    {
        "case_no": "MAA1370007",
        "case_name": "114年度桃廠建築物及道路零星油漆長約工作",
        "agency": "台灣中油股份有限公司",
        "budget": 9085959, "base_price": 6360000, "award_price": 5356638,
        "award_date": "113/11/14", "tender_year": 113,
        "detail_url": "https://web.pcc.gov.tw/tps/atm/AtmAwardWithoutSso/QueryAtmAwardDetail?pkAtmMain=NzA3MTYxNzI=",
        "bidders": [
            {"name": "鉅嘉室內裝修有限公司", "is_winner": True, "bid_amount": 5356638, "original_bid": None},
            {"name": "亞成工程行", "is_winner": False, "bid_amount": None, "original_bid": None},
            {"name": "均嘉工程有限公司", "is_winner": False, "bid_amount": 5461533, "original_bid": 5356638},
        ],
    },
    {
        "case_no": "MAA1270010",
        "case_name": "113年度桃廠建築物及道路零星油漆長約工作",
        "agency": "台灣中油股份有限公司",
        "budget": 8999991, "base_price": 6600000, "award_price": 5738922,
        "award_date": "113/01/31", "tender_year": 113,
        "detail_url": "https://web.pcc.gov.tw/tps/atm/AtmAwardWithoutSso/QueryAtmAwardDetail?pkAtmMain=NzA1MDU0NTU=",
        "bidders": [
            {"name": "均嘉工程有限公司", "is_winner": True, "bid_amount": 5738922, "original_bid": None},
            {"name": "亞成工程行", "is_winner": False, "bid_amount": None, "original_bid": None},
            {"name": "炬森興業有限公司", "is_winner": False, "bid_amount": None, "original_bid": None},
            {"name": "鉅嘉室內裝修有限公司", "is_winner": False, "bid_amount": None, "original_bid": None},
            {"name": "育碩工程有限公司", "is_winner": False, "bid_amount": 6113980, "original_bid": 5738922},
        ],
    },
]

# Save local backup
with open("output.json", "w", encoding="utf-8") as f:
    json.dump(tenders, f, ensure_ascii=False, indent=2, default=str)

print("Uploading tenders to Supabase...")
for t in tenders:
    row = {
        "case_no": t["case_no"], "case_name": t["case_name"], "agency": t["agency"],
        "budget": t["budget"], "base_price": t["base_price"], "award_price": t["award_price"],
        "award_date": t["award_date"], "is_awarded": True, "tender_year": t["tender_year"],
        "detail_url": t["detail_url"],
    }
    resp = requests.post(
        f"{base}/tenders",
        headers={**headers, "Prefer": "return=representation,resolution=merge-duplicates"},
        json=row, params={"on_conflict": "case_no"},
    )
    if resp.status_code in (200, 201) and resp.json():
        tid = resp.json()[0]["id"]
        print(f"  Tender {t['case_no']}: id={tid}")
        for b in t["bidders"]:
            br = {
                "tender_id": tid,
                "company_name": b["name"],
                "bid_amount": b.get("bid_amount"),
                "is_winner": b["is_winner"],
                "original_bid_amount": b.get("original_bid", b.get("bid_amount")),
            }
            resp2 = requests.post(f"{base}/bidders", headers=headers, json=br)
            if resp2.status_code not in (200, 201):
                print(f"    Bidder error: {resp2.text[:100]}")
    else:
        print(f"  Error {t['case_no']}: {resp.status_code} {resp.text[:200]}")

# Collect unique vendors
vendors = set()
for t in tenders:
    for b in t["bidders"]:
        vendors.add(b["name"])
print(f"\nUnique vendors ({len(vendors)}): {sorted(vendors)}")
print("Upload complete!")
