"""
Auto-solve PCC poker card CAPTCHA using pixel comparison.
Based on g0v/pcc.g0v.ronny.tw hack_captcha() algorithm.
"""
import requests
import re
import io
from PIL import Image


def solve_captcha(session):
    """
    Solve PCC poker CAPTCHA and return True if successful.
    The session cookies will be updated to allow access to detail pages.

    Algorithm:
    1. Load the CAPTCHA page
    2. Download the answer image (A區 - 2 cards combined)
    3. Download each question image (B區 - 6 individual cards)
    4. Compare pixel-by-pixel to find matching cards
    5. Submit the matching card IDs
    """
    # Step 1: Get CAPTCHA page
    captcha_url = 'https://web.pcc.gov.tw/tps/atm/AtmAwardWithoutSso/QueryAtmAwardDetail?pkAtmMain=NTE3Njg3MDM='
    resp = session.get(captcha_url, allow_redirects=True)
    html = resp.text

    if '驗證碼' not in html:
        return True  # No CAPTCHA needed

    # Extract validate ID
    id_match = re.search(r'name="id"\s+value="([^"]+)"', html)
    if not id_match:
        return False
    validate_id = id_match.group(1)

    # Extract CSRF token
    csrf_match = re.search(r'name="_csrf"\s+value="([^"]+)"', html)
    if not csrf_match:
        return False
    csrf = csrf_match.group(1)

    # Step 2: Download answer image (A區)
    answer_url_match = re.search(r"(/tps/validate/init\?poker=answer&[0-9.]*)", html)
    if not answer_url_match:
        return False
    answer_url = 'https://web.pcc.gov.tw' + answer_url_match.group(1)

    answer_resp = session.get(answer_url)
    answer_img = Image.open(io.BytesIO(answer_resp.content)).convert('RGB')

    # Extract the two answer cards from the combined image
    # Card 1 starts at x=6, Card 2 starts at x=89 (based on g0v code)
    # Each card is 69 pixels wide, 80 pixels tall, centered vertically
    height = answer_img.height

    answer_cards = []
    for start_x in [6, 89]:
        card = {}
        for x in range(69):
            for y in range(80):
                px = answer_img.getpixel((start_x + x, height // 2 - 40 + y))
                # Convert RGB tuple to single int like PHP imagecolorat
                color = (px[0] << 16) | (px[1] << 8) | px[2]
                card[(x, y)] = color
        answer_cards.append(card)

    # Step 3: Download question images (B區)
    question_ids = re.findall(r'/tps/validate/init\?poker=question&id=([^"]*)', html)
    if not question_ids:
        return False

    # Step 4: Match each question against answer cards
    matches = []

    for qid in question_ids:
        q_url = f'https://web.pcc.gov.tw/tps/validate/init?poker=question&id={qid}'
        q_resp = session.get(q_url)
        q_img = Image.open(io.BytesIO(q_resp.content)).convert('RGB')
        q_height = q_img.height

        for card_idx, answer_card in enumerate(answer_cards):
            match = True
            for x in range(69):
                if not match:
                    break
                for y in range(80):
                    px = q_img.getpixel((x + 1, q_height // 2 - 40 + y))
                    color = (px[0] << 16) | (px[1] << 8) | px[2]
                    if color != answer_card[(x, y)]:
                        match = False
                        break

            if match:
                matches.append(qid)
                break

    if len(matches) < 2:
        # Try with tolerance (allow small color differences)
        matches = []
        for qid in question_ids:
            q_url = f'https://web.pcc.gov.tw/tps/validate/init?poker=question&id={qid}'
            q_resp = session.get(q_url)
            q_img = Image.open(io.BytesIO(q_resp.content)).convert('RGB')
            q_height = q_img.height

            for card_idx, answer_card in enumerate(answer_cards):
                mismatches = 0
                total = 69 * 80
                for x in range(69):
                    for y in range(80):
                        px = q_img.getpixel((x + 1, q_height // 2 - 40 + y))
                        color = (px[0] << 16) | (px[1] << 8) | px[2]
                        if color != answer_card[(x, y)]:
                            mismatches += 1

                similarity = 1 - (mismatches / total)
                if similarity > 0.95:  # 95% match threshold
                    matches.append(qid)
                    break

    if len(matches) < 2:
        return False

    # Step 5: Submit answer
    submit_url = 'https://web.pcc.gov.tw/tps/validate/check'
    data = {
        'id': validate_id,
        '_csrf': csrf,
    }
    # Multiple 'choose' values
    submit_data = f'choose={matches[0]}&choose={matches[1]}&id={validate_id}&_csrf={csrf}'

    submit_resp = session.post(
        submit_url,
        data=submit_data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        allow_redirects=True
    )

    # Check if we got through
    return '驗證碼' not in submit_resp.text


def create_session():
    """Create a requests session with browser-like headers."""
    s = requests.Session()
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
    })
    return s


if __name__ == '__main__':
    s = create_session()
    print("Attempting to solve CAPTCHA...")

    for attempt in range(3):
        result = solve_captcha(s)
        if result:
            print(f"CAPTCHA solved on attempt {attempt + 1}!")

            # Test: try fetching a detail page
            test_url = 'https://web.pcc.gov.tw/tps/atm/AtmAwardWithoutSso/QueryAtmAwardDetail?pkAtmMain=NTIwMzQ0Mzg='
            r = s.get(test_url, allow_redirects=True)
            print(f"Test page: captcha={'驗證碼' in r.text}, has_budget={'預算金額' in r.text}")
            break
        else:
            print(f"Attempt {attempt + 1} failed, retrying...")
    else:
        print("Failed to solve CAPTCHA after 3 attempts")
