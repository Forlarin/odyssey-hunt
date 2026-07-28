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
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

THEATRE_URL = "https://www.fandango.com/amc-lincoln-square-13-aabqi/theater-page"
MOVIE_NAME_HINT = "odyssey"
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
      { "the odyssey|imax|7:00pm": {"sold_out": False, "raw_text": "7:00pm"} }
    """
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
        snapshot("01_initial_load")

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
            page.mouse.wheel(0, 800)
            page.wait_for_timeout(4000)
            snapshot("02_after_scroll")
        except Exception as e:
            print(f"Scroll step failed: {e}")

        try:
            page.wait_for_selector("text=Loading calendar", state="detached", timeout=20000)
        except Exception:
            print("'Loading calendar' placeholder never disappeared (may indicate blocked data fetch)")
        snapshot("03_after_waiting_for_calendar")

        page.wait_for_timeout(2000)
        snapshot("04_final_state")

        odyssey_blocks = page.locator(f"text=/{MOVIE_NAME_HINT}/i")
        block_count = odyssey_blocks.count()
        print(f"Found {block_count} elements mentioning '{MOVIE_NAME_HINT}'")

        showtime_buttons = page.locator("button:has-text('PM'), button:has-text('AM'), a:has-text('PM'), a:has-text('AM')")
        count = showtime_buttons.count()
        print(f"Found {count} candidate showtime elements total on page")

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
            class_attr = ""
            try:
                class_attr = el.get_attribute("class") or ""
            except Exception:
                pass
            sold_out = is_disabled or "sold out" in text.lower() or "sold-out" in class_attr.lower() or "disabled" in class_attr.lower()
            key = f"{i}|{text.lower()}"
            results[key] = {"raw_text": text, "sold_out": sold_out}

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
