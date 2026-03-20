"""Reset incomplete vendor_history records (budget->null) so scraper re-fetches them."""
import os
import requests

SUPABASE_URL = 'https://chclxcbmdzgdozldufzs.supabase.co'
SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_KEY', '')

headers = {
    'apikey': SERVICE_KEY,
    'Authorization': f'Bearer {SERVICE_KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'count=exact'
}

# 1. Reset budget=0 placeholder records
r1 = requests.patch(
    f'{SUPABASE_URL}/rest/v1/vendor_history?budget=eq.0',
    headers=headers,
    json={'budget': None, 'base_price': None, 'award_price': None, 'is_winner': None}
)
print(f'Reset budget=0: {r1.headers.get("content-range", "?")}')

# 2. Reset records missing base_price
r2 = requests.patch(
    f'{SUPABASE_URL}/rest/v1/vendor_history?budget=not.is.null&base_price=is.null',
    headers=headers,
    json={'budget': None, 'base_price': None, 'award_price': None, 'is_winner': None}
)
print(f'Reset missing base_price: {r2.headers.get("content-range", "?")}')

# 3. Reset records missing award_price
r3 = requests.patch(
    f'{SUPABASE_URL}/rest/v1/vendor_history?budget=not.is.null&award_price=is.null',
    headers=headers,
    json={'budget': None, 'base_price': None, 'award_price': None, 'is_winner': None}
)
print(f'Reset missing award_price: {r3.headers.get("content-range", "?")}')

# 4. Reset records missing is_winner
r4 = requests.patch(
    f'{SUPABASE_URL}/rest/v1/vendor_history?budget=not.is.null&is_winner=is.null',
    headers=headers,
    json={'budget': None, 'base_price': None, 'award_price': None, 'is_winner': None}
)
print(f'Reset missing is_winner: {r4.headers.get("content-range", "?")}')

print('Done! All incomplete records reset to null.')
