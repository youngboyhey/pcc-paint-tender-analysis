"""Full auto scraper: solve CAPTCHA + fetch all vendor history details"""
import requests
import re
import io
import time
import json
import os
from PIL import Image

SUPABASE_URL = "https://chclxcbmdzgdozldufzs.supabase.co"
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNoY2x4Y2JtZHpnZG96bGR1ZnpzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM5MTcwMzEsImV4cCI6MjA4OTQ5MzAzMX0.X50CLwSq1PRDDMFlsGKlSsi-n52JlZC55drAoiddo1I"


def count_colored_pixels(img, x_start=0, x_end=None):
    if x_end is None:
        x_end = img.width
    red = black = 0
    for x in range(x_start, x_end):
        for y in range(img.height):
            px = img.getpixel((x, y))
            rv, g, b, a = px
            if a < 100:
                continue
            if rv > 180 and g < 80 and b < 80:
                red += 1
            elif rv < 60 and g < 60 and b < 60:
                black += 1
    return ('red' if red > black else 'black'), max(red, black)


def solve_captcha(session):
    """Solve PCC poker CAPTCHA using color pixel counting."""
    r = session.get(
        'https://web.pcc.gov.tw/tps/atm/AtmAwardWithoutSso/QueryAtmAwardDetail?pkAtmMain=NTE3Njg3MDM=',
        timeout=15
    )
    html = r.text
    if '驗證碼' not in html:
        return True

    ans_match = re.search(r'(/tps/validate/init\?poker=answer[^"]*)', html)
    q_ids = re.findall(r'/tps/validate/init\?poker=question&id=([^"&\s]+)', html)
    id_match = re.search(r'name="id"\s+value="([^"]+)"', html)
    csrf_match = re.search(r'name="_csrf"\s+value="([^"]+)"', html)

    if not all([ans_match, q_ids, id_match, csrf_match]):
        return False

    # Download answer image
    ans_url = 'https://web.pcc.gov.tw' + ans_match.group(1).replace('&amp;', '&')
    answer_img = Image.open(io.BytesIO(session.get(ans_url, timeout=10).content)).convert('RGBA')

    # Get answer card signatures (split image in half)
    a1_suit, a1_count = count_colored_pixels(answer_img, 0, answer_img.width // 2)
    a2_suit, a2_count = count_colored_pixels(answer_img, answer_img.width // 2, answer_img.width)

    # Get question card signatures
    questions = []
    for qid in q_ids:
        q_url = f'https://web.pcc.gov.tw/tps/validate/init?poker=question&id={qid}'
        q_img = Image.open(io.BytesIO(session.get(q_url, timeout=10).content)).convert('RGBA')
        suit, count = count_colored_pixels(q_img)
        questions.append((qid, suit, count))

    # Match: same suit + closest pixel count
    matches = []
    used = set()
    for a_suit, a_count in [(a1_suit, a1_count), (a2_suit, a2_count)]:
        candidates = [(qid, s, c) for qid, s, c in questions if s == a_suit and qid not in used]
        if candidates:
            best = min(candidates, key=lambda x: abs(x[2] - a_count))
            matches.append(best[0])
            used.add(best[0])

    if len(matches) < 2:
        return False

    # Submit
    submit_data = f'choose={matches[0]}&choose={matches[1]}&id={id_match.group(1)}&_csrf={csrf_match.group(1)}'
    sr = session.post(
        'https://web.pcc.gov.tw/tps/validate/check',
        data=submit_data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        allow_redirects=True,
        timeout=15
    )
    return '驗證碼' not in sr.text


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
        if tds[i] == '預算金額' and budget is None:
            budget = pa(tds[i + 1])
        if tds[i] == '底價金額' and base_price is None:
            base_price = pa(tds[i + 1])
        if tds[i] == '總決標金額' and award_price is None:
            award_price = pa(tds[i + 1])

    in_sec = False
    for i in range(len(tds) - 1):
        if re.match(r'^(得標廠商|未得標廠商)\d*$', tds[i]) and tds[i + 1] == '':
            in_sec = True
            continue
        if not in_sec and tds[i] == '廠商名稱' and tds[i + 1] == vendor_name:
            for j in range(i + 1, min(i + 10, len(tds) - 1)):
                if tds[j] == '是否得標':
                    is_winner = '是' in tds[j + 1]
                    break
                if tds[j] == '廠商名稱':
                    break
            break

    return {'budget': budget, 'base_price': base_price, 'award_price': award_price, 'is_winner': is_winner}


def main():
    # Get records needing data
    headers = {'apikey': ANON_KEY, 'Authorization': f'Bearer {ANON_KEY}'}
    all_records = []
    offset = 0
    while True:
        r = requests.get(
            f'{SUPABASE_URL}/rest/v1/vendor_history?budget=is.null&select=id,vendor_name,case_no,detail_url&order=id&offset={offset}&limit=1000',
            headers=headers
        )
        data = r.json()
        all_records.extend(data)
        if len(data) < 1000:
            break
        offset += 1000

    print(f"Records needing data: {len(all_records)}")
    if not all_records:
        print("All records already have data!")
        return

    # Create session and solve CAPTCHA
    session = requests.Session()
    session.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'

    print("Solving CAPTCHA...")
    for attempt in range(5):
        try:
            if solve_captcha(session):
                print(f"  CAPTCHA solved on attempt {attempt + 1}!")
                break
            else:
                print(f"  Attempt {attempt + 1} failed, retrying...")
                time.sleep(2)
        except Exception as e:
            print(f"  Attempt {attempt + 1} error: {e}")
            time.sleep(5)
    else:
        print("Failed to solve CAPTCHA after 5 attempts")
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

    for i, record in enumerate(all_records):
        url = record.get('detail_url')
        if not url:
            continue

        try:
            r = session.get(url, allow_redirects=True, timeout=15)
            html = r.text

            if '驗證碼' in html:
                captcha_count += 1
                print(f"  [{i+1}] CAPTCHA triggered, re-solving...")
                time.sleep(3)
                if not solve_captcha(session):
                    print(f"  [{i+1}] CAPTCHA re-solve failed, skipping")
                    errors += 1
                    continue
                # Retry the page
                r = session.get(url, allow_redirects=True, timeout=15)
                html = r.text
                if '驗證碼' in html:
                    errors += 1
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
                    requests.patch(
                        f'{SUPABASE_URL}/rest/v1/vendor_history?id=eq.{record["id"]}',
                        headers=supa_headers,
                        json=update
                    )

            success += 1
            if (i + 1) % 20 == 0:
                print(f"  [{i+1}/{len(all_records)}] ok={success} err={errors} captcha={captcha_count} | {record['case_no']}: budget={data['budget']}")

        except requests.exceptions.ConnectionError:
            print(f"  [{i+1}] Connection error (IP blocked?), waiting 60s...")
            errors += 1
            time.sleep(60)
            # Re-create session
            session = requests.Session()
            session.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            solve_captcha(session)
        except Exception as e:
            errors += 1
            if (i + 1) % 20 == 0:
                print(f"  [{i+1}] ERROR: {str(e)[:60]}")

        # Rate limit: 1.5s between requests, 15s pause every 40
        if (i + 1) % 40 == 0:
            time.sleep(15)
        else:
            time.sleep(1.5)

    print(f"\nDone! success={success}, errors={errors}, captchas={captcha_count}")


if __name__ == '__main__':
    main()
