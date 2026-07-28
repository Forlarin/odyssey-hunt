"""
Odyssey Hunt
------------
Checks Fandango's AMC Lincoln Square 13 theatre page for IMAX 70mm showtimes
of "The Odyssey" that were previously sold out and have since opened up
seats. Sends a push notification via ntfy.sh when that happens.

State (which showtimes were sold out last time we checked) is stored in
state.json so we only alert on a *change*, not every run.
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


def send_notification(title: str, message: str):
    import urllib.request

    req = urllib.request.Request(
        url=f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        method="POST",
        headers={"Title": title, "Priority": "high", "Tags": "movie_camera"},
    )
    try:
        urllib.request.urlopen(req, timeout=15)
        print(f"Notification sent: {title} - {message}")
    except Exception as e:
        print(f"Failed to send notification: {e}")


def load_previous_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def extract_imax_slots(body_text: str) -> list[str]:
    """
    Returns an ordered list of tokens for each showtime slot in The Odyssey's
    IMAX 70mm section, e.g. ['10:00a', '2:00p', '6:00p', 'Sold Out'].
    """
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
    imax_block = section[imax_idx:block_end_idx] if block_end_idx != -1 else section[imax_idx:imax_idx + 400]

    tokens = re.findall(r"\d{1,2}:\d{2}\s?[apAP][mM]?|Sold Out", imax_block, re.IGNORECASE)
    return tokens


def scrape_showtimes() -> dict:
    results = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
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

        def snapshot(label: str):
            try:
                page.screenshot(path=str(debug_dir / f"{label}.png"), full_page=True)
                (debug_dir / f"{label}.html").write_text(page.content())
            except Exception as e:
                print(f"Could not capture snapshot '{label}': {e}")

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
            print(f"Could not remove cookie banner: {e}")

        try:
            page.wait_for_selector("text=Loading calendar", state="detached", timeout=20000)
        except Exception:
            pass

        page.wait_for_timeout(2000)
        snapshot("final_state")

        body_text = page.inner_text("body")
        (debug_dir / "body_text.txt").write_text(body_text)

        slots = extract_imax_slots(body_text)
        print(f"Found {len(slots)} IMAX 70mm slot tokens for The Odyssey: {slots}")

        for i, token in enumerate(slots):
            sold_out = "sold out" in token.lower()
            key = f"imax_slot_{i}"
            results[key] = {"raw_text": token, "sold_out": sold_out}

        context.close()
        browser.close()

    return results


def main():
    current = scrape_showtimes()
    if not current:
        print("No showtimes found at all — the page structure may have changed, "
              "or there genuinely are no listed showtimes right now.")
        sys.exit(0)

    previous = load_previous_state()

    newly_available = []
    for key, info in current.items():
        was_sold_out = previous.get(key, {}).get("sold_out")
        is_sold_out_now = info["sold_out"]
        if was_sold_out and not is_sold_out_now:
            newly_available.append(info["raw_text"])

    if newly_available:
        msg = "Seats just opened up for:\n" + "\n".join(newly_available)
        send_notification("The Odyssey IMAX 70mm — seats available!", msg)
    else:
        print("No newly-available showtimes this run.")

    save_state(current)


if __name__ == "__main__":
    main()
