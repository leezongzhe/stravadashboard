import asyncio
import argparse
import re
import sqlite3
import sys
from pathlib import Path

from playwright.async_api import async_playwright


# ============================================================
# Configuration & Paths
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

BROWSER_DATA_DIR = BASE_DIR / "browser_data"
DOWNLOAD_DIR = BASE_DIR / "incoming"
DB_PATH = BASE_DIR / "strava_dashboard.db"

BROWSER_DATA_DIR.mkdir(exist_ok=True)
DOWNLOAD_DIR.mkdir(exist_ok=True)

# ============================================================
# Database
# ============================================================

def init_activity_status_table():
    """Create a registry for activities that do not have TCX data."""
    conn = sqlite3.connect(DB_PATH)

    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_import_status (
                activity_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                last_error TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def get_unavailable_activity_ids() -> set:
    """Return activities previously found to have no downloadable TCX."""
    init_activity_status_table()
    conn = sqlite3.connect(DB_PATH)

    try:
        rows = conn.execute(
            """
            SELECT activity_id
            FROM activity_import_status
            WHERE status = 'tcx_unavailable'
            """
        ).fetchall()
        return {str(row[0]) for row in rows}
    finally:
        conn.close()


def mark_tcx_unavailable(activity_id, error):
    """Remember a manual/non-exportable activity without fake trackpoints."""
    init_activity_status_table()
    conn = sqlite3.connect(DB_PATH)

    try:
        conn.execute(
            """
            INSERT INTO activity_import_status (
                activity_id, status, last_error, updated_at
            ) VALUES (?, 'tcx_unavailable', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(activity_id) DO UPDATE SET
                status = excluded.status,
                last_error = excluded.last_error,
                updated_at = CURRENT_TIMESTAMP
            """,
            (str(activity_id), str(error)[:1000])
        )
        conn.commit()
    finally:
        conn.close()


def clear_unavailable_activities():
    """Allow explicitly requested retries of previously unavailable TCX files."""
    init_activity_status_table()
    conn = sqlite3.connect(DB_PATH)

    try:
        conn.execute(
            "DELETE FROM activity_import_status WHERE status = 'tcx_unavailable'"
        )
        conn.commit()
    finally:
        conn.close()

def get_existing_activity_ids() -> set:
    """
    Read activity IDs already imported into SQLite.
    """

    if not DB_PATH.exists():
        return set()

    conn = sqlite3.connect(DB_PATH)

    try:

        cursor = conn.cursor()

        # Check whether trackpoints table exists
        cursor.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
            AND name='trackpoints'
            """
        )

        if not cursor.fetchone():
            return set()

        # Get all existing activity IDs
        cursor.execute(
            """
            SELECT DISTINCT activity_id
            FROM trackpoints
            """
        )

        existing_ids = {
            str(row[0])
            for row in cursor.fetchall()
        }

        return existing_ids

    finally:

        conn.close()


# ============================================================
# Check Existing TCX Files
# ============================================================

def get_downloaded_activity_ids() -> set:
    """
    Get activity IDs that already have a TCX file
    inside the incoming directory.
    """

    downloaded_ids = set()

    for file in DOWNLOAD_DIR.glob("*.tcx"):

        downloaded_ids.add(file.stem)

    return downloaded_ids


async def ensure_logged_in(page):
    """Pause in the visible browser for first-time/manual Strava login."""
    training_url = "https://www.strava.com/athlete/training"

    def is_authenticated_strava_url(url):
        return bool(re.match(
            r"https://(www\.)?strava\.com/(?!login|register)",
            url
        ))

    await page.goto(training_url, wait_until="domcontentloaded")
    await asyncio.sleep(2)

    if is_authenticated_strava_url(page.url):
        print("[✓] Existing Strava login session found.")
        return

    # Strava may expire its own session while the persistent Google session
    # remains valid. In that case, clicking the Google button is sufficient
    # and should not require the user to intervene on every launch.
    google_button_name = re.compile(
        r"(continue|sign up|log in|sign in).*google|google.*(continue|sign up|log in|sign in)",
        re.IGNORECASE
    )

    google_controls = [
        page.get_by_role("button", name=google_button_name),
        page.get_by_role("link", name=google_button_name),
    ]

    for control in google_controls:
        if await control.count() > 0 and await control.first.is_visible():
            print("[*] Reusing the saved Google login session...")
            await control.first.click()
            await asyncio.sleep(3)
            break

    if is_authenticated_strava_url(page.url):
        print("[✓] Google login completed automatically.")
        await page.goto(training_url, wait_until="domcontentloaded")
        return

    print("\n" + "=" * 60)
    print("STRAVA LOGIN REQUIRED")
    print("Complete login in the open Chrome window.")
    print("The launcher will continue automatically after login.")
    print("=" * 60)

    try:
        await page.wait_for_url(
            re.compile(r"https://www\.strava\.com/(?!login|register).+"),
            timeout=300000,
            wait_until="domcontentloaded"
        )
    except Exception as exc:
        raise RuntimeError(
            "Strava login was not completed within 5 minutes."
        ) from exc

    await page.goto(training_url, wait_until="domcontentloaded")
    await asyncio.sleep(2)

    if not is_authenticated_strava_url(page.url):
        raise RuntimeError("Strava login could not be verified.")

    print("[✓] Login completed and saved for future launches.")


async def launch_browser(playwright):
    """Launch installed Chrome, with Playwright Chromium as a fallback."""
    options = {
        "user_data_dir": str(BROWSER_DATA_DIR),
        "headless": False,
    }

    try:
        return await playwright.chromium.launch_persistent_context(
            channel="chrome",
            **options
        )
    except Exception as chrome_error:
        print(f"[!] Google Chrome could not be launched: {chrome_error}")
        print("[*] Trying Playwright Chromium instead...")
        return await playwright.chromium.launch_persistent_context(**options)


# ============================================================
# Discover Activity IDs
# ============================================================

async def discover_activity_ids(page):
    """
    Discover Strava activity IDs from the Training Log page.
    """

    print(
        "\n[*] Navigating to Strava Training Log..."
    )

    await page.goto(
        "https://www.strava.com/athlete/training",
        wait_until="domcontentloaded"
    )

    # Give Strava time to load dynamic content
    await asyncio.sleep(4)

    print(
        "[*] Searching for activity links..."
    )

    all_hrefs = await page.eval_on_selector_all(
        "a[href*='/activities/']",
        """
        elements =>
            elements.map(
                el => el.getAttribute('href')
            )
        """
    )

    discovered_ids = set()

    for href in all_hrefs:

        if not href:
            continue

        match = re.search(
            r"/activities/(\d+)",
            href
        )

        if match:

            discovered_ids.add(
                match.group(1)
            )

    print(
        f"[✓] Discovered "
        f"{len(discovered_ids)} activity IDs."
    )

    return discovered_ids


# ============================================================
# Download TCX
# ============================================================

async def download_tcx(page, activity_id):
    """
    Download one activity's TCX file safely using a temporary page.
    """
    tcx_url = f"https://www.strava.com/activities/{activity_id}/export_tcx"
    output_file = DOWNLOAD_DIR / f"{activity_id}.tcx"

    print(f"\nDownloading Activity {activity_id}...")
    print(f"URL: {tcx_url}")

    # 1. Create a temporary page in the same context (shares cookies/auth)
    dl_page = await page.context.new_page()

    try:
        async with dl_page.expect_download(timeout=15000) as download_info:
            try:
                # Trigger the download on the new tab
                await dl_page.goto(tcx_url)
            except Exception as e:
                # Safely ignore Playwright's download interception errors
                if "net::ERR_ABORTED" not in str(e) and "Download is starting" not in str(e):
                    raise

        # 2. Wait for the download to start
        download = await download_info.value

        # 3. Wait for the download to finish streaming to disk
        await download.save_as(str(output_file))
        
        print(f"[✓] Saved: {output_file.name}")
        return True

    except Exception as e:
        print(f"[X] Failed to download {activity_id}")
        print(f"    Error: {e}")
        return False, e
        
    finally:
        # 4. Ensure the temporary tab is closed so you don't leak memory
        await dl_page.close()


# ============================================================
# Main
# ============================================================

async def main(retry_unavailable=False):

    # --------------------------------------------------------
    # Step 1 — Check existing activities
    # --------------------------------------------------------

    existing_ids = (
        get_existing_activity_ids()
    )

    downloaded_ids = (
        get_downloaded_activity_ids()
    )

    if retry_unavailable:
        clear_unavailable_activities()
        print("[*] Previously unavailable activities will be retried.")

    unavailable_ids = get_unavailable_activity_ids()

    print(
        f"[*] Activities already in SQLite: "
        f"{len(existing_ids)}"
    )

    print(
        f"[*] TCX files already in incoming/: "
        f"{len(downloaded_ids)}"
    )

    print(
        f"[*] Activities recorded without TCX: "
        f"{len(unavailable_ids)}"
    )


    # --------------------------------------------------------
    # Step 2 — Launch browser
    # --------------------------------------------------------

    async with async_playwright() as p:

        print(
            "\n[*] Launching Google Chrome..."
        )

        context = await launch_browser(p)

        if context.pages:

            page = context.pages[0]

        else:

            page = await context.new_page()


        # ----------------------------------------------------
        # Step 3 — Open Strava and complete first-time login
        # ----------------------------------------------------

        print(
            "\n[*] Opening Strava..."
        )

        await ensure_logged_in(page)


        # ----------------------------------------------------
        # Step 5 — Discover Activities
        # ----------------------------------------------------

        discovered_ids = (
            await discover_activity_ids(
                page
            )
        )


        # ----------------------------------------------------
        # Step 6 — Determine New Activities
        # ----------------------------------------------------

        # Activity is considered already handled if:
        #
        # 1. It has trackpoints in SQLite
        # 2. Its TCX already exists in incoming/
        # 3. It was recorded as having no downloadable TCX

        handled_ids = (
            existing_ids |
            downloaded_ids |
            unavailable_ids
        )

        new_activities = sorted(
            discovered_ids - handled_ids
        )


        print(
            "\n" + "=" * 60
        )

        print(
            f"Activities discovered : "
            f"{len(discovered_ids)}"
        )

        print(
            f"Already handled       : "
            f"{len(handled_ids)}"
        )

        print(
            f"New activities        : "
            f"{len(new_activities)}"
        )

        print(
            "=" * 60
        )


        # ----------------------------------------------------
        # Step 7 — Download New Activities
        # ----------------------------------------------------

        if not new_activities:

            print(
                "\n[✓] Everything is up to date!"
            )

        else:

            print(
                "\n[!] New activities:"
            )

            for activity_id in new_activities:

                print(
                    f"    - {activity_id}"
                )


            print(
                "\n[*] Starting TCX downloads..."
            )


            for index, activity_id in enumerate(
                new_activities,
                start=1
            ):

                print(
                    "\n"
                    + "-" * 60
                )

                print(
                    f"[{index}/"
                    f"{len(new_activities)}]"
                )

                result = await download_tcx(
                    page,
                    activity_id
                )

                if isinstance(result, tuple):
                    success, error = result
                else:
                    success, error = result, None


                if success:

                    print(
                        "[✓] Download completed."
                    )

                else:

                    print(
                        "[!] TCX is unavailable. The activity "
                        "has been recorded in SQLite and will "
                        "not be retried automatically."
                    )

                    mark_tcx_unavailable(
                        activity_id,
                        error or "TCX download did not start"
                    )


                # Pause between downloads
                await asyncio.sleep(2)


        # ----------------------------------------------------
        # Step 8 — Close Browser
        # ----------------------------------------------------

        print(
            "\n[*] Closing browser..."
        )

        await context.close()

        print(
            "[✓] Automation finished."
        )


# ============================================================
# Program Entry
# ============================================================

if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--retry-unavailable",
        action="store_true",
        help="Retry activities previously recorded without TCX data."
    )
    args = parser.parse_args()

    try:

        loop = asyncio.get_running_loop()

        if loop.is_running():

            loop.create_task(
                main(args.retry_unavailable)
            )

    except RuntimeError:

        try:

            asyncio.run(
                main(args.retry_unavailable)
            )

        except KeyboardInterrupt:

            print(
                "\nScript manually interrupted."
            )

            sys.exit(0)
