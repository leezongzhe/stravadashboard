import asyncio
import sys
from pathlib import Path
from playwright.async_api import async_playwright

# --------------------------------------------------
# Configuration
# --------------------------------------------------

ACTIVITY_ID = "19764901627"

BASE_DIR = Path(__file__).resolve().parent.parent
BROWSER_DATA_DIR = BASE_DIR / "browser_data"
DOWNLOAD_DIR = BASE_DIR / "incoming"

BROWSER_DATA_DIR.mkdir(exist_ok=True)
DOWNLOAD_DIR.mkdir(exist_ok=True)

CHROME_PATH = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

async def main():
    async with async_playwright() as p:

        # Launch Google Chrome with persistent browser storage
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_DATA_DIR),
            executable_path=CHROME_PATH,
            headless=False
        )

        if context.pages:
            page = context.pages[0]
        else:
            page = await context.new_page()

        # Open Strava
        await page.goto("https://strava.com", wait_until="domcontentloaded")
        print("Page loaded. Attempting automatic Google Login click...")

        try:
            google_btn = page.get_by_role("button", name="Sign Up With Google")
            await google_btn.wait_for(state="visible", timeout=5000)
            await google_btn.click()
            print("Successfully clicked 'Sign Up With Google' button!")
        except Exception as e:
            print("\nSkipped Google auto-click (You might already be logged in).")

        # --------------------------------------------------
        # Step 2: Open activity
        # --------------------------------------------------
        activity_url = f"https://strava.com/activities/{ACTIVITY_ID}"
        print(f"\nOpening activity: {activity_url}")
        await page.goto(activity_url, wait_until="domcontentloaded")

        # --------------------------------------------------
        # Step 3: Open TCX export
        # --------------------------------------------------
        tcx_url = f"https://strava.com/activities/{ACTIVITY_ID}/export_tcx"
        print(f"Downloading TCX from: {tcx_url}")

        async with page.expect_download() as download_info:
            try:
                # Use wait_until="commit" so it hands off to the downloader faster
                await page.goto(tcx_url, wait_until="commit")
            except Exception as e:
                if "Download is starting" in str(e):
                    print("Download safely intercepted by Playwright.")
                else:
                    raise e

        download = await download_info.value

        # --------------------------------------------------
        # Step 4: Save TCX
        # --------------------------------------------------
        output_file = DOWNLOAD_DIR / f"{ACTIVITY_ID}.tcx"
        await download.save_as(str(output_file))

        print("\n🎉 TCX download successful!")
        print(f"File saved at: {output_file}")

        # --------------------------------------------------
        # Step 5: Clean Exit
        # --------------------------------------------------
        print("\nClosing browser context cleanly...")
        await context.close()

if __name__ == "__main__":
    try:
        # Check if an event loop is already running (e.g. in certain terminal shells)
        loop = asyncio.get_running_loop()
        if loop.is_running():
            loop.create_task(main())
    except RuntimeError:
        # Standard execution loop environment
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            print("\nScript manually interrupted by user. Exiting.")
            sys.exit(0)