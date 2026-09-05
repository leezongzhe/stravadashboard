from playwright.sync_api import sync_playwright


with sync_playwright() as p:

    # Launch Chromium
    browser = p.chromium.launch(
        headless=False
    )

    # Create a browser tab
    page = browser.new_page()

    # Open Strava
    page.goto(
        "https://www.strava.com",
        wait_until="domcontentloaded"
    )

    # Display some basic information
    print("Page title:", page.title())
    print("Current URL:", page.url)

    # Keep browser open
    input("Press ENTER to close the browser...")

    browser.close()