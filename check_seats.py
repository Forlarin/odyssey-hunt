"""
Odyssey Hunt
------------
Checks AMC Lincoln Square 13 for IMAX 70mm showtimes of "The Odyssey" that
were previously sold out and have since opened up seats. Sends a push
notification via ntfy.sh when that happens.

State (which showtimes were sold out last time we checked) is stored in
state.json so we only alert on a *change*, not every run.
"""

import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

MOVIE_URL = "https://www.amctheatres.com/movies/the-odyssey-76238/showtimes"
THEATRE_SEARCH_TEXT = "AMC Lincoln Square 13"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "odyssey-hunt")
STATE_FILE = Path(__file__).parent / "state.json"


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


def scrape_showtimes() -> dict:
    """
    Returns a dict like:
      { "2026-08-02|7:00pm": {"sold_out": False, "date": "2026-08-02", "time": "7:00pm"} }
    """
    results = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ))

        page.goto(MOVIE_URL, wait_until="networkidle", timeout=60000)

        # Handle cookie banner if present
        try:
            page.click("text=Accept", timeout=5000)
        except Exception:
            pass

        # Select the theatre via the search box
        try:
            page.click("text=Select a Theatre", timeout=10000)
        except Exception:
            pass

        try:
            search_box = page.locator("input[type='text']").first
            search_box.fill(THEATRE_SEARCH_TEXT)
            page.wait_for_timeout(1500)
            page.locator(f"text={THEATRE_SEARCH_TEXT}").first.click(timeout=10000)
        except Exception as e:
            print(f"Could not select theatre automatically: {e}")

        page.wait_for_timeout(3000)

        # Try to filter to IMAX 70mm if a format filter chip exists
        try:
            page.click("text=IMAX 70mm", timeout=5000)
            page.wait_for_timeout(2000)
        except Exception:
            print("Could not click an IMAX 70mm filter chip (may already be filtered or named differently)")

        # Grab all showtime elements. AMC marks sold-out showtimes with
        # either a disabled button or visible "Sold Out" text.
        showtime_buttons = page.locator("[data-testid*='showtime'], button:has-text('PM'), button:has-text('AM')")
        count = showtime_buttons.count()
        print(f"Found {count} candidate showtime elements")

        for i in range(count):
            el = showtime_buttons.nth(i)
            try:
                text = el.inner_text(timeout=2000).strip()
            except Exception:
                continue
            if not text:
                continue
            is_disabled = False
            try:
                is_disabled = el.is_disabled()
            except Exception:
                pass
            sold_out = is_disabled or "sold out" in text.lower()
            key = text.lower().replace("\n", "|")
            results[key] = {"raw_text": text, "sold_out": sold_out}

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
