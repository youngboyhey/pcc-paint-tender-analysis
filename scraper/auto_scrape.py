"""Full auto scraper: inline CAPTCHA solving per detail page.
Uses curl_cffi for TLS fingerprint impersonation and scipy for CAPTCHA solving.
Each detail page triggers its own CAPTCHA - we solve it inline and follow the redirect."""
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


def solve_captcha_inline(session, captcha_html):
    """Solve CAPTCHA from the HTML of a detail page. Returns redirect URL or None."""
    ans_match = re.search(r'(/tps/validate/init\?poker=answer[^"]*)', captcha_html)
    q_ids = re.findall(r'/tps/validate/init\?poker=question&(?:amp;)?id=([^"&\s]+)', captcha_html)
    id_match = re.search(r'name="id"\s+value="([^"]+)"', captcha_html)
    csrf_match = re.search(r'name="_csrf"\s+value="([^"]+)"', captcha_html)

    if not all([ans_match, q_ids, id_match, csrf_match]):
        return None

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

    # Match: same color + same symbol count (or closest pixel count)
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
        return None

    # Submit CAPTCHA
    data = '&'.join([f'choose={m}' for m in matches])
    data += f'&id={id_match.group(1)}&_csrf={csrf_match.group(1)}'
    sr = session.post(
        f'{PCC_BASE}/tps/validate/check',
        data=data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        allow_redirects=False,
        timeout=15
    )

    # Success = redirect (302); Failure = 200 (shows new CAPTCHA)
    if sr.status_code in (301, 302, 303):
        loc = sr.headers.get('location', sr.headers.get('Location', ''))
        if loc.startswith('http://'):
            loc = loc.replace('http://', 'https://', 1)
        elif loc.startswith('/'):
            loc = PCC_BASE + loc
        return loc
    return None


def fetch_detail_with_captcha(session, url, max_attempts=5):
    """Fetch a detail page, solving inline CAPTCHA if needed. Returns HTML or None."""
    for attempt in range(max_attempts):
        html = fetch_https(session, url)
        if '驗證碼' not in html:
            return html  # No CAPTCHA, got the page directly

        # Solve CAPTCHA inline
        redirect_url = solve_captcha_inline(session, html)
        if redirect_url:
            result_html = fetch_https(session, redirect_url)
            if '驗證碼' not in result_html:
                return result_html
        # Wrong answer or still CAPTCHA - retry with fresh page
        time.sleep(1)
    return None


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

    # First, reset incomplete records (budget!=null but missing other fields)
    if SERVICE_KEY:
        reset_headers = {
            'apikey': SERVICE_KEY,
            'Authorization': f'Bearer {SERVICE_KEY}',
            'Content-Type': 'application/json',
            'Prefer': 'count=exact'
        }
        reset_payload = {'budget': None, 'base_price': None, 'award_price': None, 'is_winner': None}
        for condition, label in [
            ('budget=eq.0', 'budget=0 placeholder'),
        ]:
            r = std_requests.patch(
                f'{SUPABASE_URL}/rest/v1/vendor_history?{condition}',
                headers=reset_headers, json=reset_payload)
            ct = r.headers.get('content-range', '*/0').split('/')[-1]
            if ct and ct != '0' and ct != '*':
                print(f"  Reset {ct} records ({label})")

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

    # Supabase update headers
    supa_headers = {
        'Authorization': f'Bearer {SERVICE_KEY}',
        'apikey': SERVICE_KEY,
        'Content-Type': 'application/json',
        'Prefer': 'return=minimal',
    }

    success = 0
    errors = 0
    consecutive_errors = 0

    for i, record in enumerate(all_records):
        url = record.get('detail_url')
        if not url:
            continue

        try:
            html = fetch_detail_with_captcha(session, url, max_attempts=5)

            if html is None:
                errors += 1
                consecutive_errors += 1
                print(f"  [{i+1}] Failed to solve CAPTCHA after 5 attempts")
                if consecutive_errors >= 15:
                    print(f"  15 consecutive errors, stopping.")
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

                if update:
                    std_requests.patch(
                        f'{SUPABASE_URL}/rest/v1/vendor_history?id=eq.{record["id"]}',
                        headers=supa_headers,
                        json=update
                    )

            consecutive_errors = 0
            success += 1
            if (i + 1) % 10 == 0:
                print(f"  [{i+1}/{len(all_records)}] ok={success} err={errors} | {record['case_no']}: budget={data['budget']}")

        except Exception as e:
            err_str = str(e)[:120]
            consecutive_errors += 1
            errors += 1
            print(f"  [{i+1}] ERROR ({consecutive_errors}x): {err_str}")

            if consecutive_errors >= 15:
                print(f"  15 consecutive errors, stopping.")
                break

            if 'Connection' in err_str or 'Timeout' in err_str or 'timed out' in err_str or 'reset' in err_str.lower():
                print(f"  Connection error, waiting 60s...")
                time.sleep(60)
                session = requests.Session(impersonate='chrome')

        # Rate limit: 3s between records
        time.sleep(3)

    print(f"\nDone! success={success}, errors={errors}, total_processed={success+errors}")


if __name__ == '__main__':
    main()
