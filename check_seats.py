"""
Odyssey Hunt
------------
Checks Fandango's AMC Lincoln Square 13 theatre page for IMAX 70mm showtimes
of "The Odyssey" and sends a push notification via ntfy.sh whenever there
are open seats.

State is stored in state.json so we only notify again when the specific set
of available showtimes actually changes, rather than spamming you every run
while nothing's different.
"""

import json
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

THEATRE_URL = "https://www.fandango.com/amc-lincoln-square-13-aabqi/theater-page"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "odyssey-hunt")
STATE_FILE = Path(__file__).parent / "state.json"

MOVIE_MARKER = "The Odyssey"
NEXT_MOVIE_MARKERS = ["Moana (2026)", "Minions & Monsters", "NEARBY THEATERS", "Nearby Theaters"]
FORMAT_MARKER = "IMAX"
BLOCK_END_MARKER = "Check Seats"


def send_notification(title, message):
    import urllib.request

    req = urllib.request.Request(
        url="https://ntfy.sh/" + NTFY_TOPIC,
        data=message.encode("utf-8"),
        method="POST",
        headers={"Title": title, "Priority": "high", "Tags": "movie_camera"},
    )
    try:
        urllib.request.urlopen(req, timeout=15)
        print("Notification sent: " + title + " - " + message)
    except Exception as e:
        print("Failed to send notification: " + str(e))


def load_previous_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def extract_imax_slots(body_text):
    start = body_text.find(MOVIE_MARKER)
    if start == -1:
        return []

    end = len(body_text)
    for marker in NEXT_MOVIE_MARKERS:
        idx = body_text.find(marker, start + len(MOVIE_MARKER))
        if idx != -1:
            end = min(end, idx)

    section = body_text[start:end]

    imax_idx = section.find(FORMAT_MARKER)
    if imax_idx == -1:
        return []

    block_end_idx = section.find(BLOCK_END_MARKER, imax_idx)
    if block_end_idx != -1:
        imax_block = section[imax_idx:block_end_idx]
    else:
        imax_block = section[imax_idx:imax_idx + 400]

    tokens = re.findall(r"\d{1,2}:\d{2}\s?[apAP][mM]?|Sold Out", imax_block, re.IGNORECASE)
    return tokens


def scrape_showtimes():
    results = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="en-US",
            viewport={"width": 1366, "height": 900},
        )
        page = context.new_page()
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = window.chrome || { runtime: {} };
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        """)

        debug_dir = Path(__file__).parent / "debug"
        debug_dir.mkdir(exist_ok=True)

        def snapshot(label):
            try:
                page.screenshot(path=str(debug_dir / (label + ".png")), full_page=True)
                (debug_dir / (label + ".html")).write_text(page.content())
            except Exception as e:
                print("Could not capture snapshot '" + label + "': " + str(e))

        page.goto(THEATRE_URL, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(6000)

        try:
            page.evaluate("""
                document.querySelectorAll(
                    '[id*="onetrust"], [class*="onetrust"], [id*="osano"], [class*="osano"], [id*="cookie"], [class*="cookie-banner"]'
                ).forEach(el => el.remove());
                document.body.style.overflow = 'auto';
            """)
        except Exception as e:
            print("Could not remove cookie banner: " + str(e))

        try:
            page.wait_for_selector("text=Loading calendar", state="detached", timeout=20000)
        except Exception:
            pass

        page.wait_for_timeout(2000)
        snapshot("final_state")

        body_text = page.inner_text("body")
        (debug_dir / "body_text.txt").write_text(body_text)

        slots = extract_imax_slots(body_text)
        print("Found " + str(len(slots)) + " IMAX 70mm slot tokens for The Odyssey: " + str(slots))

        for i, token in enumerate(slots):
            sold_out = "sold out" in token.lower()
            key = "imax_slot_" + str(i)
            results[key] = {"raw_text": token, "sold_out": sold_out}

        context.close()
        browser.close()

    return results


def main():
    current = scrape_showtimes()
    if not current:
        print("No showtimes found at all. The page structure may have changed, or there genuinely are no listed showtimes right now.")
        sys.exit(0)

    previous = load_previous_state()
    previous_available = set(previous.get("_available_signature", []))

    current_available = sorted(
        info["raw_text"] for info in current.values() if not info["sold_out"]
    )
    current_available_set = set(current_available)

    if current_available_set and current_available_set != previous_available:
        msg = "Open IMAX 70mm seats right now:\n" + "\n".join(current_available)
        send_notification("The Odyssey IMAX 70mm - seats available!", msg)
    else:
        print("No new availability to report. Currently available: " + str(current_available))

    current["_available_signature"] = current_available
    save_state(current)


if __name__ == "__main__":
    main()
