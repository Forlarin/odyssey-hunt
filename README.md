# Odyssey Hunt

Watches AMC Lincoln Square 13 for IMAX 70mm showtimes of *The Odyssey* that
were sold out and have since opened up seats. Sends you a push notification
via [ntfy.sh](https://ntfy.sh) when that happens.

## Setup (one-time, ~10 minutes)

1. **Create a free GitHub account** if you don't have one (github.com).

2. **Create a new repository** (e.g. `odyssey-hunt`), and upload these files
   to it (keep the folder structure, especially `.github/workflows/check.yml`).

3. **Get notifications on your phone:**
   - Install the [ntfy app](https://ntfy.sh/app) (iOS or Android).
   - Subscribe to the topic `odyssey-hunt`.
   - That's it — no account or signup needed. Anyone who knows the topic
     name can technically subscribe too, so if you want it fully private,
     rename the topic in `check_seats.py` and `check.yml` to something
     random and hard to guess (e.g. `odyssey-hunt-x7q2p9`).

4. **Enable GitHub Actions:**
   - Go to your repo → the "Actions" tab → click "I understand my workflows,
     go ahead and enable them."
   - It'll run automatically every 20 minutes from then on. You can also
     click "Run workflow" manually to test it right away.

## Testing it works

Go to the Actions tab → click into the latest run → check the logs. If it
says "No showtimes found at all," the site's layout has likely changed
slightly and the CSS selectors in `check_seats.py` need a small tweak (see
below).

## If AMC changes their site layout

Ticket sites update their pages periodically, which can break the specific
element selectors this script looks for (the parts like
`page.click("text=...")`). If it stops finding showtimes:

1. Open the AMC showtimes page for The Odyssey in a normal browser.
2. Right-click a showtime → "Inspect" to see the actual HTML/text used.
3. Update the matching lines in `check_seats.py`.

Feel free to paste me the new HTML and I can update the selectors for you.

## Notes

- This checks every 20 minutes, which is deliberately not-aggressive so it
  doesn't hammer AMC's servers.
- AMC's terms of service generally discourage automated scraping — this is
  built for light personal use, not high-frequency or commercial use.
- State (`state.json`) is what lets the script know something is *newly*
  available rather than alerting you every single run.
