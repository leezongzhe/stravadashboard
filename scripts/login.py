from pathlib import Path
from playwright.sync_api import sync_playwright

# Project root
BASE_DIR = Path(__file__).resolve().parent.parent
BROWSER_DATA_DIR = BASE_DIR / "browser_data"
BROWSER_DATA_DIR.mkdir(exist_ok=True)

# 1. Define the exact path to your Google Chrome installation
# Uncomment and adjust the path for your specific Operating System:
CHROME_PATH = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"  # Windows (Typical)
# CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"  # macOS
# CHROME_PATH = "/usr/bin/google-chrome"  # Linux

with sync_playwright() as p:

    # Launch Google Chrome with persistent browser storage
    context = p.chromium.launch_persistent_context(
        user_data_dir=str(BROWSER_DATA_DIR),
        executable_path=CHROME_PATH,  # <-- Force Playwright to use this exact binary
        headless=False
    )

    # Get existing tab or create a new one
    if context.pages:
        page = context.pages[0]
    else:
        page = context.new_page()

    # Open Strava
    page.goto("https://strava.com", wait_until="domcontentloaded")
    
    print("Page loaded. Attempting automatic Google Login click...")

    try:
        # Locate the "Sign Up With Google" button by text and click it
        google_btn = page.get_by_role("button", name="Sign Up With Google")
        
        # Wait until the button is visible on screen, then click
        google_btn.wait_for(state="visible", timeout=5000)
        google_btn.click()
        print("Successfully clicked 'Sign Up With Google' button!")
        
    except Exception as e:
        print("\nCould not automatically click the Google button.")
        print("This usually means you are already logged in, or the page layout changed.")
        print(f"Error details: {e}")

    # The script will still pause here so your session stays open,
    # or in case Google prompts you for a manual 2FA verification code.
    print("\n-------------------------------------------------------------")
    print("If Google asks for a password/2FA, complete it in the browser.")
    print("Otherwise, check if you are successfully redirected to your dashboard.")
    print("-------------------------------------------------------------")
    
    input("\nPress ENTER to close the browser and save your session...")
    
    context.close()