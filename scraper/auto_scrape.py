"""Full auto scraper: solve CAPTCHA + fetch all vendor history details
Uses curl_cffi for TLS fingerprint impersonation and scipy for CAPTCHA solving."""
import re
import io
import time
import os
from PIL import Image
import numpy as np
from scipy import ndimage

# Use curl_cffi to impersonate Chrome (bypasses TLS fingerprint detection)
from curl_cffi import requests

SUPABASE_URL = "https://chclxcbmdzgdozldufzs.supabase.co"
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNoY2x4Y2JtZHpnZG96bGR1ZnpzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM5MTcwMzEsImV4cCI6MjA4OTQ5MzAzMX0.X50CLwSq1PRDDMFlsGKlSsi-n52JlZC55drAoiddo1I"
PCC_BASE = "https://web.pcc.gov.tw"


def fetch_https(session, url):
    """Fetch URL forcing HTTPS on all redirects."""
    if url.startswith('http://'):
        url = url.replace('http://', 'https://', 1)
    for _ in range(5):
        r = session.get(url, allow_redirects=False, timeout=20)
        if r.status_code in (301, 302, 303, 307, 308):
            loc = r.headers.get('location', r.headers.get('Location', ''))
            if loc.startswith('http://'):
                loc = loc.replace('http://', 'https://', 1)
            elif loc.startswith('/'):
                loc = PCC_BASE + loc
            url = loc
            continue
        return r.text
    return r.text


def analyze_card(img):
    """Analyze a playing card image: detect color (red/black) and symbol count."""
    arr = np.array(img.convert('RGBA'))
    a = arr[:, :, 3]
    r, g, b = arr[:, :, 0].astype(float), arr[:, :, 1].astype(float), arr[:, :, 2].astype(float)
    red_mask = (a > 100) & (r > 150) & (g < 100) & (b < 100)
    black_mask = (a > 100) & (r < 80) & (g < 80) & (b < 80)
    rl, rn = ndimage.label(red_mask)
    bl, bn = ndimage.label(black_mask)
    rb = sum(1 for i in range(1, rn + 1) if np.sum(rl == i) > 100)
    bb = sum(1 for i in range(1, bn + 1) if np.sum(bl == i) > 100)
    color = 'red' if rb > bb else 'black'
    return color, max(rb, bb), max(int(np.sum(red_mask)), int(np.sum(black_mask)))


def solve_captcha(session):
    """Solve PCC poker CAPTCHA using color + blob detection."""
    html = fetch_https(session,
        f'{PCC_BASE}/tps/atm/AtmAwardWithoutSso/QueryAtmAwardDetail?pkAtmMain=NTE3Njg3MDM=')
    if '驗證碼' not in html:
        return True  # No CAPTCHA

    ans_match = re.search(r'(/tps/validate/init\?poker=answer[^"]*)', html)
    q_ids = re.findall(r'/tps/validate/init\?poker=question&(?:amp;)?id=([^"&\s]+)', html)
    id_match = re.search(r'name="id"\s+value="([^"]+)"', html)
    csrf_match = re.search(r'name="_csrf"\s+value="([^"]+)"', html)

    if not all([ans_match, q_ids, id_match, csrf_match]):
        return False

    # Get answer image (2 cards side by side)
    ans_url = PCC_BASE + ans_match.group(1).replace('&amp;', '&')
    ans_img = Image.open(io.BytesIO(session.get(ans_url, timeout=10).content))
    w, h = ans_img.width, ans_img.height

    a1 = analyze_card(ans_img.crop((0, 0, w // 2, h)))
    a2 = analyze_card(ans_img.crop((w // 2, 0, w, h)))

    # Get question card images
    questions = []
    for qid in q_ids:
        q_url = f'{PCC_BASE}/tps/validate/init?poker=question&id={qid}'
        q_img = Image.open(io.BytesIO(session.get(q_url, timeout=10).content))
        questions.append((qid, *analyze_card(q_img)))

    # Match: same color + same symbol count (or closest)
    matches = []
    used = set()
    for ac, an, ap in [a1, a2]:
        cands = [(q, c, n, p) for q, c, n, p in questions if c == ac and n == an and q not in used]
        if not cands:
            cands = [(q, c, n, p) for q, c, n, p in questions if c == ac and q not in used]
        if cands:
            best = min(cands, key=lambda x: abs(x[3] - ap))
            matches.append(best[0])
            used.add(best[0])

    if len(matches) < 2:
        return False

    # Submit CAPTCHA (don't follow redirect - it goes to HTTP)
    data = '&'.join([f'choose={m}' for m in matches])
    data += f'&id={id_match.group(1)}&_csrf={csrf_match.group(1)}'
    sr = session.post(
        f'{PCC_BASE}/tps/validate/check',
        data=data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        allow_redirects=False,
        timeout=15
    )

    # Follow redirect forcing HTTPS
    if sr.status_code in (301, 302, 303):
        loc = sr.headers.get('location', sr.headers.get('Location', ''))
        if loc.startswith('http://'):
            loc = loc.replace('http://', 'https://', 1)
        elif loc.startswith('/'):
            loc = PCC_BASE + loc
        r2 = session.get(loc, timeout=15)
        return '預算金額' in r2.text
    return '預算金額' in sr.text


def extract_detail(html, vendor_name):
    """Extract budget, base_price, award_price, is_winner from detail HTML."""
    td_pat = re.compile(r'<td[^>]*>(.*?)</td>', re.DOTALL)
    tds = [re.sub(r'<[^>]+>', '', t).strip() for t in td_pat.findall(html)]
    tds = [re.sub(r'\s+', ' ', t).strip() for t in tds]

    def pa(t):
        if not t:
            return None
        m = re.search(r'[\d,]+', t.replace(',', ''))
        return int(m.group().replace(',', '')) if m else None

    budget = base_price = award_price = None
    is_winner = None

    for i in range(len(tds) - 1):
        l, v = tds[i], tds[i + 1]
        if l == '預算金額' and budget is None:
            budget = pa(v)
        if l == '底價金額' and base_price is None:
            base_price = pa(v)
        if l == '總決標金額' and award_price is None:
            award_price = pa(v)

    # Find vendor's is_winner status
    in_section = False
    for i in range(len(tds) - 1):
        l, v = tds[i], tds[i + 1]
        if re.match(r'^(得標廠商|未得標廠商)\d*$', l) and v == '':
            in_section = True
            continue
        if not in_section and l == '廠商名稱' and v == vendor_name:
            for j in range(i + 1, min(i + 10, len(tds) - 1)):
                if tds[j] == '是否得標':
                    is_winner = '是' in tds[j + 1]
                    break
                if tds[j] == '廠商名稱':
                    break
            break

    return {'budget': budget, 'base_price': base_price, 'award_price': award_price, 'is_winner': is_winner}


def main():
    import requests as std_requests  # For Supabase (doesn't need TLS impersonation)

    # Get records needing data
    headers = {'apikey': ANON_KEY, 'Authorization': f'Bearer {ANON_KEY}'}
    all_records = []
    offset = 0
    while True:
        r = std_requests.get(
            f'{SUPABASE_URL}/rest/v1/vendor_history?budget=is.null&select=id,vendor_name,case_no,detail_url&order=id&offset={offset}&limit=1000',
            headers=headers)
        data = r.json()
        all_records.extend(data)
        if len(data) < 1000:
            break
        offset += 1000

    print(f"Records needing data: {len(all_records)}")
    if not all_records:
        print("All records already have data!")
        return

    # Create curl_cffi session (Chrome impersonation)
    session = requests.Session(impersonate='chrome')

    print("Solving CAPTCHA...")
    for attempt in range(10):
        try:
            if solve_captcha(session):
                print(f"  CAPTCHA solved on attempt {attempt + 1}!")
                break
            else:
                print(f"  Attempt {attempt + 1} failed, retrying...")
                time.sleep(5)
        except Exception as e:
            print(f"  Attempt {attempt + 1} error: {e}")
            if 'Connection' in str(e) or 'reset' in str(e).lower():
                wait = 60 * (attempt + 1)  # 60s, 120s, 180s, ...
                print(f"  IP may be blocked, waiting {wait}s...")
                time.sleep(wait)
                session = requests.Session(impersonate='chrome')
            else:
                time.sleep(10)
    else:
        print("Failed to solve CAPTCHA after 10 attempts")
        return

    # Supabase update headers
    supa_headers = {
        'Authorization': f'Bearer {SERVICE_KEY}',
        'apikey': SERVICE_KEY,
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal',
    }

    success = 0
    errors = 0
    captcha_count = 0
    consecutive_errors = 0

    for i, record in enumerate(all_records):
        url = record.get('detail_url')
        if not url:
            continue

        try:
            html = fetch_https(session, url)

            if '驗證碼' in html:
                captcha_count += 1
                print(f"  [{i+1}] CAPTCHA triggered, re-solving...")
                time.sleep(3)
                if not solve_captcha(session):
                    print(f"  [{i+1}] CAPTCHA re-solve failed, skipping")
                    errors += 1
                    consecutive_errors += 1
                    if consecutive_errors >= 10:
                        print(f"  10 consecutive errors, stopping. Will resume next run.")
                        break
                    continue
                html = fetch_https(session, url)
                if '驗證碼' in html:
                    errors += 1
                    consecutive_errors += 1
                    if consecutive_errors >= 10:
                        print(f"  10 consecutive errors, stopping. Will resume next run.")
                        break
                    continue

            data = extract_detail(html, record['vendor_name'])

            # Update Supabase
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

                # If page loaded but no budget found, mark with 0 to avoid re-fetching
                if not update and '預算金額' not in html:
                    update['budget'] = 0

                if update:
                    std_requests.patch(
                        f'{SUPABASE_URL}/rest/v1/vendor_history?id=eq.{record["id"]}',
                        headers=supa_headers,
                        json=update
                    )

            consecutive_errors = 0
            success += 1
            if (i + 1) % 10 == 0:
                print(f"  [{i+1}/{len(all_records)}] ok={success} err={errors} captcha={captcha_count} | {record['case_no']}: budget={data['budget']}")

        except (requests.RequestsError, Exception) as e:
            err_str = str(e)[:120]
            consecutive_errors += 1
            errors += 1
            print(f"  [{i+1}] ERROR ({consecutive_errors} consecutive): {err_str}")

            if consecutive_errors >= 10:
                print(f"  10 consecutive errors, stopping. Will resume next run.")
                break

            if 'Connection' in err_str or 'Timeout' in err_str or 'timed out' in err_str:
                wait_time = 90 if consecutive_errors < 5 else 300
                print(f"  Connection error, waiting {wait_time}s...")
                time.sleep(wait_time)
                session = requests.Session(impersonate='chrome')
                try:
                    if solve_captcha(session):
                        print("  Re-solved CAPTCHA after reconnect")
                    else:
                        print("  CAPTCHA re-solve failed after reconnect")
                except Exception as ce:
                    print(f"  CAPTCHA re-solve error: {str(ce)[:60]}")

        # Rate limit: 2s between requests, 20s pause every 30
        if (i + 1) % 30 == 0:
            time.sleep(20)
        else:
            time.sleep(2)

    print(f"\nDone! success={success}, errors={errors}, captchas={captcha_count}")


if __name__ == '__main__':
    main()
