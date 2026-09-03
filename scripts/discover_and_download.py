import asyncio
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

CHROME_PATH = (
    r"C:\Program Files (x86)\Google"
    r"\Chrome\Application\chrome.exe"
)


# ============================================================
# Database
# ============================================================

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


# ============================================================
# Google Login
# ============================================================

async def google_login(page):

    print(
        "\n[*] Checking Google login button..."
    )

    try:

        google_btn = page.get_by_role(
            "button",
            name="Sign Up With Google"
        )

        await google_btn.wait_for(
            state="visible",
            timeout=5000
        )

        await google_btn.click()

        print(
            "[✓] Successfully clicked "
            "'Sign Up With Google' button!"
        )

    except Exception:

        print(
            "\nSkipped Google auto-click "
            "(You might already be logged in)."
        )


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
        return False
        
    finally:
        # 4. Ensure the temporary tab is closed so you don't leak memory
        await dl_page.close()


# ============================================================
# Main
# ============================================================

async def main():

    # --------------------------------------------------------
    # Step 1 — Check existing activities
    # --------------------------------------------------------

    existing_ids = (
        get_existing_activity_ids()
    )

    downloaded_ids = (
        get_downloaded_activity_ids()
    )

    print(
        f"[*] Activities already in SQLite: "
        f"{len(existing_ids)}"
    )

    print(
        f"[*] TCX files already in incoming/: "
        f"{len(downloaded_ids)}"
    )


    # --------------------------------------------------------
    # Step 2 — Launch browser
    # --------------------------------------------------------

    async with async_playwright() as p:

        print(
            "\n[*] Launching Google Chrome..."
        )

        context = (
            await p.chromium
            .launch_persistent_context(
                user_data_dir=str(
                    BROWSER_DATA_DIR
                ),
                executable_path=CHROME_PATH,
                headless=False
            )
        )

        if context.pages:

            page = context.pages[0]

        else:

            page = await context.new_page()


        # ----------------------------------------------------
        # Step 3 — Open Strava
        # ----------------------------------------------------

        print(
            "\n[*] Opening Strava..."
        )

        await page.goto(
            "https://strava.com",
            wait_until="domcontentloaded"
        )

        await asyncio.sleep(2)


        # ----------------------------------------------------
        # Step 4 — Google Login
        # ----------------------------------------------------

        await google_login(page)


        # Give login/navigation time
        await asyncio.sleep(3)


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
        # 1. It exists in SQLite
        # OR
        # 2. Its TCX already exists in incoming/

        handled_ids = (
            existing_ids |
            downloaded_ids
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

                success = await download_tcx(
                    page,
                    activity_id
                )


                if success:

                    print(
                        "[✓] Download completed."
                    )

                else:

                    print(
                        "[X] Download failed."
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

    try:

        loop = asyncio.get_running_loop()

        if loop.is_running():

            loop.create_task(
                main()
            )

    except RuntimeError:

        try:

            asyncio.run(
                main()
            )

        except KeyboardInterrupt:

            print(
                "\nScript manually interrupted."
            )

            sys.exit(0)